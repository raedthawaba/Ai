from celery import Celery
import time
import os

# Configure Celery
celery_app = Celery(
    "hajeen_tasks",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_BACKEND_URL", "redis://localhost:6379/1"),
    include=["hajeen_platform.services.distributed_messaging.tasks"],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

# Example task (would be in hajeen_platform.services.distributed_messaging.tasks)
@celery_app.task
def process_data(data: dict) -> dict:
    print(f"Processing data: {data}")
    # Simulate some work
    import time
    time.sleep(2)
    return {"status": "processed", "original_data": data, "processed_at": time.time()}

print("Celery configuration example created.")
