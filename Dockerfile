FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY config/config.example.yaml ./config/config.yaml

ENV PYTHONUNBUFFERED=1
ENV AI_SERVICE_CONFIG=/app/config/config.yaml

CMD ["python", "-m", "app.main"]
