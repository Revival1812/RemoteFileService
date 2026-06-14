### 第一阶段：核心注册与去重逻辑验证（纯本地纯净环境）

在这一阶段，我们**完全不连接** Dify 和 Neo4j，只验证 FastAPI 接口、PostgreSQL 数据库的存取以及核心的去重逻辑。

1. **环境准备与隔离配置**

   - 在代码根目录执行 `cp .env.example .env`。

   - 打开 `.env` 文件，确保以下三个关键变量处于隔离状态：

     Code snippet

     ```
     QUEUE_MODE=inline
     ENABLE_DIFY_SYNC=false
     ENABLE_NEO4J_SYNC=false
     APP_API_KEYS=dev-secret-change-me
     ```

   ![环境准备](C:\Users\Jesse\Desktop\ML\report\images\环境准备.png)

2. **启动本地容器组**

   - 在终端运行：`docker compose up --build`。
   - 观察终端日志，确认 PostgreSQL 初始化成功，Alembic 数据库迁移执行完毕（看到 `alembic upgrade head` 成功的字样），且 FastAPI 启动在 8000 端口。

   ![启动本地容器](C:\Users\Jesse\Desktop\ML\report\images\启动本地容器.png)

3. **连通性与接口文档检查**

   - 打开浏览器访问 `http://localhost:8000/healthz`，预期返回类似 `{"status": "ok"}`。

   ![连通性检查](C:\Users\Jesse\Desktop\ML\report\images\连通性检查.png)

   - 访问 `http://localhost:8000/docs` 查看自动生成的 Swagger UI 接口文档，熟悉你即将测试的路由。

   ![接口文档检查](C:\Users\Jesse\Desktop\ML\report\images\接口文档检查.png)

4. **验证新论文入库 (New)**

   - 打开 Apifox、Postman 或直接使用终端的 `curl`，向 `http://localhost:8000/v1/ingestion/jobs` 发送 README 中的示例 Payload。
   - 记得在 Headers 中添加 `Authorization: Bearer dev-secret-change-me`。
   - **预期结果：** HTTP 202，返回体中包含 `"dedup_status": "new"`。

   ![新论文入库](C:\Users\Jesse\Desktop\ML\report\images\新论文入库.png)

   ![新论文入库响应](C:\Users\Jesse\Desktop\ML\report\images\新论文入库响应.png)

5. **验证精确去重逻辑 (Existing)**

   - **原封不动**再次发送刚才的请求。
   - **预期结果：** HTTP 202，返回体中包含 `"dedup_status": "existing"`。

   ![精确去重响应](C:\Users\Jesse\Desktop\ML\report\images\精确去重响应.png)![精确去重逻辑](C:\Users\Jesse\Desktop\ML\report\images\精确去重逻辑.png)

   

6. **验证版本管理 (New Version)**

   - 修改 Payload 中的 `content_hash` 字段（随便改动几个字母），然后再次发送。
   - **预期结果：** HTTP 202，返![验证版本管理](C:\Users\Jesse\Desktop\ML\report\images\验证版本管理.png)回体中包含 `"dedup_status": "new_version"`。

   

### 第二阶段：外部依赖联调（接入 Dify 和 Neo4j）

本地逻辑跑通后，开始把第三方服务接进来。此时依然在本地运行服务，以便于实时查看容器日志排错。

1. **配置真实的外部凭据**

   - 准备好 Dify 的 API Key / Dataset ID，以及 Neo4j 的 URI 和账密。

   - 修改本地 `.env` 文件，开启同步：

     Code snippet

     ```
     ENABLE_DIFY_SYNC=true
     ENABLE_NEO4J_SYNC=true
     ```

   - 填入对应的真实凭据。

   ![配置真实的外部凭据](C:\Users\Jesse\Desktop\ML\report\images\配置真实的外部凭据.png)

2. **执行服务初始化 (Bootstrap)**

   - 新开一个终端窗口，借助正在运行的 Docker 容器执行验证脚本（或者直接在本地虚拟环境中执行）：

     Bash

     ```
     docker compose exec api python -m app.cli.bootstrap dify
     docker compose exec api python -m app.cli.bootstrap neo4j
     ```

   - **预期结果：** 脚本不报错，成功在 Dify 创建必要的 Metadata 字段，在 Neo4j 创建了节点唯一约束。

   ![dify验证脚本结果](C:\Users\Jesse\Desktop\ML\report\images\dify验证脚本结果.png)

   ![neo4j验证脚本结果](C:\Users\Jesse\Desktop\ML\report\images\neo4j验证脚本结果.png)

3. **测试异步任务与外部写入**

   - 将 `.env` 中的 `QUEUE_MODE` 改为 `celery`。重启容器：`docker compose restart`。
   - 再次向系统提交一篇带 `knowledge_documents` 和 `graph` 数据的全新论文 Payload。

   这里使用

   ```json
   {
       "schema_version": "1.0",
       "paper_id": "arxiv:2406.09246",
       "content_hash": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
       "profile": {"title": "Example Paper", "year": 2024},
       "knowledge_documents": [{
         "document_key": "arxiv:2406.09246:profile_v4",
         "name": "Example Paper - Paper Profile",
         "content": "# Example Paper Content has been updated again",
         "metadata": {
           "paper_id": "arxiv:2406.09246",
           "content_hash": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
           "content_type": "paper_profile"
         }
       }],
       "graph": {
         "paper_id": "arxiv:2406.09246",
         "nodes": [
           {
             "uid": "entity:ai_model:transformer",
             "name": "Transformer",
             "type": "Model Architecture",
             "aliases": ["Transformer Architecture", "Attention Model"],
             "description": "A deep learning architecture relying entirely on an attention mechanism to draw global dependencies between input and output."
           },
           {
             "uid": "entity:task:machine_translation",
             "name": "Machine Translation",
             "type": "Task",
             "aliases": ["MT", "Automated Translation"],
             "description": "The task of automatically converting text from one language to another."
           }
         ],
         "edges": [
           {
             "source_uid": "entity:ai_model:transformer",
             "target_uid": "entity:task:machine_translation",
             "relation": "USES",
             "paper_id": "arxiv:2406.09246",
             "evidence": "The Transformer model is predominantly used for machine translation tasks, setting new state-of-the-art results.",
             "section": "Introduction",
             "page": 1,
             "confidence": 0.95
           }
         ]
       },
       "source_metadata": {
         "source_type": "upload",
         "arxiv_id": "2406.09246",
         "doi": "",
         "owner_id": "owner-1",
         "access_scope": "private"
       }
   }
   ```

   - 记录下返回的 `job_id`。

4. **核对外部入库结果**

   - 调用查询接口：`GET http://localhost:8000/v1/ingestion/jobs/<job_id>`。
   - **预期结果：** 看到 `kb_status: completed` 和 `graph_status: completed`。
   - 登录你的 Dify 平台检查文档是否已入库且被切分，打开 Neo4j 浏览器执行 `MATCH (n) RETURN n LIMIT 10` 检查图谱节点是否生成。

### 第三阶段：公网部署与主线对接（生产环境）

当本地能够成功将数据推送到远程的 Dify 和 Neo4j 后，就可以把这个服务部署到公网，供 Dify Workflow 随时调用了。

1. **服务器部署**
   - 在你的云服务器（需要已安装 Docker）上克隆代码。
   - 生成生产环境的强随机秘钥（可使用 README 中的 `python -c "import secrets; print(secrets.token_urlsafe(32))"` 生成）。
   - 拷贝 `.env.example` 到 `.env`，填入所有真实的生产配置，**务必设置** `ENABLE_PUBLIC_DOCS=false` 以保护接口。
   - 执行 `docker compose -f docker-compose.prod.example.yml up -d` 启动服务。建议配置 Nginx 进行反向代理并挂载 HTTPS 证书。
2. **Dify Workflow 配置**
   - 回到你的 Dify 平台，找到论文处理 Workflow 的 HTTP 请求节点。
   - 将 URL 改为你的公网地址：`https://你的域名或IP/v1/ingestion/jobs`。
   - 在 Header 中配置 `Authorization: Bearer <你刚才生成的生产秘钥>`。
3. **端到端生产跑通**
   - 在 Dify 的起点上传一篇真实验证论文，触发整个工作流。
   - 登录服务器使用 `docker compose logs -f api worker` 查看服务接收请求和处理入库的日志，确认全链路闭环。