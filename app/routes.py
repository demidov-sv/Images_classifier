import uuid
import database
import json
from fastapi import File, UploadFile, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import APIRouter
from tasks import process_image
from database import log_start
from s3_client import s3_client, BUCKET_NAME


templates = Jinja2Templates(directory="templates")
router = APIRouter(tags=["Images"])


@router.get("/", response_class=HTMLResponse)
async def form(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})


@router.post("/send")
async def priem(request: Request, name: str = Form(...), file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        return templates.TemplateResponse(
            request,
            "failed_upload.html",
            {
                "request": request,
                "message": f"{name}, это не изображение. Загрузи PNG, JPEG, WebP и т.д.",
            },
            status_code=400,
        )

    task_id = str(uuid.uuid4())
    data = await file.read()
    file_size = len(data)
    s3_key = f"raw/{task_id}"

    try:
        s3_client.put_object(
            Bucket=BUCKET_NAME, Key=s3_key, Body=data, ContentType=file.content_type
        )
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "failed_upload.html",
            {"request": request, "message": f"Ошибка при загрузке файла: {str(e)}"},
            status_code=500,
        )

    log_start(task_id, file_size)
    process_image.apply_async(args=[task_id, s3_key], task_id=task_id)

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


@router.get("/task/{task_id}")
async def get_task(request: Request, task_id: str):
    task_data = database.get_task_status(task_id)

    if not task_data:
        return templates.TemplateResponse(
            request,
            "failed_upload.html",
            {"request": request, "message": "Задача не найдена"},
            status_code=404,
        )

    status = task_data["status"]

    if status in ("PROCESSING", "PENDING"):
        return templates.TemplateResponse(
            request,
            "waiting.html",
            {"request": request, "task_id": task_id, "status": "В процессе"},
        )
    elif status == "SUCCESS":
        objects = json.loads(task_data["objects_found"])
        return templates.TemplateResponse(
            request,
            "result.html",
            {
                "request": request,
                "objects": objects,
                "processing_time": task_data["processing_time"],
            },
        )
    elif status == "FAILURE":
        return templates.TemplateResponse(
            request,
            "failed_upload.html",
            {"request": request, "message": "Ошибка при обработке файла"},
            status_code=500,
        )
    else:
        return templates.TemplateResponse(
            request,
            "failed_upload.html",
            {"request": request, "message": f"Неизвестный статус: {status}"},
            status_code=500,
        )
