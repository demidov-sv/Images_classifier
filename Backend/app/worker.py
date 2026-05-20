"""Фоновый воркер для детекции объектов на изображениях с помощью YOLOv8.

Отслеживает очередь задач из Redis, скачивает исходные файлы из S3 (MinIO),
прогоняет картинки через модель машинного обучения и сохраняет результаты
инференса обратно в базу данных.
"""

import io
import time
import json
import logging
import numpy as np
import cv2
from PIL import Image
from ultralytics import YOLO
from typing import Any
from infrastructure.redis_client import redis_conn
from infrastructure.s3_client import s3_manager, BUCKET_NAME
from infrastructure.database import database
from core.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)


def get_s3_client_with_retry() -> Any:
    """Получает S3 клиент с механизмом повторных попыток подключения.

    Полезно в случаях, когда воркер стартует быстрее, чем сервис MinIO.
    Делает до 10 попыток подключения с паузой в 3 секунды.

    Returns:
        Any: Синхронный клиент S3 (boto3 client).

    Raises:
        Exception: Если не удалось подключиться к S3 после максимального количества попыток.
    """
    max_retries = 10
    for attempt in range(max_retries):
        try:
            client = s3_manager.get_sync_client()
            client.list_buckets()
            logger.info("Успешно подключились к S3 (MinIO).")
            return client
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(
                    f"S3 (MinIO) еще не готов, ожидаю... (попытка {attempt + 1}/{max_retries})"
                )
                time.sleep(3)
            else:
                logger.critical(
                    f"Не удалось подключиться к S3 после {max_retries} попыток: {e}"
                )
                raise e


s3_client = get_s3_client_with_retry()

MODEL = None


def get_model() -> YOLO:
    """Инициализирует и возвращает модель YOLOv8.

    Загружает веса модели в оперативную память при первом вызове
    и кэширует экземпляр в глобальной переменной.

    Returns:
        YOLO: Инициализированный экземпляр модели YOLO.

    Raises:
        Exception: Если файл модели не найден или произошла ошибка при загрузке.
    """
    global MODEL
    if MODEL is None:
        model_path = "/models/yolov8n.pt"
        logger.info("Загрузка весов YOLOv8n в память воркера...")
        try:
            MODEL = YOLO(model_path)
            logger.info("YOLOv8n успешно была инициализирована.")
        except Exception as e:
            logger.critical(
                f"критическая ошибка при загрузке модели: {str(e)}", exc_info=True
            )
            raise e
    return MODEL


def main_loop() -> None:
    """Запускает бесконечный цикл обработки задач из очереди Redis.

    Основной сервис воркера:
    1. Ожидает поступления task_id в Redis.
    2. Скачивает исходное изображение из S3.
    3. Выполняет предобработку (OpenCV/PIL).
    4. Запускает классификацию через модель YOLO.
    5. Логирует результаты в базу данных (успех или отказ).
    """

    logger.info("Воркер запущен и слушает очередь 'image_queue'")
    model = get_model()

    while True:
        task_id = None
        try:
            result = redis_conn.brpop("image_queue", timeout=5)
            if not result:
                continue

            _, task_id_bytes = result
            task_id = task_id_bytes.decode("utf-8")
            start_time = time.time()

            database.log_processing(task_id)

            s3_obj = s3_client.get_object(Bucket=BUCKET_NAME, Key=f"raw/{task_id}")
            image_bytes = s3_obj["Body"].read()

            with Image.open(io.BytesIO(image_bytes)) as img:
                rgb_img = img.convert("RGB")
                opencv_img = cv2.cvtColor(np.array(rgb_img), cv2.COLOR_RGB2BGR)

            results = model(opencv_img, verbose=False)  # type: ignore

            output = []
            for r in results:
                for box in r.boxes:
                    label = model.names[int(box.cls[0])]
                    conf = float(box.conf[0])

                    output.append({"class": label, "confidence": round(conf, 4)})

            duration = round((time.time() - start_time) * 1000, 1)
            database.log_finish(task_id, duration, json.dumps(output), status="SUCCESS")
            logger.info(f"[{task_id}] Успешная обработка изображения за {duration} мс.")

        except Exception as e:
            if task_id:
                logger.error(
                    f"[{task_id}] Возникла ошибка при обработке: {str(e)}",
                    exc_info=True,
                )
                try:
                    database.log_finish(task_id, 0, json.dumps([]), status="FAILURE")
                except Exception as db_err:
                    logger.critical(
                        f"[{task_id}] Сбой базы данных при попытке записать FAILURE: {str(db_err)}",
                        exc_info=True,
                    )


if __name__ == "__main__":
    main_loop()
