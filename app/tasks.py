import io
import time
import json
import numpy as np
import cv2
from PIL import Image
from celery_app import celery
from ultralytics import YOLO
from database import log_finish
from s3_client import s3_client, BUCKET_NAME

MODEL = None


def get_model():
    global MODEL
    if MODEL is None:
        print("Загружаю YOLOv8s в воркер...")
        MODEL = YOLO("yolov8s.pt")
    return MODEL


@celery.task(name="process_image", ignore_result=True, bind=True)
def process_image(self, task_id: str, s3_key: str):
    start_time = time.time()
    print(f"Обрабатываю {task_id}...")

    try:
        response = s3_client.get_object(Bucket=BUCKET_NAME, Key=s3_key)
        image_bytes = response["Body"].read()

        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("RGB")
            opencv_img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

        model = get_model()
        results = model(opencv_img, verbose=False)

        output = []
        for r in results:
            for box in r.boxes:
                label = model.names[int(box.cls[0])]
                conf = float(box.conf[0])
                output.append({"class": label, "confidence": round(conf, 4)})

        duration = round(time.time() - start_time, 4)
        log_finish(task_id, duration, json.dumps(output), status="SUCCESS")

    except Exception as e:
        error_msg = f"Ошибка: {str(e)}"
        log_finish(task_id, 0, json.dumps({"error": error_msg}), status="FAILURE")
