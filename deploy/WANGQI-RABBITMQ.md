# wangqi 侧：RabbitMQ + bean-pattern-ai 接入清单

> bean-pattern-ai 代码目录：`/home/ai-service/bean-pattern-ai`  
> 当前状态：**等待 RabbitMQ 部署**（`docker ps -a | grep -iE 'rabbit|mq'` 无结果）

## 已确认（deploy 栈）

| 项 | 值 |
|----|-----|
| Compose 路径 | `/home/opt/bean-pattern-backend/deploy/docker-compose.yml` |
| Backend **service 名** | `backend` |
| Backend **容器名** | `bean-pattern-backend` |
| Backend **网络** | `deploy_default` |
| 宿主机 API | `http://127.0.0.1:8081` |

## wangqi 需新增 RabbitMQ（建议）

在 **同一 compose 项目**（`deploy`）中增加 RabbitMQ，并与 `backend` 使用 **相同 network**（`deploy_default`）。

**建议 compose 片段：**

```yaml
  rabbitmq:
    image: rabbitmq:3.13-management-alpine
    container_name: bean-pattern-rabbitmq
    restart: unless-stopped
    environment:
      RABBITMQ_DEFAULT_USER: admin
      RABBITMQ_DEFAULT_PASS: <与 ai-service .env 中 RABBITMQ_PASSWORD 一致>
    networks:
      - default          # 与 backend 相同
    # 5672 可不映射宿主机；bean-pattern-ai 容器同网即可
    # 15672 管理界面可选映射到 127.0.0.1
```

**Java backend 需配置**（若尚未配置）：

- RabbitMQ 地址：`rabbitmq:5672`（compose 服务名）
- 启动时声明队列：**`ai.generate.request`**
- 回调鉴权：`AI_CALLBACK_TOKEN` 与 `/home/ai-service/bean-pattern-ai/.env` 中一致

## bean-pattern-ai 部署参数（MQ 就绪后）

| 环境变量 | 值（deploy 栈） |
|----------|-----------------|
| `DOCKER_NETWORK` | `deploy_default` |
| `RABBITMQ_HOST` | `rabbitmq`（compose 服务名，需与 wangqi 一致） |
| `CALLBACK_URL` | `http://backend:8081/api/ai/task/callback` |

部署命令（root，执行前与 ai-service 同事确认）：

```bash
DOCKER_NETWORK=deploy_default bash /home/ai-service/bean-pattern-ai/deploy/02-root-deploy.sh
```

## 验收

1. Java 启动后队列 `ai.generate.request` 存在  
2. `docker logs bean-pattern-ai` 出现 `RabbitMQ 已连接 queue=ai.generate.request`  
3. 小程序触发 AI 任务 → PROCESSING → SUCCESS  

## 待办（非 wangqi）

- [ ] `.env` 中 `AI_CALLBACK_TOKEN` 改为与 Java 一致（当前仍为占位符）
- [ ] wangqi 部署 RabbitMQ 并通知 ai-service 同事
- [ ] root 执行 `02-root-deploy.sh`
