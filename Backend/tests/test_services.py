import pytest
import uuid
from unittest.mock import AsyncMock

from services.services import (
    validate_and_process_image_async,
    ServiceValidationError,
)


@pytest.mark.asyncio
async def test_service_validation_raises_error_on_bad_type() -> None:
    """Проверяет, что некорректный MIME-тип вызывает ServiceValidationError."""
    with pytest.raises(ServiceValidationError) as exc_info:
        await validate_and_process_image_async(
            file_data=b"dummy text",
            content_type="text/plain",
            user_name="Alex",
        )
    assert "это не изображение" in exc_info.value.message


@pytest.mark.asyncio
async def test_service_validation_raises_error_on_huge_file() -> None:
    """Проверяет ограничение на максимальный размер файла в 10 МБ."""
    huge_data = b"0" * (11 * 1024 * 1024) 
    with pytest.raises(ServiceValidationError) as exc_info:
        await validate_and_process_image_async(
            huge_data,
            "image/jpeg",
            "Alex",
        )
    assert "файл слишком большой" in exc_info.value.message


@pytest.mark.asyncio
async def test_service_success_flow(
    mock_db: AsyncMock, mock_s3: AsyncMock, mock_redis: AsyncMock
) -> None:
    """Проверяет сквозной путь успешной обработки и генерации UUID задачи."""
    fake_image = b"\xff\xd8\xff" 

    task_id = await validate_and_process_image_async(
        file_data=fake_image, content_type="image/jpeg", user_name="Alex"
    )

    assert isinstance(task_id, str)
    assert uuid.UUID(task_id, version=4)

    mock_db.log_start_async.assert_called_once_with(task_id, len(fake_image))
    mock_s3.put_object.assert_called_once_with(
        Bucket="images", Key=f"raw/{task_id}", Body=fake_image, ContentType="image/jpeg"
    )
    mock_redis.lpush.assert_called_once_with("image_queue", task_id)