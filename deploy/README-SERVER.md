# 服务器部署说明（bean-pattern-ai）

> 项目目录：`/home/ai-service/bean-pattern-ai`（与 Linux 用户名 `ai-service` 区分）  
> 业务：拼豆魔法屋 — AI 图生图异步 Worker

## 命名约定

| 用途 | 名称 |
|------|------|
| 代码目录 | `bean-pattern-ai` |
| Docker 镜像 | `bean-pattern-ai:latest` |
| Docker 容器 | `bean-pattern-ai` |
| 日志中的服务名 | `bean-pattern-ai`（`config.yaml` → `service.name`） |

## 当前 Docker 环境（无 root 探测结论）

| 网桥 | 网段 | 已知用途 |
|------|------|----------|
| `br-05a554e00634` | 172.20.0.0/16 | Java **backend** `172.20.0.2:8081` → 宿主机 `8081` |
| `br-5d078f64695f` | 172.19.0.0/16 | 公网 Nginx 80/443、Redis 6380、前端 8084 |
| `br-47e0760aa911` | 172.18.0.0/16 | Redis 6379、管理前端 8083 |

- **RabbitMQ 5672 未映射到宿主机** → 必须用 Docker，并加入与 `backend`、`rabbitmq` **相同的 compose 网络**。
- Docker 部署时 `RABBITMQ_HOST=rabbitmq`，`CALLBACK_URL=http://backend:8081/api/ai/task/callback`。
- `AI_CALLBACK_TOKEN` 需与 wangqi 的 Java 配置一致。

## 权限

Linux 用户 `ai-service` 若无 `docker` 组，构建/运行需 **root**（每次执行前需你确认）。

## 推荐流程

### 步骤 1：root 探查

```bash
bash /home/ai-service/bean-pattern-ai/deploy/01-root-inspect-docker.sh | tee /tmp/docker-inspect.txt
```

### 步骤 2：与 wangqi 确认

1. `docker-compose.yml` 路径  
2. RabbitMQ 是否运行  
3. `AI_CALLBACK_TOKEN` → 写入 `/home/ai-service/bean-pattern-ai/.env`

### 步骤 3：root 构建并启动

```bash
DOCKER_NETWORK=<NETWORK> bash /home/ai-service/bean-pattern-ai/deploy/02-root-deploy.sh
```

### 步骤 4：验收

```bash
docker logs -f bean-pattern-ai
```

## 并入 wangqi 的 compose（长期推荐）

在 `bean-pattern-backend/deploy/docker-compose.yml` 增加服务名 **`bean-pattern-ai`**，`context` 指向 `/home/ai-service/bean-pattern-ai`。仅执行 `docker compose up -d bean-pattern-ai`，勿全栈 `down`。

## 无需 Nginx 反代

本服务不对外暴露 HTTP 端口。
