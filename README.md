# ai-service

拼豆魔法屋 AI 图片生成服务。消费 RabbitMQ 任务，调用即梦 `jimeng_t2i_v40` 图生图，上传结果到 COS，并回调 Java 后端。

**完整部署与交接文档（给运维/其他 AI 使用）**：见 [DEPLOYMENT.md](./DEPLOYMENT.md)

## 功能

- 消费队列 `ai.generate.request`
- 根据 `modelKey` 路由模型（第一版：`jimeng-t2i-v40`）
- 图生图：将 MQ 消息中的 `imageUrl` 直接传给即梦
- 提示词：`promptTemplate + " " + userPrompt`
- 结果统一转 PNG 上传 COS
- 回调 Java：`PROCESSING` → `SUCCESS` / `FAILED`

## 目录结构

```text
bean-pattern-ai/
  app/
    main.py           # 入口
    config.py         # 配置加载
    consumer.py       # RabbitMQ 消费
    handler.py        # 消息处理
    generator.py      # 模型路由
    providers/jimeng.py
    storage.py        # COS 上传
    callback.py       # Java 回调
  config/
    config.example.yaml
  tests/
  Dockerfile
  requirements.txt
  .env.example
```

## 快速开始

### 1. 安装依赖

```bash
cd ai-service
pip install -r requirements.txt
```

### 2. 配置

```bash
copy config\config.example.yaml config\config.yaml
copy .env.example .env
# 编辑 .env 填入真实密钥
```

必填环境变量见 `.env.example`。

### 3. 启动

```bash
python -m app.main
```

启动前请确保 `.env` 中环境变量已填写。`python -m app.main` 会自动加载项目根目录的 `.env` 文件。

### 4. Docker

```bash
docker build -t bean-pattern-ai .
docker run --env-file .env bean-pattern-ai
```

## MQ 消息格式

```json
{
  "taskId": "AI1715234567890123456",
  "imageUrl": "https://example.com/input.png",
  "userPrompt": "补充说明",
  "style": "Q版",
  "promptTemplate": "固定风格提示词",
  "modelKey": "jimeng-t2i-v40",
  "createdAt": "2026-05-25 12:00:00"
}
```

## 回调格式

Header: `X-AI-Service-Token: ${AI_CALLBACK_TOKEN}`

```json
{
  "taskId": "AI1715234567890123456",
  "status": "PROCESSING",
  "aiImageUrl": null,
  "errorMessage": null
}
```

成功判定：HTTP 2xx 且响应 JSON 的 `code == 0`。

## 即梦对接

- 文档：[即梦AI-图片生成4.0-接口文档](https://www.volcengine.com/docs/85621/1817045?lang=zh)
- req_key: `jimeng_t2i_v40`
- 鉴权：`VOLC_ACCESS_KEY_ID` / `VOLC_SECRET_ACCESS_KEY`
- 轮询默认：2s 间隔，300s 超时（可在 config 调整）

## 测试

```bash
python -m unittest discover -s tests -v
```

## 与 Java 后端联调

1. Java 投递 MQ 消息，`modelKey=jimeng-t2i-v40`
2. 确保 `AI_CALLBACK_TOKEN` 与 Java 后端一致
3. ai-service 需能访问 `imageUrl` 与 `CALLBACK_URL`
