# SecondTouch: the FastAPI server and the static frontend in one container.
# Azure Container Apps (or any container host) builds it from this file; the Azure OpenAI settings come in
# as environment variables / secrets at deploy time, never baked into the image.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY data/reference ./data/reference

# run as a non-root user
RUN useradd --create-home secondtouch
USER secondtouch

EXPOSE 8000
CMD ["uvicorn", "app:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
