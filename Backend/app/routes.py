import os
import logging
from fastapi import File, UploadFile, Form, Request, APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


from services.services import (
    validate_and_process_image_async,
    get_task_for_presentation_async,
    ServiceValidationError,
    TaskNotFoundError
)
from services.schemas import TaskStatus  # Теперь статус живет здесь

logger = logging.getLogger(__name__)

current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "templates")
templates = Jinja2Templates(directory=templates_dir)
router = APIRouter(tags=["Images"])


@router.get("/", response_class=HTMLResponse)
async def form(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})


@router.post("/send")
async def priem(request: Request, name: str = Form(...), file: UploadFile = File(...)):
    # Читаем файл асинхронно
    data = await file.read()
    
    try:
        # Ждем выполнения асинхронного сервиса
        task_id = await validate_and_process_image_async(data, file.content_type, name)
        
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
        # Ошибка валидации — штатная ситуация (400)
        return templates.TemplateResponse(
            request,
            "failed_upload.html",
            {"request": request, "message": e.message},
            status_code=400,
        )
    except Exception:
        # Упала база или S3. Логируем трейсбэк, фронту отдаем заглушку (500)
        logger.exception(f"Критическая ошибка при загрузке от пользователя {name}")
        return templates.TemplateResponse(
            request,
            "failed_upload.html",
            {"request": request, "message": "На сервере произошла внутренняя ошибка. Мы уже разбираемся."},
            status_code=500,
        )


@router.get("/task/{task_id}")
async def get_task(request: Request, task_id: str):
    try:
        # Запрашиваем типизированную модель из БД асинхронно
        task = await get_task_for_presentation_async(task_id)

        if task.status in (TaskStatus.PROCESSING, TaskStatus.PENDING):
            return templates.TemplateResponse(
                request, "waiting.html", {"request": request, "task_id": task_id, "status": "В процессе"}
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
                request, "failed_upload.html", {"request": request, "message": "Ошибка при обработке файла воркером"}, status_code=500
            )
            
    except TaskNotFoundError:
        return templates.TemplateResponse(
            request, "failed_upload.html", {"request": request, "message": "Задача не найдена"}, status_code=404
        )