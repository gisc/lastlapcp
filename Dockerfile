# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8000 \
    DATABASE_PATH=/data/lastlapcp.db \
    PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["gunicorn", "--preload", "-b", "0.0.0.0:8000", "--workers", "2", "app:app"]
