FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/services/api

WORKDIR /app
COPY pyproject.toml ./
COPY alembic.ini ./
COPY services/api ./services/api
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn incidentlens.app:app --host 0.0.0.0 --port 8000"]
