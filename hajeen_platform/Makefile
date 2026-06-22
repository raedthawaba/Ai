.PHONY: dev worker test up down clean

PYTHONPATH=.

dev:
	uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

worker:
	celery -A workers.celery_app worker -l info

test:
	PYTHONPATH=. pytest

up:
	@echo "Note: Docker is deferred. Use 'make dev' and 'make worker' for local development."

down:
	@echo "Note: Docker is deferred."

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -f hajeen.sqlite3
