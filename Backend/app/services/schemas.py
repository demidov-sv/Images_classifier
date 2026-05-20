from enum import Enum
from typing import List, Any
from pydantic import BaseModel, Field

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"

class TaskPresentationModel(BaseModel):
    task_id: str = Field(..., description="Уникальный UUID задачи")
    status: TaskStatus = Field(..., description="Текущий статус обработки")
    processing_time: float | None = Field(None, description="Время инференса модели в секундах")
    count: int = Field(0, description="Количество найденных объектов на изображении")
    objects: List[Any] = Field(default_factory=list, description="Список найденных объектов с координатами/тегами")

    class Config:
        # Позволяет Pydantic работать не только со словарями, 
        # но и с ORM-моделями (например, если SQLAlchemy начнет возвращать объекты)
        from_attributes = True