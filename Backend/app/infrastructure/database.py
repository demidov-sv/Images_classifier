# Backend/app/infrastructure/database.py
import os
import sqlite3
import logging
import aiosqlite
from datetime import datetime
from core.config import settings

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_directory_exists()

    def _ensure_directory_exists(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

    def init_db(self):
        """
        Синхронная инициализация БД (вызывается один раз при старте в lifespan).
        Включает WAL для поддержки конкурентного доступа.
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
            logger.critical(f"Ошибка инициализации БД: {e}")
            raise

    # --- АСИНХРОННЫЕ МЕТОДЫ ДЛЯ API (используются в services.py) ---

    async def log_start_async(self, task_id: str, file_size: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO logs (task_id, start_time, file_size, status) VALUES (?, ?, ?, ?)",
                (task_id, datetime.now(), file_size, "PENDING"),
            )
            await db.commit()

    async def get_task_status_async(self, task_id: str) -> dict | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM logs WHERE task_id = ?", (task_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    # --- СИНХРОННЫЕ МЕТОДЫ ДЛЯ ВОРКЕРА (worker.py пока остается синхронным) ---
    
    def log_processing(self, task_id: str):
        with sqlite3.connect(self.db_path, timeout=60) as conn:
            conn.execute("UPDATE logs SET status = ? WHERE task_id = ?", ("PROCESSING", task_id))
            conn.commit()

    def log_finish(self, task_id: str, processing_time: float, objects_json: str, status: str = "SUCCESS"):
        with sqlite3.connect(self.db_path, timeout=60) as conn:
            conn.execute(
                "UPDATE logs SET processing_time = ?, objects_found = ?, status = ? WHERE task_id = ?",
                (processing_time, objects_json, status, task_id),
            )
            conn.commit()

# Экземпляр синглтона для импорта по всему проекту
database = DatabaseManager(settings.DB_PATH)