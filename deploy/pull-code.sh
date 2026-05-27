#!/usr/bin/env bash
# 从 Git 远程拉取最新代码（不覆盖 .env / config/config.yaml）
# 用法:
#   bash deploy/pull-code.sh
#   bash deploy/pull-code.sh --restart   # 拉取后自动重启服务
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${PROJECT_DIR}"

RESTART=false
if [[ "${1:-}" == "--restart" ]]; then
  RESTART=true
fi

if [[ ! -d .git ]]; then
  echo "错误: ${PROJECT_DIR} 不是 Git 仓库。请先配置 remote 并完成首次 push。"
  exit 1
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "错误: 尚未配置 git remote origin。"
  echo "  git remote add origin <你的仓库URL>"
  echo "  git push -u origin main"
  exit 1
fi

echo "========== 拉取前状态 =========="
git status -sb
echo

echo "========== git pull =========="
git pull --rebase origin "$(git branch --show-current)"

echo
echo "========== 拉取完成 =========="
git log -1 --oneline

if [[ "${RESTART}" == true ]]; then
  echo
  echo "========== 重启服务 =========="
  bash "${PROJECT_DIR}/deploy/dev-start.sh" restart
else
  echo
  echo "代码已更新。若需重启服务: bash deploy/dev-start.sh restart"
  echo "或: bash deploy/pull-code.sh --restart"
fi
