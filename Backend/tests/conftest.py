import pytest
from typing import Generator
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture
from unittest.mock import MagicMock, AsyncMock


from main import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Создает изолированный клиент для тестирования эндпоинтов FastAPI."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_db(mocker: MockerFixture) -> AsyncMock:
    """Мокает асинхронные методы базы данных из инфраструктуры."""
    
    mock = mocker.patch("services.services.database")
    mock.log_start_async = AsyncMock()
    mock.get_task_status_async = AsyncMock()
    return mock


@pytest.fixture
def mock_redis(mocker: MockerFixture) -> AsyncMock:
    """Мокает асинхронное соединение с Redis брокером."""
    mock = mocker.patch("services.services.async_redis_conn")
    mock.lpush = AsyncMock(return_value=1)
    return mock


@pytest.fixture
def mock_s3(mocker: MockerFixture) -> AsyncMock:
    """Мокает асинхронный контекстный менеджер S3 (MinIO)."""
    mock_s3_manager = mocker.patch("services.services.s3_manager")
    
    mock_s3_client = AsyncMock()
    mock_s3_client.put_object = AsyncMock()
    
    mock_s3_manager.client = AsyncMock()
    mock_s3_manager.client.__aenter__.return_value = mock_s3_client
    
    return mock_s3_client