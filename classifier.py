from ultralytics import YOLO


def get_reliable_objects(image_path):
    model = YOLO("yolov8n.pt")

    # conf=0.75 отсекает всё, что ниже 75% на уровне модели
    results = model(image_path, conf=0.6, verbose=False)

    output = []
    for r in results:
        for box in r.boxes:
            label = model.names[int(box.cls[0])]
            conf = float(box.conf[0])
            output.append(f"{label}: {conf:.2%}")

    return output


# Запуск
get_reliable_objects("image.jpg")
