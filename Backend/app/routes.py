"""Модуль веб-интерфейса для работы с изображениями.

Содержит эндпоинты для рендеринга HTML-страниц: формы загрузки,
обработки файлов и отображения результатов классификации.
"""
import logging
from pathlib import Path
from fastapi import File, UploadFile, Form, Request, APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import status
from infrastructure.redis_client import async_redis_conn as redis_client

from services.services import (
    validate_and_process_image_async,
    get_task_for_presentation_async,
    ServiceValidationError,
    TaskNotFoundError,
)
from services.schemas import TaskStatus  

logger = logging.getLogger(__name__)

current_dir = Path(__file__).resolve().parent
templates_dir = current_dir.parent / "templates"
templates = Jinja2Templates(directory=templates_dir)
router = APIRouter(tags=["Images"])
MAX_QUEUE_SIZE = 20

@router.get("/", response_class=HTMLResponse)
async def form(request: Request) -> HTMLResponse:
    """Отображает главную страницу с формой для загрузки изображений.

    Args:
        request: Объект асинхронного запроса FastAPI

    Returns:
        HTMLResponse: HTML-страница с формой загрузки.
    """
    return templates.TemplateResponse(request, "index.html", {"request": request})


@router.post("/send")
async def priem(request: Request, name: str = Form(...), file: UploadFile = File(...)) -> HTMLResponse:
    """Принимает файл от пользователя, валидирует его и отправляет на обработку.

    Функция считывает бинарные данные, вызывает асинхронный сервис валидации 
    и, в случае успеха, возвращает страницу с номером созданной задачи. 

    Args:
        request: Объект асинхронного запроса FastAPI.
        name: Имя пользователя, полученное из текстового поля формы.
        file: Загруженный файл изображения.

    Returns:
        HTMLResponse: HTML-страница успешной загрузки (200), страница ошибки 
            валидации данных (400) или страница внутренней ошибки сервера (500).
    """
    try:
        current_queue_len = await redis_client.llen("image_queue") 
    except Exception:
        current_queue_len = 0
    if current_queue_len >= MAX_QUEUE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Сервер перегружен. В очереди уже {MAX_QUEUE_SIZE} задач. Попробуйте позже."
        )
    
    data = await file.read()

    try:
        content_type = file.content_type or "image/jpeg"
        task_id = await validate_and_process_image_async(data, content_type, name)

        return templates.TemplateResponse(
            request,
            "success_upload.html",
            {
                "request": request,
                "name": name,
                "task_id": task_id,
                "check_url": f"/task/{task_id}",
            },
        )
    except ServiceValidationError as e:
        return templates.TemplateResponse(
            request,
            "failed_upload.html",
            {"request": request, "message": e.message},
            status_code=400,
        )
    except Exception:
        logger.exception(f"Критическая ошибка при загрузке от пользователя {name}")
        return templates.TemplateResponse(
            request,
            "failed_upload.html",
            {
                "request": request,
                "message": "На сервере произошла внутренняя ошибка.Попробуй позже",
            },
            status_code=500,
        )


@router.get("/task/{task_id}")
async def get_task(request: Request, task_id: str) -> HTMLResponse:
    """Проверяет статус задачи классификации и возвращает соответствующий экран.

    Опрашивает сервисный слой для получения состояния задачи. В зависимости от статуса
    (в очереди, успешно обработано, ошибка воркера или не найдено) рендерит
    разные HTML-шаблоны для пользователя.

    Args:
        request: Объект асинхронного запроса FastAPI.
        task_id: Уникальный строковый идентификатор проверяемой задачи.

    Returns:
        HTMLResponse: HTML-страница ожидания (200), страница с результатами
            анализа (200), либо страница ошибки, если задача сломалась (500)
            или не существует (404).
    """
    try:
       
        task = await get_task_for_presentation_async(task_id)

        if task.status in (TaskStatus.PROCESSING, TaskStatus.PENDING):
            return templates.TemplateResponse(
                request,
                "waiting.html",
                {"request": request, "task_id": task_id, "status": "В процессе"},
            )

        elif task.status == TaskStatus.SUCCESS:
            return templates.TemplateResponse(
                request,
                "result.html",
                {
                    "request": request,
                    "filename": f"image_{task_id[:8]}.jpg",
                    "processing_time": task.processing_time,
                    "count": task.count,
                    "objects": task.objects,
                },
            )

        elif task.status == TaskStatus.FAILURE:
            return templates.TemplateResponse(
                request,
                "failed_upload.html",
                {"request": request, "message": "Ошибка при обработке файла воркером"},
                status_code=500,
            )

    except TaskNotFoundError:
        return templates.TemplateResponse(
            request,
            "failed_upload.html",
            {"request": request, "message": "Задача не найдена"},
            status_code=404,
        )
