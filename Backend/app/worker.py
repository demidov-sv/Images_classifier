import io
import time
import json
import logging
import numpy as np
import cv2
from PIL import Image
from ultralytics import YOLO

from infrastructure.redis_client import redis_conn
from infrastructure.s3_client import s3_client, BUCKET_NAME
from infrastructure import database
from core.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

MODEL = None

def get_model():
    global MODEL
    if MODEL is None:
        logger.info("Загрузка весов YOLOv8n в память воркера...")
        try:
            MODEL = YOLO("/models/yolov8n.pt")
            logger.info("YOLOv8n успешно загружена.")
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
            
            result = redis_conn.brpop("image_queue", timeout=0)
            if not result:
                continue
                
            _, task_id_bytes = result
            task_id = task_id_bytes.decode("utf-8")
            start_time = time.time()
            logger.info(f"[{task_id}] Задача извлечена из очереди. Начинаем обработку.")

            
            try:
                database.log_processing(task_id)
            except Exception as db_err:
                
                logger.error(f"[{task_id}] Ошибка обновления статуса на PROCESSING: {str(db_err)}")

            
            response = s3_client.get_object(Bucket=BUCKET_NAME, Key=f"raw/{task_id}")
            image_bytes = response["Body"].read()

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
                    logger.critical(f"[{task_id}] Критический сбой БД при записи FAILURE: {str(db_err)}", exc_info=True)
            else:
                logger.error(f"Системный сбой воркера (Redis/S3): {str(e)}", exc_info=True)

if __name__ == "__main__":
    main_loop()