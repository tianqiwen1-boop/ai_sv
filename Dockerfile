FROM python:3.11-slim

WORKDIR /app

ARG PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple
ARG PIP_TRUSTED_HOST=mirrors.cloud.tencent.com
ENV PIP_DEFAULT_TIMEOUT=120

COPY requirements.txt .
RUN pip install --no-cache-dir \
    --index-url "${PIP_INDEX_URL}" \
    --trusted-host "${PIP_TRUSTED_HOST}" \
    -r requirements.txt

COPY app ./app
COPY config/config.example.yaml ./config/config.yaml

ENV PYTHONUNBUFFERED=1
ENV AI_SERVICE_CONFIG=/app/config/config.yaml

CMD ["python", "-m", "app.main"]
