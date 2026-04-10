FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md alembic.ini /app/
COPY backend_app /app/backend_app
COPY alembic /app/alembic

RUN pip install --upgrade pip setuptools wheel && pip install --no-build-isolation -e .

EXPOSE 8000

CMD ["uvicorn", "backend_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
