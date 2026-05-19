import uuid
import json
from infrastructure.redis_client import redis_conn
from infrastructure.s3_client import s3_client, BUCKET_NAME
from infrastructure import database

MAX_FILE_SIZE = 10 * 1024 * 1024

# Кастомные исключения для общения с роутером
class ServiceValidationError(Exception):
    """Исключение для ошибок валидации (размер, формат)"""
    def __init__(self, message: str):
        self.message = message

class TaskNotFoundError(Exception):
    """Исключение, если задача не найдена в БД"""
    pass


def validate_and_process_image(file_data: bytes, content_type: str, user_name: str) -> str:
    """
    Полный цикл бизнес-валидации и постановки задачи в очередь.
    """
    # 1. Валидация типа файла
    if not content_type or not content_type.startswith("image/"):
        raise ServiceValidationError(
            f"{user_name}, это не изображение. Загрузи PNG, JPEG, WebP."
        )

    # 2. Валидация размера файла
    if len(file_data) > MAX_FILE_SIZE:
        raise ServiceValidationError(
            f"{user_name}, файл слишком большой! Максимальный размер — 10 МБ."
        )

    task_id = str(uuid.uuid4())
    s3_key = f"raw/{task_id}"

    # 3. Сохранение в инфраструктуру
    s3_client.put_object(
        Bucket=BUCKET_NAME, 
        Key=s3_key, 
        Body=file_data, 
        ContentType=content_type
    )

    # 4. Логирование в БД и пуш в Redis
    database.log_start(task_id, len(file_data))
    redis_conn.lpush("image_queue", task_id)

    return task_id


def get_task_for_presentation(task_id: str) -> dict:
    """
    Получает данные из БД и готовит их для отображения в UI.
    Роутер получит чистый словарь с уже распарсенными объектами.
    """
    task_data = database.get_task_status(task_id)
    
    if not task_data:
        raise TaskNotFoundError()

    # Избавляем роутер от необходимости знать, как сериализованы данные в БД
    if task_data["status"] == "SUCCESS":
        try:
            task_data["objects"] = json.loads(task_data["objects_found"])
        except (json.JSONDecodeError, TypeError):
            task_data["objects"] = []
        task_data["count"] = len(task_data["objects"])
    else:
        task_data["objects"] = []
        task_data["count"] = 0

    return task_data