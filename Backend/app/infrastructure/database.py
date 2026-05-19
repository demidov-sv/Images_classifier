# Backend/app/infrastructure/database.py
import sqlite3
import os
from datetime import datetime
from core.config import settings

def _get_connection():
    """Создает директорию, если ее нет, и возвращает подключение"""
    db_dir = os.path.dirname(settings.DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    return sqlite3.connect(settings.DB_PATH, timeout=60)

def init_db():
    conn = _get_connection()
    conn.execute("PRAGMA journal_mode=WAL;")
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
    conn.close()

def log_start(task_id, file_size):
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO logs (task_id, start_time, file_size, status) VALUES (?, ?, ?, ?)",
        (task_id, datetime.now(), file_size, "PENDING"),  
    )
    conn.commit()
    conn.close()

def log_processing(task_id):
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE logs SET status = ? WHERE task_id = ?", ("PROCESSING", task_id))
    conn.commit()
    conn.close()

def log_finish(task_id, processing_time, objects_json, status="SUCCESS"):
    conn = _get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE logs SET processing_time = ?, objects_found = ?, status = ? WHERE task_id = ?",
        (processing_time, objects_json, status, task_id),
    )
    conn.commit()
    conn.close()

def get_task_status(task_id):
    conn = _get_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM logs WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None