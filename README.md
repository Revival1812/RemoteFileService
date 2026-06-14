# Paper Registry and Async Ingestion Service

用于接收 Dify 论文处理 Workflow 输出，完成论文注册、精确去重、版本管理、异步入库状态管理，并可选同步到 Dify Knowledge 和 Neo4j。Dify、Neo4j、对象存储都未配置时，服务仍可完成 PostgreSQL 注册、去重、版本管理和查询。

## 本地启动

```bash
cp .env.example .env
docker compose up --build
```

访问：

```text
http://localhost:8000/healthz
http://localhost:8000/docs
```

## 环境变量

核心变量在 `.env.example` 中：

- `APP_API_KEYS`: 普通客户端 Key，逗号分隔。
- `APP_ADMIN_API_KEYS`: 管理员 Key，逗号分隔。
- `DATABASE_URL`: PostgreSQL 连接串。
- `REDIS_URL`: Redis 连接串。
- `QUEUE_MODE`: `inline` 或 `celery`。
- `MAX_REQUEST_BYTES`: 最大请求体大小。
- `ENABLE_PUBLIC_DOCS`: 是否公开 `/docs` 和 `/openapi.json`。
- `ENABLE_DIFY_SYNC`: 是否启用 Dify Knowledge 同步。
- `ENABLE_NEO4J_SYNC`: 是否启用 Neo4j 图谱同步。
- `ENABLE_EXTERNAL_RETRIEVAL_API`: 是否启用预留的 `/v1/retrieval`。

不要把 Dify、Neo4j、S3 或 API Key 提交到代码仓库。

## 数据库迁移

Compose 启动 API 时会自动执行：

```bash
alembic upgrade head
```

手动迁移：

```bash
make migrate
```

## API Key 生成

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

把结果写入 `.env`：

```env
APP_API_KEYS=generated-client-key
APP_ADMIN_API_KEYS=generated-admin-key
```

## 提交论文

```bash
curl -X POST http://localhost:8000/v1/ingestion/jobs \
  -H "Authorization: Bearer dev-secret-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "schema_version": "1.0",
    "paper_id": "arxiv:2406.09246",
    "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "profile": {"title": "Example Paper", "year": 2024},
    "knowledge_documents": [{
      "document_key": "arxiv:2406.09246:profile",
      "name": "Example Paper - Paper Profile",
      "content": "# Example Paper",
      "metadata": {
        "paper_id": "arxiv:2406.09246",
        "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "content_type": "paper_profile"
      }
    }],
    "graph": {"paper_id": "arxiv:2406.09246", "nodes": [], "edges": []},
    "source_metadata": {
      "source_type": "upload",
      "arxiv_id": "2406.09246",
      "doi": "",
      "owner_id": "owner-1",
      "access_scope": "private"
    }
  }'
```

重复执行同一请求会返回 `dedup_status=existing`，不会再次调用 Dify 或 Neo4j。

## Dify Workflow 配置

在 Dify Workflow 的 HTTP 节点中配置：

```text
INGESTION_ENDPOINT=https://example.com/v1/ingestion/jobs
INGESTION_TOKEN=<APP_API_KEY>
```

请求头：

```text
Authorization: Bearer <APP_API_KEY>
Content-Type: application/json
```

## 启用 Dify

`.env`：

```env
ENABLE_DIFY_SYNC=true
DIFY_API_BASE_URL=https://api.dify.ai/v1
DIFY_KB_API_KEY=...
DIFY_PAPERS_DATASET_ID=...
```

验证：

```bash
python -m app.cli.bootstrap dify
```

该命令验证 API 和 dataset，并返回服务需要的 Metadata 字段清单：`paper_id`、`content_hash`、`content_type`、`section_id`、`section_title`、`title`、`arxiv_id`、`doi`、`year`、`subdomain`、`origin`、`owner_id`、`access_scope`、`version`、`status`。

## 启用 Neo4j

`.env`：

```env
ENABLE_NEO4J_SYNC=true
NEO4J_URI=bolt://host:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=...
NEO4J_DATABASE=neo4j
```

验证并初始化约束：

```bash
python -m app.cli.bootstrap neo4j
```

验证节点和边：

```cypher
MATCH (n:Entity) RETURN n LIMIT 10;
MATCH ()-[r:RELATES_TO]->() RETURN r LIMIT 10;
```

## 查询 Job

```bash
curl http://localhost:8000/v1/ingestion/jobs/<job_id> \
  -H "Authorization: Bearer dev-secret-change-me"
```

状态包含：

- `status`: `received`、`syncing`、`completed`、`partial_success`、`failed`
- `dedup_status`: `new`、`existing`、`new_version`
- `kb_status`: Dify 状态
- `graph_status`: Neo4j 状态

Dify 成功但 Neo4j 失败时，Job 会是 `partial_success`。

## 验证 Dify 文档索引

```bash
curl http://localhost:8000/v1/papers/arxiv:2406.09246/documents \
  -H "Authorization: Bearer dev-secret-change-me"
```

查看 `remote_document_id`、`batch_id` 和 `indexing_status`。

## Docker 部署

本地：

```bash
docker compose up --build
```

生产参考：

```bash
docker compose -f docker-compose.prod.example.yml up -d
```

公网部署注意事项：

- 使用 HTTPS 反向代理。
- 设置强随机 `APP_API_KEYS` 和 `APP_ADMIN_API_KEYS`。
- 关闭公开文档：`ENABLE_PUBLIC_DOCS=false`。
- 使用托管 PostgreSQL/Redis 时，确保网络访问和连接池限制。
- 不要暴露 Redis、PostgreSQL、Neo4j 管理端口到公网。
- 对 Dify、Neo4j 和对象存储凭据使用平台 Secret 管理。

## 常用命令

```bash
make dev
make migrate
make test
make lint
make bootstrap
make down
```

## 故障排查

- `401`: 缺少或错误的 `Authorization: Bearer <API_KEY>`。
- `413`: 请求体超过 `MAX_REQUEST_BYTES`。
- `422`: `content_hash` 不是 64 位十六进制、`document_key` 重复、图边悬空、节点重复或 relation 不在白名单。
- `dedup_status=existing`: 精确重复，服务不会重复同步外部 Provider。
- `partial_success`: 某个 Provider 失败但注册已保留，可调用 `/v1/ingestion/jobs/{job_id}/retry`。
- Dify 失败不会回滚论文注册；检查 API Key、dataset id 和 Dify indexing 状态。
- Neo4j 失败不会回滚论文注册；检查 URI、用户名、密码、数据库名和约束初始化。

