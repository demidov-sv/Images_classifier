import uuid
import json
import logging

# Импортируем схемы из соседнего файла
from services.schemas import TaskStatus, TaskPresentationModel
from infrastructure.redis_client import async_redis_conn 
from infrastructure.s3_client import s3_manager, BUCKET_NAME
from infrastructure.database import database

logger = logging.getLogger(__name__)
MAX_FILE_SIZE = 10 * 1024 * 1024

class ServiceValidationError(Exception):
    def __init__(self, message: str):
        self.message = message

class TaskNotFoundError(Exception):
    pass


async def validate_and_process_image_async(file_data: bytes, content_type: str, user_name: str) -> str:
    if not content_type or not content_type.startswith("image/"):
        raise ServiceValidationError(f"{user_name}, это не изображение. Загрузи PNG, JPEG, WebP.")
        
    if len(file_data) > MAX_FILE_SIZE:
        raise ServiceValidationError(f"{user_name}, файл слишком большой! Максимальный размер — 10 МБ.")

    task_id = str(uuid.uuid4())
    s3_key = f"raw/{task_id}"

    try:
        await database.log_start_async(task_id, len(file_data))
        
        async with s3_manager.client as s3_client:
            await s3_client.put_object(
                Bucket=BUCKET_NAME, 
                Key=s3_key, 
                Body=file_data, 
                ContentType=content_type
            )

        # Синхронный быстрый Redis
        await async_redis_conn.lpush("image_queue", task_id)
        
        # Асинхронная БД
        

        return task_id
        
    except Exception as e:
        logger.exception(f"Ошибка инфраструктуры при постановке задачи {task_id}")
        raise


async def get_task_for_presentation_async(task_id: str) -> TaskPresentationModel:
    task_data = await database.get_task_status_async(task_id)
    
    if not task_data:
        raise TaskNotFoundError()

    status = TaskStatus(task_data["status"])
    objects = []

    if status == TaskStatus.SUCCESS:
        try:
            objects = json.loads(task_data.get("objects_found") or "[]")
        except (json.JSONDecodeError, TypeError):
            logger.warning(f"Не удалось распарсить объекты для задачи {task_id}")

    # Возвращаем строгую схему
    return TaskPresentationModel(
        task_id=task_id,
        status=status,
        processing_time=task_data.get("processing_time"),
        count=len(objects),
        objects=objects
    )