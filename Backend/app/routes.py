import os
from fastapi import File, UploadFile, Form, Request, APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from services import services
from services.services import ServiceValidationError, TaskNotFoundError





current_dir = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(current_dir, "templates")
templates = Jinja2Templates(directory=templates_dir)
router = APIRouter(tags=["Images"])


@router.get("/", response_class=HTMLResponse)
async def form(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})


@router.post("/send")
async def priem(request: Request, name: str = Form(...), file: UploadFile = File(...)):
    # Читаем файл (передаем в сервис чистые байты)
    data = await file.read()
    
    try:
        # Вся магия происходит внутри сервиса
        task_id = services.validate_and_process_image(data, file.content_type, name)
        
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
        # Ловим ошибку валидации из сервиса и отдаем 400/413 на фронт
        return templates.TemplateResponse(
            request,
            "failed_upload.html",
            {"request": request, "message": e.message},
            status_code=400,
        )
    except Exception as e:
        # Любые инфраструктурные падения (упал S3, упал Redis)
        return templates.TemplateResponse(
            request,
            "failed_upload.html",
            {"request": request, "message": f"Внутренняя ошибка сервера: {str(e)}"},
            status_code=500,
        )


@router.get("/task/{task_id}")
async def get_task(request: Request, task_id: str):
    try:
        # Запрашиваем уже подготовленные сервисом данные
        task_data = services.get_task_for_presentation(task_id)
        status = task_data["status"]

        if status in ("PROCESSING", "PENDING"):
            return templates.TemplateResponse(
                request, "waiting.html", {"request": request, "task_id": task_id, "status": "В процессе"}
            )
            
        elif status == "SUCCESS":
            return templates.TemplateResponse(
                request,
                "result.html",
                {
                    "request": request,
                    "filename": f"image_{task_id[:8]}.jpg", 
                    "processing_time": task_data["processing_time"],
                    "count": task_data["count"],
                    "objects": task_data["objects"], 
                },
            )
            
        elif status == "FAILURE":
            return templates.TemplateResponse(
                request, "failed_upload.html", {"request": request, "message": "Ошибка при обработке файла воркером"}, status_code=500
            )
            
    except TaskNotFoundError:
        return templates.TemplateResponse(
            request, "failed_upload.html", {"request": request, "message": "Задача не найдена"}, status_code=404
        )