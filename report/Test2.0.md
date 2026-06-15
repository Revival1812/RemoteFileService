下面按“本地推 GitHub -> 阿里云拉取 -> 配置 -> 启动 -> 验证”的顺序来做。

**一、推送前注意**
本地不要把真实密钥推到 GitHub。

确认 `.env` 不会被提交：

```
git status
```

如果看到 `.env` 在变更列表里，先取消跟踪：

```
git rm --cached .env
```

本次代码已经新增了 `.gitignore`，里面包含：

```
.env
```

你应该提交的是代码、迁移、Compose、README，不是 `.env`。

本地推送：

```
git add .
git commit -m "Add Dify workflow gateway"
git push
```

**二、服务器拉取前备份**
在阿里云服务器项目目录执行：

```
cd /你的项目目录
cp .env .env.backup.$(date +%Y%m%d%H%M%S)
docker compose ps
```

建议备份数据库：

```
docker compose exec postgres pg_dump -U postgres papers > backup_$(date +%Y%m%d%H%M%S).sql
```

如果你的 PostgreSQL 是外部托管库，就用对应的 `pg_dump` 方式备份。

**三、服务器拉取代码**
如果服务器没有本地改动：

```
git pull
```

如果服务器有改动，先看：

```
git status
```

不要直接 `reset --hard`，因为可能会误删服务器配置。一般服务器上只应该有 `.env` 这种本地配置，代码应从 Git 管理。

**四、更新服务器 .env**
你的旧 `.env` 可以继续用，但这次新增了 Workflow Gateway 配置。打开：

```
nano .env
```

补充这些变量：

```
ENABLE_WORKFLOW_GATEWAY=true
DIFY_WORKFLOW_API_BASE_URL=https://api.dify.ai/v1
DIFY_WORKFLOW_API_KEY=你的DifyWorkflowKey
WORKFLOW_GATEWAY_QUEUE=workflow_gateway
WORKFLOW_GATEWAY_MAX_RUNTIME_SECONDS=1800
WORKFLOW_GATEWAY_CONNECT_TIMEOUT_SECONDS=30
WORKFLOW_GATEWAY_SSE_READ_TIMEOUT_SECONDS=1800
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

注意：

- `DIFY_WORKFLOW_API_KEY` 是 Workflow 的 Key，不是原来的 Knowledge Base Key。
- 不需要给客户端暴露这个 Key。
- 原来的 `APP_API_KEYS` 和 `APP_ADMIN_API_KEYS` 继续保留。
- 原来的 `DIFY_KB_API_KEY`、`DIFY_PAPERS_DATASET_ID` 如果你还要同步知识库，也继续保留。
- `QUEUE_MODE=celery` 推荐保留，因为现在有两个 worker。

**五、启动/更新容器**
推荐先检查 Compose 是否能解析：

```
docker compose config
```

然后执行数据库迁移：

```
docker compose run --rm api alembic upgrade head
```

这次迁移只新增表：

```
workflow_jobs
```

不会改旧表。

然后构建并启动：

```
docker compose up -d --build
```

确认新服务起来：

```
docker compose ps
```

你应该看到至少这些服务：

```
api
worker
workflow_worker
postgres
redis
```

查看日志：

```
docker compose logs -f api
docker compose logs -f worker
docker compose logs -f workflow_worker
```

**六、端口和安全组**
对公网来说，只需要开放：

```
80
443
```

如果你临时直接用公网 IP 测试 API，则需要开放：

```
8000
```

不建议公网开放：

```
5432
6379
```

也就是说，PostgreSQL 和 Redis 只给容器内部使用，不要在阿里云安全组里开放它们。

如果你用 Nginx，公网访问路径应是：

```
http://你的公网IP/v1/workflow-jobs/arxiv
```

或 HTTPS：

```
https://你的域名/v1/workflow-jobs/arxiv
```

不需要为 `workflow_worker` 新增公网端口。

**七、基础验证命令**
先验证 API 活着：

```
curl http://182.92.109.116:80/healthz
```

预期：

```
{"status":"ok"}
```

![屏幕截图 2026-06-15 205237](images\屏幕截图 2026-06-15 205237.png)

验证数据库 ready：

```
curl http://182.92.109.116:80/readyz
```

预期：

```
{"status":"ready"}
```

![屏幕截图 2026-06-15 205256](images\屏幕截图 2026-06-15 205256.png)

验证 Workflow Gateway 管理状态：

```
curl http://182.92.109.116:80/v1/admin/workflow-gateway/status \
  -H "Authorization: Bearer E6n_0wW7Dg7N79eG3kY-tBCbqG4ksoxDWKc7DYKf7NA"
```

重点看：

```
{
  "enabled": true,
  "queue_name": "workflow_gateway",
  "postgres_configured": true,
  "redis_configured": true
}
```

![屏幕截图 2026-06-15 205615](images\屏幕截图 2026-06-15 205615.png)

**八、Apifox 验证：arXiv 长工作流**
Apifox 新建请求：

```
POST http://182.92.109.116:80/v1/workflow-jobs/arxiv
```

Headers：

```
Authorization: Bearer 0F8y65kzFbvfVqPye3ZqFDzo3A5Kft9u4IF-gLP35gI
Content-Type: application/json
Idempotency-Key: arxiv-2602-11929-test-001
```

Body JSON：

```
{
  "source_type": "arxiv",
  "arxiv_id": "2602.11929",
  "analysis_id": "apifox-arxiv-test-001",
  "action": "analyze_arxiv",
  "user_query": "请完整解析这篇论文",
  "user_level": "研究生或研究人员",
  "force_accept": false,
  "allow_ingestion": false,
  "parser_mode": "auto",
  "analysis_depth": "full",
  "owner_id": "user-001",
  "access_scope": "private"
}
```

预期 HTTP：

```
202 Accepted
```

预期响应：

```
{
  "job_id": "wjob_xxx",
  "status": "queued",
  "status_url": "/v1/workflow-jobs/wjob_xxx",
  "result_url": "/v1/workflow-jobs/wjob_xxx/result"
}
```

记录 `job_id`。

![屏幕截图 2026-06-15 210023](images\屏幕截图 2026-06-15 210023.png)

**九、Apifox 查询状态**
新建请求：

```
GET http://182.92.109.116:80/v1/workflow-jobs/<job_id>
```

Headers：

```
Authorization: Bearer 0F8y65kzFbvfVqPye3ZqFDzo3A5Kft9u4IF-gLP35gI
X-Owner-Id: user-001
```

可能状态：

```
queued
uploading
starting
running
reconnecting
succeeded
failed
cancelled
```

如果正在跑，正常会看到：

```
{
  "status": "running",
  "current_node_id": "...",
  "current_node_title": "...",
  "event_count": 33
}
```

![屏幕截图 2026-06-15 210243](images\屏幕截图 2026-06-15 210243.png)

**十、Apifox 查询结果**
摘要结果：

```
GET http://182.92.109.116:80/v1/workflow-jobs/<job_id>/result?view=summary
```

Headers：

```
Authorization: Bearer 0F8y65kzFbvfVqPye3ZqFDzo3A5Kft9u4IF-gLP35gI
X-Owner-Id: user-001
```

如果任务还没完成，预期：

```
202
```

![屏幕截图 2026-06-15 210403](images\屏幕截图 2026-06-15 210403.png)

如果成功，预期：

```
200
```

![屏幕截图 2026-06-15 211425](images\屏幕截图 2026-06-15 211425.png)

完整结果：

```
GET http://182.92.109.116:80/v1/workflow-jobs/<job_id>/result?view=full
```

![屏幕截图 2026-06-15 211930](images\屏幕截图 2026-06-15 211930.png)

**十一、Apifox 验证上传 PDF**
新建请求：

```
POST http://182.92.109.116:80/v1/workflow-jobs/upload
```

Headers：

```
Authorization: Bearer 0F8y65kzFbvfVqPye3ZqFDzo3A5Kft9u4IF-gLP35gI
Idempotency-Key: upload-test-001
```

Body 选择 `form-data`：

| 字段              | 类型 | 示例                     |
| ----------------- | ---- | ------------------------ |
| `paper_file`      | File | 选择一个 PDF             |
| `analysis_id`     | Text | `apifox-upload-test-001` |
| `action`          | Text | `new_upload`             |
| `user_query`      | Text | `请完整解析这篇论文`     |
| `user_level`      | Text | `研究生或研究人员`       |
| `force_accept`    | Text | `false`                  |
| `allow_ingestion` | Text | `false`                  |
| `parser_mode`     | Text | `auto`                   |
| `analysis_depth`  | Text | `full`                   |
| `owner_id`        | Text | `user-001`               |
| `access_scope`    | Text | `private`                |

可选补充图片：

| 字段                   | 类型 |
| ---------------------- | ---- |
| `supplementary_images` | File |
| `supplementary_images` | File |

可以传多个同名 `supplementary_images`。

预期：

```
202 Accepted
```

![屏幕截图 2026-06-16 001216](images\屏幕截图 2026-06-16 001216.png)

![屏幕截图 2026-06-16 001255](images\屏幕截图 2026-06-16 001255.png)

**十二、取消任务验证**
如果任务还在跑：

```
POST http://182.92.109.116:80/v1/workflow-jobs/<job_id>/cancel
```

Headers：

```
Authorization: Bearer 0F8y65kzFbvfVqPye3ZqFDzo3A5Kft9u4IF-gLP35gI
X-Owner-Id: user-001
```

预期：

```
{
  "job_id": "wjob_xxx",
  "status": "cancelled"
}
```

**十三、验证旧论文入库仍正常**
Apifox 或 curl：

```
curl -X POST http://182.92.109.116:80/v1/ingestion/jobs \
  -H "Authorization: Bearer 0F8y65kzFbvfVqPye3ZqFDzo3A5Kft9u4IF-gLP35gI" \
  -H "Content-Type: application/json" \
  -d '{
    "schema_version": "1.0",
    "paper_id": "arxiv:2406.09246",
    "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "profile": {"title": "Example Paper", "year": 2024},
    "knowledge_documents": [],
    "graph": {
      "paper_id": "arxiv:2406.09246",
      "nodes": [],
      "edges": []
    },
    "source_metadata": {
      "source_type": "upload",
      "arxiv_id": "2406.09246",
      "doi": "",
      "owner_id": "user-001",
      "access_scope": "private"
    }
  }'
```

预期：

```
202
```

第一次：

```
"dedup_status": "new"
```

重复提交：

```
"dedup_status": "existing"
```

**十四、最终确认所有服务可用**
在服务器执行：

```
docker compose ps
```

确认：

```
api              Up / healthy
worker           Up
workflow_worker  Up / healthy
postgres         Up / healthy
redis            Up / healthy
```

看 API 日志：

```
docker compose logs --tail=100 api
```

看长 workflow worker 日志：

```
docker compose logs --tail=100 workflow_worker
```

看原论文入库 worker 日志：

```
docker compose logs --tail=100 worker
```

验证 Redis 队列 worker 能响应：

```
docker compose exec workflow_worker celery -A app.workers.celery_app.celery_app inspect ping
```

验证数据库表存在：

```
docker compose exec postgres psql -U postgres -d papers -c "\dt"
```

应该能看到：

```
workflow_jobs
```

**十五、如果启动失败，优先检查这些**

1. `.env` 里有没有 `DIFY_WORKFLOW_API_KEY`。
2. `workflow_worker` 是否启动。
3. 是否执行了 `alembic upgrade head`。
4. 阿里云安全组是否开放 8000，或 Nginx 是否代理到 8000。
5. Redis/PostgreSQL 有没有误暴露到公网。
6. `docker compose logs -f workflow_worker` 里是否有 Dify API 鉴权错误。
7. 如果上传失败，检查 PDF 文件是否真的是 PDF，大小是否超过 `WORKFLOW_GATEWAY_MAX_UPLOAD_MB`。

最推荐的上线顺序是：

```
cd /你的项目目录
cp .env .env.backup.$(date +%Y%m%d%H%M%S)
git pull
nano .env
docker compose config
docker compose run --rm api alembic upgrade head
docker compose up -d --build
docker compose ps
curl http://182.92.109.116:80/healthz
curl http://182.92.109.116:80/v1/admin/workflow-gateway/status -H "Authorization: Bearer E6n_0wW7Dg7N79eG3kY-tBCbqG4ksoxDWKc7DYKf7NA"
```

这样能最大限度避免旧服务被破坏，同时确认新增的长工作流中转服务已经工作。
