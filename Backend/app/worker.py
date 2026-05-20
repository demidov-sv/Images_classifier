import io
import time
import json
import logging
import numpy as np
import cv2
from PIL import Image
from ultralytics import YOLO

from infrastructure.redis_client import redis_conn
from infrastructure.s3_client import s3_manager, BUCKET_NAME
from infrastructure.database import database
from core.logging import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def get_s3_client_with_retry():
    """
    Пытается получить клиент с ретраями. 
    Полезно, если воркер стартует быстрее, чем MinIO.
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
                logger.warning(f"S3 (MinIO) еще не готов, жду... (попытка {attempt + 1}/{max_retries})")
                time.sleep(3)
            else:
                logger.critical(f"Не удалось подключиться к S3 после {max_retries} попыток: {e}")
                raise e


s3_client = get_s3_client_with_retry()

MODEL = None

def get_model():
    global MODEL
    if MODEL is None:
        model_path = "/models/yolov8n.pt"
        logger.info("Загрузка весов YOLOv8n в память воркера...")
        try:
            MODEL = YOLO(model_path)
            logger.info("YOLOv8n успешно инициализирована.")
        except Exception as e:
            logger.critical(f"Критическая ошибка загрузки модели: {str(e)}", exc_info=True)
            raise e
    return MODEL

def main_loop():
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
                img = img.convert("RGB")
                opencv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

            
            results = model(opencv_img, verbose=False)

            output = []
            for r in results:
                for box in r.boxes:
                    label = model.names[int(box.cls[0])]
                    conf = float(box.conf[0])
                    
                    output.append({
                        "class": label,            
                        "confidence": round(conf, 4) 
                    })

            duration = round((time.time() - start_time) * 1000, 1)
            database.log_finish(task_id, duration, json.dumps(output), status="SUCCESS")
            logger.info(f"[{task_id}] Успешно обработано за {duration} мс.")

        except Exception as e:
            if task_id:
                logger.error(f"[{task_id}] Ошибка при обработке: {str(e)}", exc_info=True)
                try:
                    database.log_finish(task_id, 0, json.dumps([]), status="FAILURE")
                except Exception as db_err:
                    logger.critical(f"[{task_id}] Сбой БД при попытке записать FAILURE: {str(db_err)}", exc_info=True)

if __name__ == "__main__":
    main_loop()