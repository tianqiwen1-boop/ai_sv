#!/usr/bin/env bash
# dev 测试环境：启动或重启 bean-pattern-ai
# 用法:
#   bash deploy/dev-start.sh          # 启动（容器已存在则 docker start，否则完整部署）
#   bash deploy/dev-start.sh restart  # 重新构建镜像并部署（改代码/.env 后用这个）
set -euo pipefail

ACTION="${1:-start}"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONTAINER_NAME="bean-pattern-ai"
DOCKER_NETWORK="${DOCKER_NETWORK:-bean-dev-network}"

_run_docker() {
  if docker info >/dev/null 2>&1; then
    docker "$@"
  elif [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    docker "$@"
  else
    echo "错误: 当前用户无法访问 Docker。请 root 执行，或: usermod -aG docker ai-service 后重新登录"
    exit 1
  fi
}

_status() {
  _run_docker ps -a --filter "name=^/${CONTAINER_NAME}$" --format '{{.Names}} {{.Status}}' 2>/dev/null || true
}

case "${ACTION}" in
  start)
    if _run_docker ps -a --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
      echo "========== 启动已有容器 =========="
      _run_docker start "${CONTAINER_NAME}"
    else
      echo "========== 容器不存在，执行完整部署 =========="
      DOCKER_NETWORK="${DOCKER_NETWORK}" bash "${PROJECT_DIR}/deploy/02-root-deploy.sh"
      exit 0
    fi
    ;;
  restart)
    echo "========== 重新构建并部署 =========="
    DOCKER_NETWORK="${DOCKER_NETWORK}" bash "${PROJECT_DIR}/deploy/02-root-deploy.sh"
    exit 0
    ;;
  *)
    echo "用法: $0 [start|restart]"
    exit 1
    ;;
esac

sleep 2
echo "========== 状态 =========="
_status
echo "========== 最近日志 =========="
_run_docker logs --tail 20 "${CONTAINER_NAME}"
