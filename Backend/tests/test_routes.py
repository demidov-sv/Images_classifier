import pytest
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture
from unittest.mock import MagicMock, AsyncMock

from services.schemas import TaskStatus
from services.services import ServiceValidationError


def test_get_form_page(client: TestClient) -> None:
    """Проверяет успешную загрузку главной страницы с формой."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_send_image_success(client: TestClient, mocker: MockerFixture) -> None:
    """Проверяет успешный сценарий отправки изображения через форму."""
 
    mock_service = mocker.patch(
        "routes.validate_and_process_image_async",
        return_value="task-abc-123",
        new_callable=AsyncMock,
    )

    files = {"file": ("test.jpg", b"fake_content", "image/jpeg")}
    data = {"name": "Alex"}

    response = client.post("/send", data=data, files=files)

    assert response.status_code == 200
    assert "task-abc-123" in response.text
    mock_service.assert_called_once_with(b"fake_content", "image/jpeg", "Alex")


@pytest.mark.asyncio
async def test_send_image_validation_error(client: TestClient, mocker: MockerFixture) -> None:
    """Проверяет поведение при ошибке валидации данных (HTTP 400)."""
    mocker.patch(
        "routes.validate_and_process_image_async",
        side_effect=ServiceValidationError("Неверный формат файла"),
        new_callable=AsyncMock,
    )

    files = {"file": ("test.txt", b"text", "text/plain")}
    response = client.post("/send", data={"name": "Alex"}, files=files)

    assert response.status_code == 400
    assert "Неверный формат файла" in response.text


@pytest.mark.asyncio
async def test_get_task_success(client: TestClient, mocker: MockerFixture) -> None:
    """Проверяет рендер страницы результатов при успешном завершении задачи."""
    fake_task = MagicMock()
    fake_task.status = TaskStatus.SUCCESS
    fake_task.processing_time = 12.5
    fake_task.count = 1
    fake_task.objects = [{"class": "person", "confidence": 0.95}]

    mocker.patch(
        "routes.get_task_for_presentation_async",
        return_value=fake_task,
        new_callable=AsyncMock,
    )

    response = client.get("/task/task-123")
    assert response.status_code == 200
    assert "image_task-123.jpg" in response.text
    assert "12.5" in response.text