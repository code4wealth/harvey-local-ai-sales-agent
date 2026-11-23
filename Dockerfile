FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ app/
COPY frontend/ frontend/
COPY data/ data/
COPY scripts/ scripts/
EXPOSE 8000
HEALTHCHECK --interval=1m --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8000), timeout=4).close()"
# AI inference is not in this image. With docker-compose's host networking,
# the app uses the same fixed http://127.0.0.1:11434 endpoint as the host.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
