# bean-pattern-ai 完整部署与交接文档

> **文档用途**：供其他 AI / 运维人员在不依赖原对话上下文的情况下，将 **`bean-pattern-ai`**（拼豆 AI 图生图 Worker）部署到 Linux 服务器并完成与 Java 后端的联调。  
> **服务器目录**：`/home/ai-service/bean-pattern-ai`（Linux 用户名 `ai-service` 仅作登录账号，与项目名不同）。  
> **项目归属**：拼豆魔法屋 — AI 一键生成链路中的 Python 异步图片生成服务。  
> **版本**：V1.0 | 日期：2026-05-26

---

## 1. 项目是什么

**bean-pattern-ai**（仓库内 Python 包仍为 `app/`）是一个 **独立 Python 守护进程**，职责单一：

1. 从 **RabbitMQ** 队列 `ai.generate.request` 消费任务消息  
2. 调用 **火山引擎即梦** 图片生成 4.0（`jimeng_t2i_v40`）做 **图生图**  
3. 将生成结果转为 **PNG**，上传到 **腾讯云 COS**（S3-compatible）  
4. 通过 HTTP **回调 Java 后端**，更新任务状态  

**不负责**：用户鉴权、扣减次数、任务入库、管理后台、小程序接口。这些由 **Java 后端** 完成。

---

## 2. 系统架构

```
小程序 → Java Backend → MySQL
              ↓
         RabbitMQ (ai.generate.request)
              ↓
         Python ai-service
              ↓
    即梦 API (jimeng_t2i_v40)
              ↓
         腾讯云 COS
              ↓
    HTTP 回调 Java (POST /api/ai/task/callback)
```

### 职责划分

| 模块 | 职责 |
|------|------|
| 小程序 | 上传原图、提交生成、轮询任务 |
| Java 后端 | 鉴权、扣次数、创建任务、投递 MQ、接收回调、更新 DB |
| RabbitMQ | 异步分发；队列/exchange 由 **Java 侧声明** |
| **ai-service** | 消费 MQ、调即梦、上传 COS、回调 Java |
| 管理后台 | 配置 `promptTemplate`、`modelKey`（`jimeng-t2i-v40`） |

---

## 3. 目录结构

```text
bean-pattern-ai/
├── app/
│   ├── main.py              # 入口：加载 .env → 读配置 → 启动 MQ 消费者
│   ├── config.py            # YAML + 环境变量 ${VAR} 替换与校验
│   ├── consumer.py          # RabbitMQ 消费（passive 声明队列，不存在则 fail-fast）
│   ├── handler.py           # 单条消息处理主流程
│   ├── generator.py         # 按 modelKey 路由到 provider
│   ├── providers/
│   │   └── jimeng.py        # 即梦 jimeng_t2i_v40 适配器
│   ├── storage.py           # COS/S3 上传 PNG
│   ├── callback.py          # 回调 Java 后端
│   ├── prompt.py            # promptTemplate + userPrompt 拼接
│   ├── models.py            # Pydantic 消息/回调模型
│   ├── errors.py            # 业务异常
│   ├── retry.py             # 内部有限重试
│   └── logging_config.py
├── config/
│   ├── config.example.yaml  # 配置模板（提交仓库）
│   └── config.yaml          # 实际配置（勿提交密钥，可用 example 复制）
├── tests/
│   └── test_core.py         # 单元测试
├── Dockerfile
├── requirements.txt
├── .env.example             # 环境变量模板
├── .env                     # 实际密钥（gitignore，部署时创建）
├── README.md
└── DEPLOYMENT.md            # 本文档
```

---

## 4. 端到端业务流程

### 4.1 Java 侧（已实现，本服务不修改）

1. 小程序 `POST /api/ai/generate`  
2. Java 扣减 AI 次数，创建任务 `PENDING`  
3. 查询风格表得到 `promptTemplate`、`modelKey`  
4. 投递 RabbitMQ 消息  
5. 小程序轮询 `GET /api/ai/task/{taskId}`  

### 4.2 ai-service 单条消息处理

```
收到 MQ 消息
  → 解析 JSON（失败：打日志 + ack，不回调）
  → 校验 taskId、imageUrl
  → 回调 Java：status=PROCESSING（aiImageUrl/errorMessage 均为 null）
  → 拼接 prompt = promptTemplate + " " + userPrompt（userPrompt 空则只用 template）
  → 即梦 submit（image_urls=[imageUrl]）→ 轮询直到 done
  → 下载结果图 URL → Pillow 转 PNG
  → 上传 COS：ai-results/{yyyy}/{MM}/{dd}/{taskId}.png
  → 回调 Java：status=SUCCESS，aiImageUrl=公开 URL
  → ack 消息
```

任一步业务失败 → 回调 `FAILED`（带 `errorMessage`）→ **ack**（避免前端无限轮询）。

### 4.3 任务状态机（与 Java 约定）

| status | aiImageUrl | errorMessage | Java 行为 |
|--------|------------|--------------|-----------|
| `PROCESSING` | `null` | `null` | 只更新 status、updatedAt |
| `SUCCESS` | **必填** | `null` | 写完成时间 |
| `FAILED` | `null` | **必填** | 写完成时间 |

终态 `SUCCESS`/`FAILED` 后重复回调会被 Java **忽略**。

---

## 5. 接口契约（必须严格遵守）

### 5.1 RabbitMQ 消息（Java → ai-service）

- **队列名**：`ai.generate.request`（默认，可环境变量覆盖）  
- **格式**：JSON，**camelCase**  
- **序列化**：Java `Jackson2JsonMessageConverter`  

```json
{
  "taskId": "AI1715234567890123456",
  "imageUrl": "https://example.com/input.png",
  "userPrompt": "用户补充说明，可为空",
  "style": "Q版",
  "promptTemplate": "管理后台配置的固定提示词，必填",
  "modelKey": "jimeng-t2i-v40",
  "createdAt": "2026-05-25 12:00:00"
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| taskId | 是 | Java 任务 ID |
| imageUrl | 是 | 公网可访问的原图 URL，即梦直接拉取 |
| userPrompt | 否 | 用户补充词 |
| style | 是 | 仅日志，不参与 prompt 拼接 |
| promptTemplate | 是（业务） | 风格固定提示词；空则 FAILED |
| modelKey | 否 | 空则用默认 `jimeng-t2i-v40` |
| createdAt | 否 | `yyyy-MM-dd HH:mm:ss`，Asia/Shanghai |

### 5.2 HTTP 回调（ai-service → Java）

- **URL**：环境变量 `CALLBACK_URL`  
  - Docker 同网：`http://backend:8081/api/ai/task/callback`  
  - 公网/内网 API：按实际 Java 地址配置  
- **Method**：`POST`  
- **Header**：`X-AI-Service-Token: ${AI_CALLBACK_TOKEN}`（与 Java **必须一致**）  
- **Content-Type**：`application/json`  

**PROCESSING 示例：**

```json
{
  "taskId": "AI1715234567890123456",
  "status": "PROCESSING",
  "aiImageUrl": null,
  "errorMessage": null
}
```

**SUCCESS 示例：**

```json
{
  "taskId": "AI1715234567890123456",
  "status": "SUCCESS",
  "aiImageUrl": "https://bucket.cos.region.myqcloud.com/ai-results/2026/05/26/AI1715234567890123456.png",
  "errorMessage": null
}
```

**FAILED 示例：**

```json
{
  "taskId": "AI1715234567890123456",
  "status": "FAILED",
  "aiImageUrl": null,
  "errorMessage": "即梦任务超时"
}
```

**回调成功判定**：HTTP 2xx 且响应 JSON 中 `code == 0`（Java 成功时 `message` 为 `"ok"`）。

---

## 6. 即梦模型对接

| 项 | 值 |
|----|-----|
| 官方文档 | https://www.volcengine.com/docs/85621/1817045?lang=zh |
| req_key | `jimeng_t2i_v40` |
| modelKey | `jimeng-t2i-v40` |
| SDK | `volcengine` Python SDK |
| 鉴权环境变量 | `VOLC_ACCESS_KEY_ID`、`VOLC_SECRET_ACCESS_KEY` |
| API Host | `VOLC_VISUAL_HOST`（默认 `visual.volcengineapi.com`） |
| 调用方式 | 异步：`cv_sync2async_submit_task` → 轮询 `cv_sync2async_get_result` |
| 原图传递 | **方式 A**：`image_urls=[message.imageUrl]`，不先下载原图 |
| 输出 | 单张图；下载后 **统一转 PNG** 再上传 COS |
| 默认参数（config.extra，可调） | `scale=0.5`, `force_single=1`, `poll_interval_seconds=2`, `timeout_seconds=300` |
| width/height | **不传** |

---

## 7. 配置说明

### 7.1 配置文件

- 模板：`config/config.example.yaml`  
- 运行：`config/config.yaml`（从 example 复制）  
- 路径覆盖：`AI_SERVICE_CONFIG` 环境变量  

YAML 中 `${VAR}` 或 `${VAR:default}` 会在启动时从 **环境变量** 替换。

### 7.2 环境变量清单（.env）

从 `.env.example` 复制为 `.env` 并填写真实值：

```bash
# RabbitMQ（与 Java 同一集群）
RABBITMQ_HOST=rabbitmq          # Docker 服务名；裸机填 IP 或 localhost
RABBITMQ_PORT=5672
RABBITMQ_USERNAME=admin
RABBITMQ_PASSWORD=<向运维索取>
AI_QUEUE_NAME=ai.generate.request

# Java 回调
CALLBACK_URL=http://backend:8081/api/ai/task/callback
AI_CALLBACK_TOKEN=<与 Java 后端完全相同>

# 火山即梦
VOLC_ACCESS_KEY_ID=<向运维索取>
VOLC_SECRET_ACCESS_KEY=<向运维索取>
VOLC_VISUAL_HOST=visual.volcengineapi.com

# 腾讯云 COS
S3_ENDPOINT=https://cos.ap-guangzhou.myqcloud.com
S3_BUCKET=<bucket 名>
S3_REGION=ap-guangzhou
S3_PUBLIC_BASE_URL=https://<bucket>.cos.ap-guangzhou.myqcloud.com
S3_PATH_STYLE_ACCESS=false
S3_URL_INCLUDE_BUCKET=false
S3_ACCESS_KEY=<向运维索取>
S3_SECRET_KEY=<向运维索取>

AI_SERVICE_CONFIG=config/config.yaml
```

**注意**：`python -m app.main` 启动时会自动 `load_dotenv` 加载项目根目录 `.env`。

### 7.3 COS 公开 URL 拼接规则

- `url_include_bucket=false`（默认）：`{S3_PUBLIC_BASE_URL}/{key}`  
- `url_include_bucket=true`：`{S3_PUBLIC_BASE_URL}/{bucket}/{key}`  

对象 key 格式：`ai-results/{yyyy}/{MM}/{dd}/{taskId}.png`

---

## 8. 部署前置条件

部署前确认：

| # | 条件 |
|---|------|
| 1 | RabbitMQ 已运行，且存在队列 **`ai.generate.request`**（由 Java 启动时声明） |
| 2 | Java 后端已部署且 `POST /api/ai/task/callback` 可访问 |
| 3 | `AI_CALLBACK_TOKEN` 与 Java 配置一致 |
| 4 | 服务器能访问：即梦 API、COS、消息中的 `imageUrl` |
| 5 | 管理后台风格 `modelKey` 配置为 **`jimeng-t2i-v40`** |
| 6 | 即梦 AK/SK、COS 密钥已申请 |

### 网络要求（Docker Compose 场景）

`ai-service` 容器需与 `rabbitmq`、`backend` 在 **同一 Docker network**，否则 `RABBITMQ_HOST=rabbitmq`、`CALLBACK_URL=http://backend:8081/...` 无法解析。

---

## 9. 部署步骤（推荐 Docker）

### 9.1 上传代码到服务器

```bash
# 示例目录
mkdir -p /home/ai-service/bean-pattern-ai
# 将项目目录上传到 /home/ai-service/bean-pattern-ai
```

服务器登录用户可为 `ai-service`（与项目名 `bean-pattern-ai` 无关）。

### 9.2 配置

```bash
cd /home/ai-service/bean-pattern-ai
cp config/config.example.yaml config/config.yaml
cp .env.example .env
vim .env   # 填入全部真实密钥与地址
```

### 9.3 构建镜像

```bash
docker build -t bean-pattern-ai:latest .
```

### 9.4 单独运行（测试）

```bash
docker run -d \
  --name bean-pattern-ai \
  --restart unless-stopped \
  --env-file .env \
  --network <与 backend/rabbitmq 相同的 network 名> \
  bean-pattern-ai:latest
```

### 9.5 查看日志

```bash
docker logs -f bean-pattern-ai
```

**启动成功标志：**

```text
启动 ai-service default_model=jimeng-t2i-v40
RabbitMQ 已连接 queue=ai.generate.request
```

### 9.6 并入现有 docker-compose（推荐）

在 Java 项目 `bean-pattern-backend/deploy/docker-compose.yml` 中增加（路径按实际 monorepo 调整）：

```yaml
  bean-pattern-ai:
    build:
      context: ../../bean-pattern-ai    # 或镜像: bean-pattern-ai:latest
    container_name: bean-pattern-ai
    restart: unless-stopped
    depends_on:
      - rabbitmq
      - backend
    env_file:
      - ../../bean-pattern-ai/.env     # 或使用 environment 逐项注入
    networks:
      - default                   # 与 backend、rabbitmq 相同
```

然后：

```bash
docker compose up -d bean-pattern-ai
```

---

## 10. 裸机部署（可选）

```bash
cd /home/ai-service/bean-pattern-ai
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp config/config.example.yaml config/config.yaml
cp .env.example .env
# 编辑 .env；RABBITMQ_HOST 改为实际 IP

# 前台测试
python -m app.main

# 后台运行（示例）
nohup python -m app.main >> /var/log/ai-service.log 2>&1 &
```

**CentOS 注意**：`requirements.txt` 中 `volcengine>=1.0.221`，勿使用 `1.0.180`（会导致 pycryptodome 编译失败）。

---

## 11. 联调与验收

### 11.1 单元测试（部署前可选）

```bash
cd /home/ai-service/bean-pattern-ai
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

### 11.2 端到端验收清单

| # | 步骤 | 期望 |
|---|------|------|
| 1 | 小程序提交 AI 生成 | Java 任务 `PENDING` |
| 2 | ai-service 消费消息 | 日志出现 `开始处理 taskId=...` |
| 3 | 回调 PROCESSING | Java 任务变 `PROCESSING` |
| 4 | 即梦生成完成 | 日志 `即梦任务已提交`、`处理成功` |
| 5 | 回调 SUCCESS | Java 任务 `SUCCESS`，有 `aiImageUrl` |
| 6 | 小程序轮询 | 进入结果页 |

### 11.3 测试用 imageUrl（开发环境）

```
https://bean-pattern-dev-1417861640.cos.ap-guangzhou.myqcloud.com/01897521-c779-40f6-8c72-7316296a71de.png
https://bean-pattern-dev-1417861640.cos.ap-guangzhou.myqcloud.com/0153f14d-80e3-4f71-9c5a-3cb13766e1cf.png
```

可向 MQ 手动投递一条 JSON 做冒烟（需 RabbitMQ 管理界面或 `rabbitmqadmin`）。

---

## 12. 错误处理与重试策略

| 场景 | 处理 |
|------|------|
| JSON 解析失败 | 打日志 + ack，**不回调** |
| 缺少 taskId | 打日志 + ack，不回调 |
| imageUrl 空 / modelKey 无效 / 即梦失败 / 上传失败 | 回调 **FAILED** + ack |
| PROCESSING 回调失败 | 打 error 日志，**继续生成** |
| SUCCESS/FAILED 回调失败 | 重试 3 次（间隔 3s），仍失败打 **critical** 日志 |
| 下载原图 / 上传 COS | 各最多 3 次，间隔 2s |
| 即梦 HTTP | 1 次请求，轮询最长 300s（可配置） |
| queue 不存在 | 启动 **fail-fast**（passive 声明） |
| MQ 连接断开 | 每 5s 重连 |

**第一版不做**：DLQ、HTTP `/health` 探活。

---

## 13. 日志与排查

- 日志输出到 **stdout**（Docker 用 `docker logs` 查看）  
- 关键字段：`taskId`、`modelKey`、`style`、耗时  
- CentOS 认证日志：`/var/log/secure`（SSH 问题）  

### 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| `配置错误: 缺少环境变量` | `.env` 未填或未加载 | 检查 `.env`，确认 `main.py` 同目录上级有 `.env` |
| `Connection refused :5672` | RabbitMQ 未启动或 HOST 错误 | 改 `RABBITMQ_HOST`，启动 RabbitMQ |
| `queue not found` | Java 未声明队列 | 先启动 Java 或手动声明队列 |
| 回调 401 | `AI_CALLBACK_TOKEN` 不一致 | 与 Java 对齐 |
| 即梦提交失败 code!=10000 | AK/SK 错误或余额 | 检查 `VOLC_*` |
| `Permission denied (publickey)` | SSH 与部署无关；检查服务器密钥 | — |

---

## 14. 安全要求

1. **禁止**将 `.env`、AK/SK、COS 密钥提交到 Git  
2. `AI_CALLBACK_TOKEN` 仅通过环境变量 / K8s Secret 注入  
3. 生产环境轮换已泄露的密钥  
4. 服务器防火墙：ai-service **无需对外暴露端口**（仅出站访问即梦/COS/回调 Java）  

---

## 15. 扩展说明（后续版本）

- 多模型：在 `config.yaml` 的 `models` 下新增 key，实现新 `provider`  
- 当前仅实现 `provider: jimeng`  
- 横向扩容：增加 ai-service 副本，`prefetch_count=1` 时每实例串行处理  

---

## 16. 给部署 AI 的执行清单（可直接按顺序执行）

```
[ ] 1. 将项目上传到服务器 /home/ai-service/bean-pattern-ai
[ ] 2. 复制 config.yaml、.env 并填写全部环境变量
[ ] 3. 确认 RabbitMQ、Java backend 已运行且同 Docker 网络
[ ] 4. 确认 AI_CALLBACK_TOKEN 与 Java 一致
[ ] 5. docker build -t bean-pattern-ai .
[ ] 6. docker run / compose up bean-pattern-ai
[ ] 7. docker logs 确认 RabbitMQ 已连接
[ ] 8. 触发一条 AI 生成任务，确认 PROCESSING → SUCCESS
[ ] 9. 小程序轮询到结果图 URL
```

---

## 17. 参考文件

| 文件 | 说明 |
|------|------|
| `README.md` | 简要说明 |
| `config/config.example.yaml` | 全量配置项 |
| `.env.example` | 环境变量模板 |
| `app/handler.py` | 主流程 |
| `app/providers/jimeng.py` | 即梦调用 |
| `proj3/jimeng_image.py` | 即梦联调参考脚本（同 AK/SK 与 API） |

---

*文档结束 — 如有接口变更，以 Java 后端与本文档第 5 节契约为准。*
