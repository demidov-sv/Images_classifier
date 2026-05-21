import random
import re
from pathlib import Path
from typing import List

from locust import HttpUser, constant, task

_shared_task_ids: List[str] = []

IMAGE_PATH: Path = Path(__file__).parent / "test_image.png"

try:
    with open(IMAGE_PATH, "rb") as f:
        TEST_IMAGE_BYTES: bytes = f.read()
except FileNotFoundError:
    print(f"Файл {IMAGE_PATH} не найден!")
    exit(1)


class UploadUser(HttpUser):
    """Класс пользователей для генерации тяжелой POST-нагрузки.

    Имитирует клиентов, которые загружают изображения на сервер.
    Используется строгий интервал в 1 секунду для создания 
    детерминированной нагрузки.
    """

    weight: int = 1
    wait_time = constant(1)

    @task
    def upload_image(self) -> None:
        """
        Отправляет POST-запрос с тестовым изображением и регистрирует задачу в системе.

        Формирует запрос, включающий бинарные данные изображения.
        После получения ответа парсит HTML-разметку с помощью регулярного выражения,
        извлекает уникальный идентификатор задачи (task_id) и добавляет его
        в глобальный пул `_shared_task_ids` для последующего мониторинга поллерами.

        Args:
            self: Экземпляр класса UploadUser, предоставляющий контекст выполнения 
                  и встроенный HTTP-клиент (FastHttpUser/HttpUser).

        """
        files = {"file": ("test_image.png", TEST_IMAGE_BYTES, "image/png")}
        data = {"name": "locust-test"}

        with self.client.post(
            "/send",
            data=data,
            files=files,
            catch_response=True,
            name="POST /send",
        ) as response:
            if response.status_code == 200:
                match = re.search(r'<span class="task-id">([^<]+)</span>', response.text)
                if match:
                    task_id: str = match.group(1).strip()
                    _shared_task_ids.append(task_id)
                    response.success()
                else:
                    response.failure("Task ID не найден в HTML")
            elif response.status_code == 429:
                response.failure("Сработал лимит очереди (429 Too Many Requests)")
            else:
                response.failure(f"Код: {response.status_code}")


class StatusUser(HttpUser):
    """Класс пользователей для генерации легковесной GET-нагрузки.

    Имитирует клиентов, которые осуществляют поллинг (проверку статуса)
    ранее отправленных задач.

    """

    weight: int = 5
    wait_time = constant(1)

    @task
    def check_status(self) -> None:
        """
        Выполняет легковесный GET-запрос для мониторинга статуса обработки задачи.

        Извлекает случайный идентификатор задачи из глобального списка `_shared_task_ids`.
        Если список пуст (загрузчики еще не успели создать задачи), метод совершает
        ранний возврат (early return), чтобы предотвратить отправку запросов 
        с некорректным URL или вызов исключений.

        Args:
            self: Экземпляр класса StatusUser, предоставляющий контекст выполнения.

        Returns:
            None: Состояние транзакции (успешный ответ 200 OK или ошибка) 
            фиксируется во внутренней системе метрик Locust.

        """
        if not _shared_task_ids:
            return

        task_id: str = random.choice(_shared_task_ids)

        with self.client.get(
            f"/task/{task_id}",
            catch_response=True,
            name="GET /task/{id}",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Код: {response.status_code}")