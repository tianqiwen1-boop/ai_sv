# Git 仓库说明

## 本地已初始化

项目目录 `/home/ai-service/bean-pattern-ai` 已做首次 Git 提交。

**不会提交的文件**（见 `.gitignore`）：

- `.env`（密钥）
- `config/config.yaml`（运行配置）

## 首次关联远程仓库

1. 在 GitHub / Gitee / GitLab 创建**空仓库**（不要勾选 README 初始化）
2. 在服务器执行：

```bash
cd /home/ai-service/bean-pattern-ai

git remote add origin https://gitee.com/你的用户名/bean-pattern-ai.git
# 或 SSH: git@github.com:你的用户名/bean-pattern-ai.git

git branch -M main
git push -u origin main
```

HTTPS 推送需使用平台 **Personal Access Token** 作为密码。

## 日常：拉取代码

```bash
cd /home/ai-service/bean-pattern-ai
bash deploy/pull-code.sh              # 仅拉取
bash deploy/pull-code.sh --restart    # 拉取并重新部署
```

## 日常：提交并推送

```bash
cd /home/ai-service/bean-pattern-ai
git add .
git status                            # 确认无 .env
git commit -m "说明修改内容"
git push
```

## dev 服务启停

```bash
bash deploy/dev-start.sh              # 启动
bash deploy/dev-start.sh restart      # 重新构建并部署
bash deploy/dev-stop.sh               # 停止
bash deploy/dev-stop.sh --remove      # 停止并删除容器
```

无 Docker 权限时用 root 执行，或将 `ai-service` 加入 `docker` 组。
