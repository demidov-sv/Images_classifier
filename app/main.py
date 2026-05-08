from contextlib import asynccontextmanager
from fastapi import FastAPI
from routes import router as image_router
from database import init_db
from s3_client import init_s3


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_s3()
    yield


app = FastAPI(title="Image Classifier", lifespan=lifespan)

app.include_router(image_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
