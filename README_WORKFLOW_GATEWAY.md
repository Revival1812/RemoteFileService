# Dify Workflow Gateway 增量说明

本文档说明新增的 Dify 长工作流异步中转服务。它是在现有论文入库服务上增量扩展的独立模块，不替换原有 `/v1/ingestion/jobs`。

## 架构

```text
Dify 主 Chatflow
  -> POST /v1/workflow-jobs/arxiv 或 /v1/workflow-jobs/upload
  -> FastAPI 立即返回 202 + gateway job_id
  -> workflow_worker 消费 workflow_gateway 队列
  -> 调用 Dify /files/upload 和 /workflows/run
  -> 持续读取 streaming SSE
  -> PostgreSQL.workflow_jobs 持久化状态和结果
  -> 主 Chatflow 轮询 /v1/workflow-jobs/{job_id}
  -> 完成后读取 /v1/workflow-jobs/{job_id}/result
```

## 与现有 Ingestion 服务的关系

现有论文入库接口保持不变：

```text
POST /v1/ingestion/jobs
GET  /v1/ingestion/jobs/{job_id}
POST /v1/ingestion/jobs/{job_id}/retry
```

新增 Gateway 默认只保存 Dify Workflow 的输出结果，不自动调用现有 ingestion。只有未来显式开启并实现 `WORKFLOW_GATEWAY_AUTO_INGEST=true` 后，才应在 `paper_result` 已经包含完整 ingestion payload 时复用现有 service 层入库。

## 环境变量

```env
ENABLE_WORKFLOW_GATEWAY=true
DIFY_WORKFLOW_API_BASE_URL=https://api.dify.ai/v1
DIFY_WORKFLOW_API_KEY=
WORKFLOW_GATEWAY_QUEUE=workflow_gateway
WORKFLOW_GATEWAY_MAX_RUNTIME_SECONDS=1800
WORKFLOW_GATEWAY_CONNECT_TIMEOUT_SECONDS=30
WORKFLOW_GATEWAY_SSE_READ_TIMEOUT_SECONDS=1800
WORKFLOW_GATEWAY_START_MAX_ATTEMPTS=3
WORKFLOW_GATEWAY_RECONNECT_MAX_ATTEMPTS=10
WORKFLOW_GATEWAY_RECONNECT_BASE_DELAY_SECONDS=3
WORKFLOW_GATEWAY_UPLOAD_DIR=/var/lib/paper-service/workflow-gateway
WORKFLOW_GATEWAY_MAX_UPLOAD_MB=50
WORKFLOW_GATEWAY_RESULT_RETENTION_DAYS=30
WORKFLOW_GATEWAY_MAX_CONCURRENT_JOBS_PER_OWNER=3
WORKFLOW_GATEWAY_STORE_EVENTS=false
WORKFLOW_GATEWAY_AUTO_INGEST=false
WORKFLOW_GATEWAY_WORKER_CONCURRENCY=2
```

`DIFY_WORKFLOW_API_KEY` 独立于 Dify Knowledge 的 `DIFY_KB_API_KEY`。客户端永远不传 Dify Workflow Key。

## 本地启动

```bash
cp .env.example .env
docker compose up -d --build
```

查看服务：

```bash
docker compose ps
```

## 生产启动

```bash
docker compose -f docker-compose.prod.example.yml up -d --build
```

公网只需要继续通过 Nginx 反向代理 API 服务的 8000 端口，不需要新增公网端口。

## 数据库迁移

新增 migration：

```text
app/db/migrations/versions/0002_workflow_jobs.py
```

执行：

```bash
alembic upgrade head
```

或通过容器：

```bash
docker compose run --rm api alembic upgrade head
```

## 服务列表

| 服务 | 作用 | 端口 |
|---|---|---|
| `api` | FastAPI API | `8000:8000` |
| `worker` | 原有论文入库 Celery worker | 不暴露 |
| `workflow_worker` | 新增长工作流 Celery worker，只消费 `workflow_gateway` 队列 | 不暴露 |
| `postgres` | PostgreSQL | 本地 compose 映射 5432 |
| `redis` | Celery broker/backend | 本地 compose 映射 6379 |

生产环境不应把 PostgreSQL 和 Redis 暴露到公网。

## 健康检查

```bash
curl http://localhost:8000/healthz
curl http://localhost:8000/readyz
```

管理员状态：

```bash
curl http://localhost:8000/v1/admin/workflow-gateway/status \
  -H "Authorization: Bearer <APP_ADMIN_API_KEY>"
```

## arXiv 提交

```bash
curl -X POST http://localhost:8000/v1/workflow-jobs/arxiv \
  -H "Authorization: Bearer <APP_API_KEY>" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: arxiv-2602-11929-v1" \
  -d '{
    "source_type": "arxiv",
    "arxiv_id": "2602.11929",
    "analysis_id": "",
    "action": "analyze_arxiv",
    "user_query": "请完整解析这篇论文",
    "user_level": "研究生或研究人员",
    "force_accept": false,
    "allow_ingestion": false,
    "parser_mode": "auto",
    "analysis_depth": "full",
    "owner_id": "user-001",
    "access_scope": "private"
  }'
```

返回：

```json
{
  "job_id": "wjob_xxx",
  "status": "queued",
  "status_url": "/v1/workflow-jobs/wjob_xxx",
  "result_url": "/v1/workflow-jobs/wjob_xxx/result"
}
```

## PDF 提交

```bash
curl -X POST http://localhost:8000/v1/workflow-jobs/upload \
  -H "Authorization: Bearer <APP_API_KEY>" \
  -H "Idempotency-Key: upload-demo-v1" \
  -F "paper_file=@./paper.pdf;type=application/pdf" \
  -F "analysis_id=upload-demo" \
  -F "action=new_upload" \
  -F "user_query=请完整解析这篇论文" \
  -F "user_level=研究生或研究人员" \
  -F "force_accept=false" \
  -F "allow_ingestion=false" \
  -F "parser_mode=auto" \
  -F "analysis_depth=full" \
  -F "owner_id=user-001" \
  -F "access_scope=private"
```

补充图片可重复传：

```bash
-F "supplementary_images=@./figure1.png;type=image/png"
```

## 状态查询

```bash
curl http://localhost:8000/v1/workflow-jobs/<job_id> \
  -H "Authorization: Bearer <APP_API_KEY>" \
  -H "X-Owner-Id: user-001"
```

## 结果查询

摘要视图：

```bash
curl "http://localhost:8000/v1/workflow-jobs/<job_id>/result?view=summary" \
  -H "Authorization: Bearer <APP_API_KEY>" \
  -H "X-Owner-Id: user-001"
```

完整视图：

```bash
curl "http://localhost:8000/v1/workflow-jobs/<job_id>/result?view=full" \
  -H "Authorization: Bearer <APP_API_KEY>" \
  -H "X-Owner-Id: user-001"
```

状态规则：

| 任务状态 | `/result` HTTP |
|---|---|
| `queued/running/reconnecting` | 202 |
| `succeeded` | 200 |
| `failed/cancelled` | 409 |

## 取消任务

```bash
curl -X POST http://localhost:8000/v1/workflow-jobs/<job_id>/cancel \
  -H "Authorization: Bearer <APP_API_KEY>" \
  -H "X-Owner-Id: user-001"
```

如果任务已获得 Dify `task_id`，服务会调用 Dify stop task 接口；未启动任务会直接标记为 `cancelled`。

## 现有 Ingestion curl

```bash
curl -X POST http://localhost:8000/v1/ingestion/jobs \
  -H "Authorization: Bearer <APP_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "schema_version": "1.0",
    "paper_id": "arxiv:2406.09246",
    "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "profile": {"title": "Example Paper", "year": 2024},
    "knowledge_documents": [],
    "graph": {"paper_id": "arxiv:2406.09246", "nodes": [], "edges": []},
    "source_metadata": {
      "source_type": "upload",
      "owner_id": "user-001",
      "access_scope": "private"
    }
  }'
```

## Dify Chatflow 调用建议

主 Chatflow 不要直接等待长 Workflow。建议流程：

1. HTTP 节点提交 `/v1/workflow-jobs/arxiv` 或 `/v1/workflow-jobs/upload`。
2. 保存返回的 `job_id`。
3. 后续轮询 `/v1/workflow-jobs/{job_id}`。
4. 状态为 `succeeded` 后读取 `/v1/workflow-jobs/{job_id}/result?view=summary`。

## 日志查看

```bash
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f workflow_worker
```

## 队列隔离

原有论文入库 worker 仍使用默认 Celery 队列。新增 worker 只消费：

```text
workflow_gateway
```

命令：

```bash
celery -A app.workers.celery_app.celery_app worker \
  --queues=workflow_gateway \
  --concurrency=2 \
  --hostname=workflow-worker@%h
```

这样 10 到 30 分钟的 Dify SSE 长任务不会占满原有论文入库 worker。

## 备份与回滚

备份 PostgreSQL：

```bash
docker compose exec postgres pg_dump -U postgres papers > backup.sql
```

回滚本次数据库迁移：

```bash
alembic downgrade 0001_initial
```

代码回滚：

1. 停止服务：`docker compose down`
2. 回退代码到上一版本
3. 执行数据库 downgrade
4. 重新启动：`docker compose up -d --build`

## 常见故障

- `404 Workflow gateway disabled`：检查 `ENABLE_WORKFLOW_GATEWAY`。
- `401`：缺少或错误的 `Authorization: Bearer <APP_API_KEY>`。
- `403`：private 任务的 `X-Owner-Id` 与 owner 不匹配。
- `413`：上传文件超过 `WORKFLOW_GATEWAY_MAX_UPLOAD_MB`。
- `422`：文件类型、MIME、文件头或请求字段不合法。
- 任务长时间 `queued`：检查 `workflow_worker` 是否启动，以及是否消费 `workflow_gateway` 队列。
- 任务 `failed` 且缺少 API Key：检查 `DIFY_WORKFLOW_API_KEY`。
- SSE 中断：worker 会使用 Dify task/run 查询接口尝试恢复，不会在已有 `workflow_run_id` 后重复创建 run。
