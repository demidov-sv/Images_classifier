from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import APIRouter
import os
import uuid

templates = Jinja2Templates(directory="templates")
router = APIRouter(tags=["Images"])
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)
from tasks import process_image
from celery_app import celery
from celery.result import AsyncResult


@router.get("/", response_class=HTMLResponse)
async def form(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@router.post("/send")
async def priem(request: Request, name: str = Form(...), file: UploadFile = File(...)):
    print (file.content_type)
    if not file.content_type or not file.content_type.startswith("image/"):

        return templates.TemplateResponse("failed_upload.html", {
            "request": request,
            "message": f"{name}, это не изображение. Загрузи PNG, JPEG, WebP и т.д."
        })
    

    task_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1] or ".jpg"
    file_path = os.path.join(UPLOAD_DIR, f"{task_id}{ext}")
    
    data = await file.read()
    with open(file_path, "wb") as f:
        f.write(data)
    process_image.apply_async(args=[task_id, file_path], task_id=task_id)
    return templates.TemplateResponse("success_upload.html", {
        "request": request,
        "name": name,
        "task_id": task_id,
        "check_url": f"/task/{task_id}"
    })

@router.get("/task/{task_id}")
async def get_task(request: Request, task_id: str):
    result = AsyncResult(task_id, app=celery)
    
    # PENDING — задача ещё не взята или не существует
    if result.state == "PENDING":
        # Проверяем, есть ли вообще инфа (может, несуществующий ID)
        if result.info is None:
            return templates.TemplateResponse("waiting.html", {
                "request": request,
                "task_id": task_id,
                "check_url": f"/task/{task_id}",
                "status": "PENDING"
            })
    
    # В процессе
    if result.state in ["PENDING", "STARTED", "PROCESSING"]:
        return templates.TemplateResponse("waiting.html", {
            "request": request,
            "task_id": task_id,
            "check_url": f"/task/{task_id}",
            "status": result.state
        })
    
    # Успех
    if result.state == "SUCCESS":
        data = result.info
        objects = data.get("objects", []) if isinstance(data, dict) else []
        return templates.TemplateResponse("result.html", {
            "request": request,
            "task_id": task_id,
            "filename": "загруженный файл",
            "processing_time": "—",
            "objects": objects,
            "count": len(objects)
        })
    
    # Ошибка
    if result.state == "FAILURE":
        return templates.TemplateResponse("failed_upload.html", {
            "request": request,
            "message": f"Ошибка обработки: {str(result.info)}"
        })
    
    # На всякий случай
    return templates.TemplateResponse("failed_upload.html", {
        "request": request,
        "message": f"Неизвестный статус: {result.state}"
    })