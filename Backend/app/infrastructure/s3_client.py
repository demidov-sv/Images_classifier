# Backend/app/infrastructure/s3_client.py
import time
import logging
import aioboto3
import boto3
from botocore.exceptions import EndpointConnectionError, ClientError
from core.config import settings 

logger = logging.getLogger(__name__)

BUCKET_NAME = "images"

class S3Manager:
    def __init__(self):
        # Асинхронная сессия для FastAPI
        self.async_session = aioboto3.Session()
        
        # Настройки подключения
        self.client_kwargs = {
            "service_name": "s3",
            "endpoint_url": settings.S3_ENDPOINT,
            "aws_access_key_id": settings.S3_ACCESS_KEY,
            "aws_secret_access_key": settings.S3_SECRET_KEY,
            "region_name": "us-east-1",
        }

    def init_s3(self):
        """
        Синхронная проверка и создание бакета при старте (вызывается в lifespan).
        """
        sync_client = boto3.client(**self.client_kwargs)
        max_retries = 10
        for attempt in range(max_retries):
            try:
                sync_client.create_bucket(Bucket=BUCKET_NAME)
                logger.info(f"Бакет '{BUCKET_NAME}' успешно создан/готов.")
                return
            except sync_client.exceptions.BucketAlreadyOwnedByYou:
                logger.info(f"Бакет '{BUCKET_NAME}' уже существует.")
                return
            except (EndpointConnectionError, ClientError) as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Ожидание MinIO... (попытка {attempt + 1}/{max_retries})")
                    time.sleep(2)
                else:
                    logger.critical(f"Не удалось подключиться к S3 после {max_retries} попыток: {e}")
                    raise
            except Exception as e:
                logger.critical(f"Ошибка подключения к S3: {e}")
                raise

    @property
    def client(self):
        """
        Возвращает контекстный менеджер для асинхронного клиента.
        Использование: async with s3_manager.client as s3_client: ...
        """
        return self.async_session.client(**self.client_kwargs)

    def get_sync_client(self):
        """Возвращает синхронный клиент (нужен для worker.py)."""
        return boto3.client(**self.client_kwargs)

# Экземпляр синглтона для импорта по всему проекту
s3_manager = S3Manager()