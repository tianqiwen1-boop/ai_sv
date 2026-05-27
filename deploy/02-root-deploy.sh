#!/usr/bin/env bash
# 请用 root 执行。配置以 /home/ai-service/bean-pattern-ai/.env 为准（见 ai-service-dev部署缺项答复.md）
set -euo pipefail

DOCKER_NETWORK="${DOCKER_NETWORK:-bean-dev-network}"
PROJECT_DIR="/home/ai-service/bean-pattern-ai"
IMAGE_NAME="bean-pattern-ai:latest"
CONTAINER_NAME="bean-pattern-ai"

if [[ ! -f "${PROJECT_DIR}/.env" ]]; then
  echo "错误: 缺少 ${PROJECT_DIR}/.env"
  exit 1
fi

echo "========== 部署参数 =========="
echo "  NETWORK=${DOCKER_NETWORK}"
echo "  环境变量来自 ${PROJECT_DIR}/.env"
grep -E '^(RABBITMQ_HOST|CALLBACK_URL|AI_QUEUE_NAME)=' "${PROJECT_DIR}/.env" || true
echo

echo "========== 构建镜像 =========="
docker build -t "${IMAGE_NAME}" "${PROJECT_DIR}"

echo "========== 停止旧容器（若存在）=========="
docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

echo "========== 启动容器 =========="
docker run -d \
  --name "${CONTAINER_NAME}" \
  --restart unless-stopped \
  --network "${DOCKER_NETWORK}" \
  --env-file "${PROJECT_DIR}/.env" \
  -e AI_SERVICE_CONFIG=/app/config/config.yaml \
  -v "${PROJECT_DIR}/config/config.yaml:/app/config/config.yaml:ro" \
  "${IMAGE_NAME}"

echo "========== 最近日志 =========="
sleep 3
docker logs --tail 50 "${CONTAINER_NAME}"
