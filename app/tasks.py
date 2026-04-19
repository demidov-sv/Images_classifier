from celery_app import celery
from ultralytics import YOLO

MODEL = None

def get_reliable_objects(image_path):
    global MODEL
    if MODEL is None:
        print("🔄 Загружаю YOLOv8 s...")
        MODEL = YOLO("yolov8s.pt")
        print("✅ Модель готова!")
    
    results = MODEL(image_path, verbose=False)
    
    output = []
    for r in results:
        for box in r.boxes:
            label = MODEL.names[int(box.cls[0])]
            conf = float(box.conf[0])
            output.append({"class": label, "confidence": round(conf, 4)})
    
    return output


@celery.task(name="process_image")
def process_image(task_id: str, file_path: str):
    print(f"🔧 Обрабатываю {task_id}...")
    objects = get_reliable_objects(file_path)
    print(f"✅ Готово {task_id}, найдено: {len(objects)} объектов")
    return {"status": "done", "task_id": task_id, "objects": objects}