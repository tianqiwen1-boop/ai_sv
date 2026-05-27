# dev 部署对接说明

## 配置来源

`/home/ai-service/ai-service-dev部署缺项答复.md`（wangqi 提供，2026-05-27）

## 关键参数（勿用旧值）

| 项 | 正确值 |
|----|--------|
| `RABBITMQ_HOST` | `bean-pattern-rabbitmq`（非 localhost / rabbitmq） |
| `CALLBACK_URL` | `http://bean-pattern-backend-dev:8082/api/ai/task/callback`（**8082**，非 8081） |
| `AI_QUEUE_NAME` | `ai.generate.request.dev` |
| Docker 网络 | `bean-dev-network` |
| `AI_S3_PREFIX` | `ai-results/dev/` |

## modelKey

文档中的 `seadance-2.0` = 即梦 `jimeng_t2i_v40`（`provider: jimeng`）。

## 部署

```bash
DOCKER_NETWORK=bean-dev-network bash /home/ai-service/bean-pattern-ai/deploy/02-root-deploy.sh
```
