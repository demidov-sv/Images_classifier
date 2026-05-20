import asyncio
import time
import re
import httpx
from collections import defaultdict


URL = "http://localhost:8000"
IMAGE_PATH = "tests/test_image.png"
RPS = 5
DURATION = 10

try:
    IMAGE_BYTES = open(IMAGE_PATH, "rb").read()
except FileNotFoundError:
    exit(1)


async def worker(client, task_num):
    start = time.time()
    files = {"file": ("test_image.png", IMAGE_BYTES, "image/png")}
    data = {"name": f"test-{task_num}"}

    try:
        r = await client.post(f"{URL}/send", data=data, files=files)
        match = re.search(r'<span class="task-id">([^<]+)</span>', r.text)
        if not match:
            print(f"{r.status_code}")
            return ("error", time.time() - start)

        task_id = match.group(1).strip()

        while True:
            elapsed = time.time() - start
            if elapsed > 60:
                print(f"ТАЙМАУТ: Задача {task_id[:8]}... зависла на сервере.")
                return ("timeout", elapsed)

            r2 = await client.get(f"{URL}/task/{task_id}")

            # Проверяем на жесткие ошибки сервера (500, 404 и т.д.)
            if r2.status_code >= 400:
                print(
                    f"ОШИБКА: Сервер вернул код {r2.status_code} для задачи {task_id[:8]}..."
                )
                return ("error", elapsed)

            body = r2.text.lower()

            if "результат" in body:
                time_match = re.search(r"Время:\s*([\d\.]+\s*мс)", r2.text)
                proc_time = time_match.group(1) if time_match else "? мс"
                objects = re.findall(
                    r"<td>\s*(.*?)\s*</td>\s*<td[^>]*>\s*([\d\.]+%)\s*</td>", r2.text
                )

                if objects:
                    objects_str = ", ".join(
                        [f"{name} ({conf})" for name, conf in objects]
                    )
                    print(
                        f"УСПЕХ [{task_id[:8]}...]: {elapsed:.1f}с (модель: {proc_time}) | Объекты: {objects_str}"
                    )
                else:
                    print(
                        f"УСПЕХ [{task_id[:8]}...]: {elapsed:.1f}с (модель: {proc_time}) | Объектов не найдено"
                    )

                return ("success", elapsed)

            if "ошибка при обработке" in body or "ошибка сервера" in body:
                print(f"ФЕЙЛ: Ошибка воркера на задаче {task_id[:8]}...")
                return ("error", elapsed)

            if "обработка" in body or "в процессе" in body:
                await asyncio.sleep(0.25)
                continue

            print(f" СТРАННЫЙ ОТВЕТ: Код {r2.status_code}, текст: {body[:100]}")
            return ("error", elapsed)

    except Exception as e:
        print(f"ИСКЛЮЧЕНИЕ в воркере: {type(e).__name__} -> {e}")
        return ("exception", time.time() - start)


async def main():

    limits = httpx.Limits(max_connections=300, max_keepalive_connections=100)
    async with httpx.AsyncClient(
        limits=limits, timeout=30.0, follow_redirects=True
    ) as client:
        total_requests = DURATION * RPS
        print(
            f"Запуск теста: {RPS} RPS в течение {DURATION} сек (Всего запросов: {total_requests})"
        )
        print(
            "--------------------------------------------------------------------------------"
        )

        tasks = []
        start_time = time.time()

        for i in range(total_requests):
            tasks.append(asyncio.create_task(worker(client, i)))

            next_slot = start_time + (i + 1) / RPS
            sleep_time = next_slot - time.time()
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

        print(" Все запросы отправлены! Дожидаемся завершения обработки...")
        print(
            "--------------------------------------------------------------------------------"
        )
        results = await asyncio.gather(*tasks)

        status_counts = defaultdict(int)
        times_by_status = defaultdict(list)

        for status, elapsed in results:
            status_counts[status] += 1
            times_by_status[status].append(elapsed)

        print("\n=== РЕЗУЛЬТАТЫ НАГРУЗОЧНОГО ТЕСТА ===")
        print(f"Всего отправлено запросов: {len(results)}")

        for status in ("success", "error", "timeout", "exception"):
            count = status_counts[status]
            if count:
                avg = sum(times_by_status[status]) / count
                print(
                    f" {status.upper()}: {count} шт. (среднее время полного цикла: {avg:.2f}s)"
                )
            else:
                print(f" {status.upper()}: 0 шт.")

        if times_by_status["success"]:
            times = sorted(times_by_status["success"])
            print("\nПерцентили времени выполнения (успешные):")
            for p in (50, 90, 95, 99):
                idx = int(len(times) * p / 100)
                val = times[min(idx, len(times) - 1)]
                print(
                    f"  P{p}: {val:.2f} сек (столько или быстрее выполнилось {p}% запросов)"
                )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nТест прерван пользователем.")
