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

   ![更改queue_mode](C:\Users\Jesse\Desktop\ML\report\images\更改queue_mode.png)

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

   ![发送带知识和图关系的消息](C:\Users\Jesse\Desktop\ML\report\images\发送带知识和图关系的消息.png)

4. **核对外部入库结果**

   - 调用查询接口：`GET http://localhost:8000/v1/ingestion/jobs/<job_id>`。
   - **预期结果：** 看到 `kb_status: completed` 和 `graph_status: completed`。

   ![核对外部入库结果](C:\Users\Jesse\Desktop\ML\report\images\核对外部入库结果.png)

   - 登录你的 Dify 平台检查文档是否已入库且被切分，打开 Neo4j 浏览器执行 `MATCH (n) RETURN n LIMIT 10` 检查图谱节点是否生成。

   ![图谱节点生成](C:\Users\Jesse\Desktop\ML\report\images\图谱节点生成.png)

### 第三阶段：公网部署与主线对接（生产环境）

#### 第一阶段：阿里云服务器准备与基础环境搭建

在阿里云控制台完成基础云资源配置，这是所有部署的前提。

**1. 配置阿里云安全组（关键）** 买好 ECS 服务器（推荐使用 Ubuntu 22.04 或 24.04 系统）后，进入阿里云控制台的**安全组**设置，确保开放以下入方向端口：

- **22**：用于 SSH 远程登录。
- **80 和 443**：用于后续 Nginx 的 HTTP 和 HTTPS Web 服务访问。

**2. 登录服务器并安装环境** 通过 SSH 连接到你的阿里云 ECS，依次执行以下命令安装 Git 和 Docker 环境：

Bash

```
# 更新系统包
sudo apt update && sudo apt upgrade -y

# 安装 Git
sudo apt install git -y

# 使用官方脚本一键安装 Docker
curl -fsSL https://get.docker.com | bash

# 验证 Docker 和 Docker Compose 是否安装成功
docker --version
docker compose version
```

#### 第二阶段：拉取代码与生产环境配置

**1. 克隆代码仓库** 将你的项目拉取到服务器上：

Bash

```
git clone https://github.com/Revival1812/RemoteFileService.git
cd RemoteFileService
```

**2. 生成生产环境强随机秘钥** 在终端运行以下 Python 单行命令生成一个 32 位的强安全秘钥，**请务必将输出的字符串复制保存好**，这将在 Dify 配置中用到：

Bash

```
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

**3. 配置环境变量** 拷贝环境模板文件并进行编辑：

Bash

```
cp .env.example .env
nano .env
```

在 `.env` 文件中，你需要修改以下关键信息：

- 填入刚刚生成的 32 位强秘钥（通常对应 `API_AUTH_TOKEN` 或类似的鉴权字段）。
- 填入你真实的 Neo4j 和 Dify 的连接地址与凭证。
- **安全加固**：务必将 `ENABLE_PUBLIC_DOCS` 设置为 `false`，这样可以防止公网用户扫描和查看你的 Swagger API 文档。

保存并退出（在 nano 中按 `Ctrl+O` 回车保存，`Ctrl+X` 退出）。

#### 第三阶段：启动服务与 Nginx 反向代理配置

**1. 启动 Docker 服务** 使用生产环境的编排文件在后台启动服务：

Bash

```
docker compose -f docker-compose.prod.example.yml up -d
```

注意如果原命令不行，这里要替换为我仓库里的镜像，需要修改这个 docker-compose 文件：

**第一步：打开编排文件**

Bash

```
nano docker-compose.prod.example.yml
```

**第二步：修改镜像配置** 找到文件里所有的 `image: your-registry/...` 这一行（可能在 `api` 或 `worker` 服务下）。 在它的上方加上一行 `build: .`（意思是让 Docker 用当前目录的代码临时打包），并把 `image` 的名字改成一个本地专属的名字，比如：

**修改前（大概是这样）：**

YAML

```
services:
  api:
    image: your-registry/paper-ingestion-service:latest
    restart: always
    ...
```

**修改后（请照着改）：**

YAML

```
services:
  api:
    build: .                                      # 👈 新增这一行，告诉Docker自己打包
    image: remotefileservice-api:latest           # 👈 把 your-registry 改掉
    restart: always
    ...
```

*(注意：如果文件里还有 `worker` 节点也报同样的错，也做同样的修改，把 image 改成 `remotefileservice-worker:latest` 并加上 `build: .`)*

保存并退出（按 `Ctrl+O` 回车保存，按 `Ctrl+X` 退出）。

**第三步：带上 `--build` 参数重新启动** 这次我们要命令 Docker 先构建镜像再启动，执行以下命令：

Bash

```
docker compose -f docker-compose.prod.example.yml up -d --build
```

接下来你就会看到 Docker 开始一层层地拉取 Python 环境并安装依赖。等它构建完成后，你的服务就会顺利地在本地跑起来了！

你可以通过 `docker ps` 检查容器是否正常运行，并记下 API 容器暴露在宿主机的端口（假设为 `8000`）。

**2. 安装并配置 Nginx** 为了挂载 HTTPS 证书并提供安全的公网访问，我们使用 Nginx 进行反向代理。

Bash

```
sudo apt install nginx -y
sudo nano /etc/nginx/sites-available/remotefileservice
```

写入以下基础代理配置（请将 `your_domain.com` 换成你解析到该服务器公网 IP 的域名，`8000` 换成你容器实际暴露的端口），我这里是182.92.109.116：

Nginx

```
server {
    listen 80;
    server_name your_domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

激活配置并重启 Nginx：

Bash

```
sudo ln -s /etc/nginx/sites-available/remotefileservice /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

在apifox里进行测试有结果如下：

![公网IP支持外部数据库录入](C:\Users\Jesse\Desktop\ML\report\images\公网IP支持外部数据库录入.png)

#### 第四阶段：Dify Workflow 配置与端到端测试

**1. 修改 Dify 工作流节点** 回到你的 Dify 平台，打开“论文处理 Workflow”的 HTTP 请求节点进行修改：

- **URL**：修改为你的生产环境公网地址，例如 `https://your_domain.com/v1/ingestion/jobs`。
- **Header**：新增或修改请求头进行鉴权，填入 `Authorization: Bearer <你刚才在服务器生成的32位生产秘钥>`。

**2. 跑通全链路闭环**

- 在 Dify 的工作流起点，上传一篇真实的验证论文并执行触发。
- 回到阿里云服务器的终端，使用以下命令实时滚动查看日志：

Bash

```
docker compose -f docker-compose.prod.example.yml logs -f api worker
```

如果在终端日志中看到接收到了 Dify 的请求，并且 Worker 正常完成了论文解析与 Neo4j 的入库操作，同时 Dify 端节点返回成功状态，这就说明你的服务已经在公网完美闭环了。