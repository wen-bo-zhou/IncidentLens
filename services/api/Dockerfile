FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/services/api

WORKDIR /app
COPY pyproject.toml ./
COPY alembic.ini ./
COPY services/api ./services/api
RUN pip install --no-cache-dir .

RUN groupadd --system incidentlens \
    && useradd --system --gid incidentlens --home-dir /app incidentlens \
    && mkdir -p /app/data/runtime \
    && chown -R incidentlens:incidentlens /app

EXPOSE 8000
USER incidentlens
CMD ["sh", "-c", "alembic upgrade head && uvicorn incidentlens.app:app --host 0.0.0.0 --port 8000 --no-proxy-headers"]
