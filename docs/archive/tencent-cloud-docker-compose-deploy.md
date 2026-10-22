# 腾讯云 Docker Compose 生产部署文档

本文档按照“容器化 -> 生产配置 -> 部署到服务器 -> 验证”的顺序，说明如何把本项目部署到腾讯云 CVM。

> 适用目标：单台腾讯云 CVM，使用 Docker Compose 部署 Python/FastAPI 后端、ARQ Worker、PostgreSQL、Redis、Nginx 前端入口。
>
> 不建议同时部署 `java_backend`。当前生产 Compose 走的是 Python 后端，Java 后端是另一套实现，任务队列协议不同。

## 0. 项目部署结构

本项目生产环境建议采用下面的结构：

```text
Browser
  |
  | 80/443
  v
Nginx
  |-- /              -> React/Vite build 后的静态文件
  |-- /api/          -> FastAPI:39800
                       |
                       |-- PostgreSQL:5432
                       |-- Redis:6379
                       |-- ARQ Worker
                       |-- Tencent COS
```

生产环境只需要向公网开放：

- `80`: HTTP
- `443`: HTTPS
- `22`: SSH，仅允许管理员 IP

不要向公网开放：

- `39800`: FastAPI
- `5432`: PostgreSQL
- `6379`: Redis
- `39880`: 本地调试端口

## 1. 容器化

### 1.1 后端镜像

项目已有后端 Dockerfile：

```text
backend/Dockerfile
```

当前后端镜像会：

- 使用 `python:3.12-slim`
- 安装 `uv`
- 根据 `pyproject.toml` 和 `uv.lock` 安装依赖
- 启动 `uvicorn app.main:app`

建议生产环境做两点加固：

1. 固定 `uv` 镜像版本，不使用 `latest`。
2. 如果字体下载对 PPTX 导出质量很关键，移除 `|| true`，避免字体下载失败但构建继续通过。

当前：

```dockerfile
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN uv run python scripts/fetch_fonts.py || true
```

可调整为类似：

```dockerfile
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /usr/local/bin/uv
RUN uv run python scripts/fetch_fonts.py
```

> 版本号可以按你的实际锁定策略调整。关键点是生产镜像尽量不要依赖 `latest`。

### 1.2 前端镜像

当前 `docker-compose.prod.yml` 使用：

```yaml
volumes:
  - ./frontend/dist:/usr/share/nginx/html:ro
```

这要求服务器上已经手动执行过前端构建。为了让部署流程可重复，建议新增前端 Dockerfile：

```text
frontend/Dockerfile
```

内容：

```dockerfile
FROM node:22-alpine AS build

WORKDIR /src

COPY frontend/package*.json frontend/
RUN cd frontend && npm ci

COPY frontend frontend
COPY shared shared

RUN cd frontend && npm run build

FROM nginx:alpine

COPY --from=build /src/frontend/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

注意这里的构建上下文必须是项目根目录，而不是 `frontend/` 目录，因为前端构建会读取根目录下的 `shared/`。

### 1.3 Nginx 配置

生产环境建议调整 `nginx.conf`：

```nginx
server {
    listen 80;
    server_name ppt.example.com;

    root /usr/share/nginx/html;
    index index.html;

    client_max_body_size 10m;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://api:39800;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 1800s;
    }
}
```

需要替换：

```text
ppt.example.com
```

为你的正式域名。

说明：

- `client_max_body_size 10m` 要和后端 `MAX_UPLOAD_MB=10` 对齐。
- `proxy_buffering off` 保留，项目使用 SSE 推送生成进度。
- `proxy_read_timeout` 建议调大，避免长时间 AI 生成时代理层超时。

## 2. 生产配置

### 2.1 环境变量文件

生产环境建议使用两个环境文件：

```text
.env
backend/.env.production
```

根目录 `.env` 只放 Compose 插值需要的变量：

```env
POSTGRES_PASSWORD=请使用强随机密码
```

生成方式：

```bash
openssl rand -hex 32
```

后端生产环境变量放在：

```text
backend/.env.production
```

模板：

```env
APP_ENV=production

CORS_ORIGINS=["https://ppt.example.com"]

JWT_SECRET=请使用 openssl rand -hex 32 生成
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080

LLM_API_KEY=你的大模型密钥
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_THINKING_ENABLED=false
LLM_TIMEOUT_SECONDS=60

IMAGE_PROVIDER=bailian
IMAGE_API_KEY=你的生图密钥
IMAGE_BASE_URL=https://dashscope.aliyuncs.com/api/v1
IMAGE_MODEL=qwen-image-3.0
IMAGE_WORKSPACE_ID=
IMAGE_TIMEOUT_SECONDS=60

UNSPLASH_ACCESS_KEY=

MAX_IMAGE_MB=8
MAX_UPLOAD_MB=10

STORAGE_DRIVER=cos
COS_BUCKET=你的 COS Bucket
COS_REGION=ap-guangzhou
COS_SECRET_ID=你的腾讯云 SecretId
COS_SECRET_KEY=你的腾讯云 SecretKey
```

服务器上设置权限：

```bash
chmod 600 .env backend/.env.production
```

注意：

- 不要把 `.env`、`backend/.env.production` 提交到 Git。
- 不要继续使用本地开发的 `backend/.env` 部署生产。
- 如果本地 `.env` 中已经出现真实密钥，部署前建议在对应平台全部轮换。
- `POSTGRES_PASSWORD` 建议使用纯十六进制随机串，避免 `@`、`:`、`/`、`?` 等字符破坏数据库 URL。

### 2.2 存储驱动

生产环境建议使用腾讯云 COS：

```env
STORAGE_DRIVER=cos
```

原因：

- API 容器和 Worker 容器都需要访问同一批图片、上传文件和导出资源。
- 如果使用本地存储，容器重建或多容器之间可能出现文件不可见。
- COS 可以避免本地磁盘丢失和容器生命周期问题。

确保后端依赖中包含：

```toml
cos-python-sdk-v5
```

当前本地工作区已经在 `backend/pyproject.toml` 增加了该依赖，部署前要确保这项改动和 `uv.lock` 一起进入服务器。

### 2.3 数据库迁移

当前生产 Compose 没有自动执行 Alembic 迁移。建议新增一次性 `migrate` 服务。

推荐的 `docker-compose.prod.yml`：

```yaml
services:
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_USER: aippt
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
      POSTGRES_DB: aippt
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U aippt -d aippt"]
      interval: 5s
      timeout: 5s
      retries: 10

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 10

  migrate:
    build: ./backend
    restart: "no"
    env_file: ./backend/.env.production
    environment:
      DATABASE_URL: postgresql+asyncpg://aippt:${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}@postgres:5432/aippt
      REDIS_URL: redis://redis:6379/0
    volumes:
      - ./shared:/shared:ro
    command: ["uv", "run", "alembic", "upgrade", "head"]
    depends_on:
      postgres:
        condition: service_healthy

  api:
    build: ./backend
    restart: unless-stopped
    env_file: ./backend/.env.production
    environment:
      DATABASE_URL: postgresql+asyncpg://aippt:${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}@postgres:5432/aippt
      REDIS_URL: redis://redis:6379/0
    volumes:
      - ./shared:/shared:ro
    depends_on:
      migrate:
        condition: service_completed_successfully
      redis:
        condition: service_healthy

  worker:
    build: ./backend
    restart: unless-stopped
    command: ["uv", "run", "arq", "app.worker.settings.WorkerSettings"]
    env_file: ./backend/.env.production
    environment:
      DATABASE_URL: postgresql+asyncpg://aippt:${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}@postgres:5432/aippt
      REDIS_URL: redis://redis:6379/0
    volumes:
      - ./shared:/shared:ro
    depends_on:
      migrate:
        condition: service_completed_successfully
      redis:
        condition: service_healthy

  nginx:
    build:
      context: .
      dockerfile: frontend/Dockerfile
    restart: unless-stopped
    ports:
      - "80:80"
    depends_on:
      - api

volumes:
  postgres_data:
  redis_data:
```

说明：

- `postgres` 和 `redis` 不映射宿主机端口，只在 Compose 内网访问。
- `migrate` 只负责执行数据库迁移，成功后退出。
- `api` 和 `worker` 等待迁移成功后再启动。
- `nginx` 只暴露 `80`。
- 如果你用腾讯云负载均衡或 CDN 处理 HTTPS，容器内只监听 `80` 即可。

## 3. 部署到腾讯云服务器

### 3.1 准备服务器

建议服务器：

- Ubuntu 22.04 LTS 或 Ubuntu 24.04 LTS
- 2 核 4 GB 起步
- 磁盘建议 40 GB 起步
- 安装 Docker Engine 和 Docker Compose Plugin

检查 Docker：

```bash
docker version
docker compose version
```

### 3.2 配置腾讯云安全组

安全组入站规则建议：

| 协议 | 端口 | 来源 | 用途 |
| --- | --- | --- | --- |
| TCP | 22 | 你的固定公网 IP | SSH 登录 |
| TCP | 80 | 0.0.0.0/0 | HTTP |
| TCP | 443 | 0.0.0.0/0 | HTTPS |

不要开放：

| 端口 | 原因 |
| --- | --- |
| 39800 | FastAPI 应只由 Nginx 内网访问 |
| 5432 | PostgreSQL 不应暴露公网 |
| 6379 | Redis 不应暴露公网 |
| 39880 | 本地调试端口，不用于生产 |

### 3.3 配置域名

在 DNS 控制台添加：

```text
类型: A
主机记录: ppt
记录值: 你的 CVM 公网 IP
```

示例：

```text
ppt.example.com -> 1.2.3.4
```

然后把 `nginx.conf` 中的：

```nginx
server_name ppt.example.com;
```

改成你的域名。

### 3.4 拉取代码

在服务器上：

```bash
cd /opt
git clone <你的仓库地址> ai-ppt-generator
cd /opt/ai-ppt-generator
```

如果仓库是私有仓库，请先配置 SSH Key 或访问令牌。

### 3.5 创建生产环境变量

创建根目录 `.env`：

```bash
cat > .env <<'EOF'
POSTGRES_PASSWORD=替换成强随机密码
EOF
```

创建后端生产环境变量：

```bash
cp backend/.env.example backend/.env.production
```

然后编辑：

```bash
nano backend/.env.production
```

至少需要改：

- `APP_ENV=production`
- `CORS_ORIGINS`
- `JWT_SECRET`
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `IMAGE_PROVIDER`
- `IMAGE_API_KEY`
- `STORAGE_DRIVER=cos`
- `COS_BUCKET`
- `COS_REGION`
- `COS_SECRET_ID`
- `COS_SECRET_KEY`

设置权限：

```bash
chmod 600 .env backend/.env.production
```

### 3.6 构建并启动

先检查 Compose 展开后的配置：

```bash
docker compose --env-file .env -f docker-compose.prod.yml config
```

构建并启动：

```bash
docker compose --env-file .env -f docker-compose.prod.yml up -d --build
```

查看状态：

```bash
docker compose --env-file .env -f docker-compose.prod.yml ps
```

查看日志：

```bash
docker compose --env-file .env -f docker-compose.prod.yml logs -f api worker nginx
```

### 3.7 后续更新

更新代码：

```bash
cd /opt/ai-ppt-generator
git pull
docker compose --env-file .env -f docker-compose.prod.yml up -d --build
```

查看迁移是否成功：

```bash
docker compose --env-file .env -f docker-compose.prod.yml logs migrate
```

重启单个服务：

```bash
docker compose --env-file .env -f docker-compose.prod.yml restart api
docker compose --env-file .env -f docker-compose.prod.yml restart worker
docker compose --env-file .env -f docker-compose.prod.yml restart nginx
```

## 4. 验证

### 4.1 容器状态

```bash
docker compose --env-file .env -f docker-compose.prod.yml ps
```

期望：

- `postgres`: running / healthy
- `redis`: running / healthy
- `migrate`: exited 0
- `api`: running
- `worker`: running
- `nginx`: running

### 4.2 后端健康检查

```bash
curl http://127.0.0.1/api/v1/health
```

期望返回类似：

```json
{
  "status": "ok",
  "database": "ok",
  "redis": "ok"
}
```

注意：当前项目的 `/api/v1/health` 即使数据库或 Redis 不可用，也可能返回 HTTP 200，需要查看 `database` 和 `redis` 字段。

### 4.3 浏览器验证

访问：

```text
http://你的服务器公网 IP
```

或：

```text
https://你的域名
```

验证核心链路：

1. 打开首页。
2. 注册或登录。
3. 创建项目。
4. 输入主题生成大纲。
5. 确认大纲后生成页面。
6. 检查页面生成进度是否实时刷新。
7. 上传图片或文档。
8. 导出 PPTX。
9. 下载 PPTX 并打开确认内容可编辑。

### 4.4 Worker 验证

生成页面时观察 Worker 日志：

```bash
docker compose --env-file .env -f docker-compose.prod.yml logs -f worker
```

如果页面一直处于排队或生成中，优先检查：

- `worker` 是否启动。
- `REDIS_URL` 是否指向 `redis://redis:6379/0`。
- LLM 密钥是否有效。
- 供应商接口是否超时或限流。

### 4.5 COS 验证

上传图片或生成配图后，检查：

- COS Bucket 中是否出现 `media/` 前缀的对象。
- 页面中的图片是否能正常显示。
- 导出 PPTX 时图片是否能正常嵌入。

如果图片接口返回 500，可能是 COS 对象不存在时 SDK 异常未被转换为 `FileNotFoundError`。建议修复 `backend/app/storage/cos.py`：

```python
def load(self, key: str) -> bytes:
    try:
        response = self._client.get_object(Bucket=self.bucket, Key=key)
    except Exception as error:
        if "NoSuchKey" in str(error):
            raise FileNotFoundError(key) from error
        raise
    return response["Body"].get_raw_stream().read()
```

正式修复时建议捕获腾讯云 SDK 的明确异常类型，而不是只匹配字符串。

## 5. HTTPS 建议

有两种常见方式。

### 方案 A：腾讯云负载均衡或 CDN 终止 HTTPS

推荐生产使用。

特点：

- 证书托管在腾讯云。
- CVM 容器内仍只监听 `80`。
- Nginx 配置简单。

需要确认反代后请求头：

```nginx
proxy_set_header X-Forwarded-Proto $scheme;
```

### 方案 B：CVM Nginx 直接配置证书

需要：

- 申请证书。
- 将证书文件放到服务器安全目录。
- Compose 挂载证书。
- Nginx 增加 `443 ssl` server。

如果只是先跑通项目，可以先使用 HTTP，确认核心链路正常后再接 HTTPS。

## 6. 备份和恢复

### 6.1 PostgreSQL 备份

备份：

```bash
docker compose --env-file .env -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U aippt -d aippt > backup-$(date +%F).sql
```

恢复：

```bash
docker compose --env-file .env -f docker-compose.prod.yml exec -T postgres \
  psql -U aippt -d aippt < backup.sql
```

### 6.2 COS 备份

COS 本身提供对象持久化，但建议：

- 开启版本控制。
- 配置生命周期。
- 为生产 Bucket 使用独立子账号和最小权限策略。

### 6.3 Compose 数据卷

查看数据卷：

```bash
docker volume ls
```

注意不要随意执行：

```bash
docker compose down -v
```

该命令会删除 PostgreSQL 和 Redis 的数据卷。

## 7. 常见问题

### 7.1 页面打不开

检查：

```bash
docker compose --env-file .env -f docker-compose.prod.yml ps
docker compose --env-file .env -f docker-compose.prod.yml logs nginx
```

常见原因：

- 腾讯云安全组没有开放 `80`。
- DNS 没解析到 CVM 公网 IP。
- 前端镜像没有成功构建。
- `nginx.conf` 的 `server_name` 不匹配。

### 7.2 接口 502

检查：

```bash
docker compose --env-file .env -f docker-compose.prod.yml logs api
```

常见原因：

- `api` 容器启动失败。
- 数据库迁移失败。
- `DATABASE_URL` 配置错误。
- 后端依赖安装失败。

### 7.3 生成任务一直不动

检查：

```bash
docker compose --env-file .env -f docker-compose.prod.yml logs worker
docker compose --env-file .env -f docker-compose.prod.yml logs redis
```

常见原因：

- Worker 没启动。
- Redis 连接失败。
- LLM API Key 错误。
- 模型服务超时。
- 模型供应商限流。

### 7.4 上传文件失败

检查：

- `MAX_UPLOAD_MB`
- `nginx.conf` 的 `client_max_body_size`
- 后端日志

如果 Nginx 日志出现 `413 Request Entity Too Large`，说明 Nginx 上传限制太小。

### 7.5 图片不显示

检查：

- `STORAGE_DRIVER=cos`
- `COS_BUCKET`
- `COS_REGION`
- `COS_SECRET_ID`
- `COS_SECRET_KEY`
- COS Bucket 权限

本项目通过后端 `/api/v1/media/...` 读取 COS 对象，所以 Bucket 通常不需要公网公开。

### 7.6 数据库密码导致连接失败

如果 `POSTGRES_PASSWORD` 包含特殊字符，可能破坏：

```text
postgresql+asyncpg://aippt:${POSTGRES_PASSWORD}@postgres:5432/aippt
```

建议使用：

```bash
openssl rand -hex 32
```

生成只包含十六进制字符的密码。

## 8. 上线检查清单

上线前确认：

- [ ] 已新增 `frontend/Dockerfile`。
- [ ] 已更新 `docker-compose.prod.yml`。
- [ ] 已更新 `nginx.conf`。
- [ ] 已创建根目录 `.env`。
- [ ] 已创建 `backend/.env.production`。
- [ ] `backend/.env.production` 没有提交到 Git。
- [ ] `POSTGRES_PASSWORD` 是强随机值。
- [ ] `JWT_SECRET` 是强随机值。
- [ ] 已配置 LLM 密钥。
- [ ] 已配置图片服务密钥。
- [ ] 已配置 COS。
- [ ] 腾讯云安全组只开放必要端口。
- [ ] `docker compose config` 通过。
- [ ] `migrate` 容器退出码为 0。
- [ ] API、Worker、Nginx 均正常运行。
- [ ] 浏览器可访问页面。
- [ ] 注册、登录、生成、导出链路完成验证。
- [ ] 已配置数据库备份方案。

## 9. 参考资料

- Docker Compose restart 命令文档：https://docs.docker.com/reference/cli/docker/compose/restart/
- Docker Compose `depends_on` 条件示例：https://github.com/docker/compose/blob/main/pkg/e2e/testdata/TestUpWait/compose.yaml
- 腾讯云安全组配置说明：https://cloud.tencent.com/document/product/213/15377
- 腾讯云创建安全组：https://cloud.tencent.com/document/product/213/112613
