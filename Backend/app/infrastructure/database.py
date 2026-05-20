import os
import sqlite3
import logging
import aiosqlite
from datetime import datetime
from core.config import settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Менеджер для работы с базой данных SQLite.

    Обеспечивает как асинхронные методы (для веб-сервера FastAPI),
    так и синхронные (для фонового воркера).
    """

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._ensure_directory_exists()

    def _ensure_directory_exists(self) -> None:
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

    def init_db(self) -> None:
        """Синхронная инициализация БД.

        Вызывается один раз при старте приложения.
        Создает таблицу logs, если она не существует. Включает режим WAL
        для поддержки конкурентного доступа между FastAPI и воркером.

        Raises:
            Exception: Если не удалось создать файл БД или выполнить SQL-запросы.
        """
        try:
            with sqlite3.connect(self.db_path, timeout=60) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS logs (
                        task_id TEXT PRIMARY KEY,
                        start_time TIMESTAMP,
                        processing_time REAL DEFAULT 0,
                        file_size INTEGER,
                        objects_found TEXT DEFAULT '[]',
                        status TEXT DEFAULT 'PENDING'
                    )
                """)
                conn.commit()
            logger.info(f"База данных успешно инициализирована по пути: {self.db_path}")
        except Exception as e:
            logger.critical(f"Ошибка инициализации базы данных: {e}")
            raise

    async def log_start_async(self, task_id: str, file_size: int) -> None:
        """Асинхронно записывает информацию о новой задаче в БД.

        Создает запись со статусом 'PENDING' и текущим временем старта.

        Args:
            task_id: Уникальный идентификатор задачи.
            file_size: Размер загруженного файла изображения в байтах.
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO logs (task_id, start_time, file_size, status) VALUES (?, ?, ?, ?)",
                (task_id, datetime.now(), file_size, "PENDING"),
            )
            await db.commit()

    async def get_task_status_async(self, task_id: str) -> dict | None:
        """Асинхронно получает текущее состояние задачи по ее ID.

        Args:
            task_id: Уникальный идентификатор задачи.

        Returns:
            dict | None: Словарь с полями задачи, если она найдена,
                в противном случае None.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM logs WHERE task_id = ?", (task_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    def log_processing(self, task_id: str) -> None:
        """Синхронно обновляет статус задачи на 'PROCESSING'.

        Вызывается воркером перед тем, как начать прогонять изображение через ML-модель.

        Args:
            task_id: Уникальный идентификатор задачи.
        """
        with sqlite3.connect(self.db_path, timeout=60) as conn:
            conn.execute(
                "UPDATE logs SET status = ? WHERE task_id = ?", ("PROCESSING", task_id)
            )
            conn.commit()

    def log_finish(
        self,
        task_id: str,
        processing_time: float,
        objects_json: str,
        status: str = "SUCCESS",
    ) -> None:
        """Синхронно записывает результаты выполнения задачи.

        Сохраняет время, затраченное на инференс, найденные объекты и итоговый статус.

        Args:
            task_id: Уникальный идентификатор задачи.
            processing_time: Время, затраченное на обработку (в миллисекундах).
            objects_json: JSON-строка с массивом найденных объектов и их уверенностью.
            status: Итоговый статус обработки (по умолчанию 'SUCCESS').
        """
        with sqlite3.connect(self.db_path, timeout=60) as conn:
            conn.execute(
                "UPDATE logs SET processing_time = ?, objects_found = ?, status = ? WHERE task_id = ?",
                (processing_time, objects_json, status, task_id),
            )
            conn.commit()


database = DatabaseManager(settings.DB_PATH)
