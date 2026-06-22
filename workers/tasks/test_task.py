from workers.celery_app import app

@app.task(name="workers.tasks.test_task.add")
def add(x, y):
    return x + y

@app.task(name="workers.tasks.test_task.ping_worker")
def ping_worker():
    return "pong"
