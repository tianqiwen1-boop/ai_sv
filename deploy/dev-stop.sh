#!/usr/bin/env bash
# dev 测试环境：停止 bean-pattern-ai
# 用法:
#   bash deploy/dev-stop.sh           # 停止容器（保留容器，可用 dev-start.sh 再启）
#   bash deploy/dev-stop.sh --remove  # 停止并删除容器
set -euo pipefail

CONTAINER_NAME="bean-pattern-ai"
REMOVE=false
if [[ "${1:-}" == "--remove" ]]; then
  REMOVE=true
fi

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

if ! _run_docker ps -a --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
  echo "容器 ${CONTAINER_NAME} 不存在，无需停止"
  exit 0
fi

echo "========== 停止 ${CONTAINER_NAME} =========="
_run_docker stop "${CONTAINER_NAME}" 2>/dev/null || true

if [[ "${REMOVE}" == true ]]; then
  echo "========== 删除容器 =========="
  _run_docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true
  echo "已停止并删除容器（镜像 bean-pattern-ai:latest 仍保留）"
else
  echo "已停止。再次启动: bash deploy/dev-start.sh"
fi

_run_docker ps -a --filter "name=^/${CONTAINER_NAME}$" --format 'table {{.Names}}\t{{.Status}}' 2>/dev/null || true
