#!/usr/bin/env bash
# 请用 root 执行，用于摸清 wangqi 的 Docker 栈（bean-pattern-backend）
set -euo pipefail

echo "========== Docker 版本 =========="
docker version
echo

echo "========== 运行中容器 =========="
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}\t{{.Status}}'
echo

echo "========== 网络列表 =========="
docker network ls
echo

echo "========== backend 容器网络（请记下网络名，如 xxx_default）=========="
BACKEND=$(docker ps --format '{{.Names}}' | grep -E 'backend|bean.*backend' | head -1 || true)
if [[ -z "${BACKEND}" ]]; then
  echo "未自动匹配到 backend 容器名，请手动: docker ps"
else
  echo "backend container: ${BACKEND}"
  docker inspect "${BACKEND}" --format '{{json .NetworkSettings.Networks}}' | python3 -m json.tool 2>/dev/null || \
    docker inspect "${BACKEND}" --format '{{json .NetworkSettings.Networks}}'
fi
echo

echo "========== rabbitmq 容器（若存在）=========="
RABBIT=$(docker ps --format '{{.Names}}' | grep -i rabbit | head -1 || true)
if [[ -z "${RABBIT}" ]]; then
  echo "警告: 未发现名称含 rabbit 的运行中容器，请确认 RabbitMQ 是否已启动"
else
  echo "rabbitmq container: ${RABBIT}"
  docker inspect "${RABBIT}" --format '{{json .NetworkSettings.Networks}}' | python3 -m json.tool 2>/dev/null || \
    docker inspect "${RABBIT}" --format '{{json .NetworkSettings.Networks}}'
fi
echo

echo "========== compose 项目（若有标签）=========="
docker ps --format '{{.Names}}\t{{.Label "com.docker.compose.project"}}\t{{.Label "com.docker.compose.project.working_dir"}}' | column -t -s $'\t' || true
echo

echo "========== 将部署用户加入 docker 组（可选，执行后需重新登录 SSH）=========="
echo "  usermod -aG docker ai-service   # Linux 用户名仍为 ai-service，与项目名 bean-pattern-ai 无关"
echo
