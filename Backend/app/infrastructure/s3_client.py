import time
import logging
import aioboto3
import boto3
from botocore.exceptions import EndpointConnectionError, ClientError
from core.config import settings
from typing import Any

logger = logging.getLogger(__name__)


BUCKET_NAME = "images"


class S3Manager:
    """Менеджер для работы с объектным хранилищем S3 (MinIO).

    Предоставляет методы для инициализации бакета, а также интерфейсы
    для получения как асинхронных (FastAPI), так и синхронных (Worker) клиентов.
    """

    def __init__(self) -> None:

        self.async_session = aioboto3.Session()

        self.client_kwargs = {
            "service_name": "s3",
            "endpoint_url": settings.S3_ENDPOINT,
            "aws_access_key_id": settings.S3_ACCESS_KEY,
            "aws_secret_access_key": settings.S3_SECRET_KEY,
            "region_name": "us-east-1",
        }

    def init_s3(self) -> None:
        """Синхронная инициализация бакета S3 при старте приложения.

        Выполняет проверку существования бакета и создает его при необходимости.
        Содержит механизм повторных попыток на случай, если сервис S3
        (MinIO) еще не успел полностью запуститься. Вызывается один раз в lifespan.

        Raises:
            Exception: Если не удалось подключиться к S3 после всех попыток.
        """
        max_retries = 10
        for attempt in range(max_retries):
            sync_client = None
            try:
                sync_client = boto3.client(**self.client_kwargs)
                sync_client.create_bucket(Bucket=BUCKET_NAME)
                logger.info(f"Бакет '{BUCKET_NAME}' успешно создан.")
                return
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code")
                if error_code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                    logger.info(
                        f"Бакет '{BUCKET_NAME}' уже существует и готов к работе."
                    )
                    return

                self._handle_retry(e, attempt, max_retries)
            except EndpointConnectionError as e:
                self._handle_retry(e, attempt, max_retries)
            except Exception as e:
                logger.critical(f"Критическая ошибка подключения к S3: {e}")
                raise
            finally:
                if sync_client is not None:
                    sync_client.close()

    def _handle_retry(self, e, attempt, max_retries) -> None:
        if attempt < max_retries - 1:
            logger.warning(
                f"Ожидание MinIO... (попытка {attempt + 1}/{max_retries}). Ошибка: {e}"
            )
            time.sleep(2)
        else:
            logger.critical(
                f"Не удалось подключиться к S3 после {max_retries} попыток: {e}"
            )
            raise e

    @property
    def client(self) -> Any:
        """Асинхронный клиент для работы с S3.

        Используется для выполнения операций с бакетами и объектами внутри FastAPI.

        Returns:
            Any: Асинхронный контекстный менеджер, возвращающий S3-клиент

        """
        return self.async_session.client(**self.client_kwargs)

    def get_sync_client(self) -> Any:
        """Возвращает синхронный клиент (используется в фоновом воркере)."""
        return boto3.client(**self.client_kwargs)


s3_manager = S3Manager()
