from contextlib import asynccontextmanager
from fastapi import FastAPI
from routes import router as image_router
from infrastructure.database import database
from infrastructure.s3_client import s3_manager

@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()  # Вызываем через объект
    s3_manager.init_s3() # Вызываем через объект
    yield


app = FastAPI(title="Image Classifier", lifespan=lifespan)

app.include_router(image_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
