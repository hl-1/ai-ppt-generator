# AI PPT 部署手册（腾讯云 CVM + Docker Compose）

> 目标：在一台腾讯云 CVM 上，用 Docker Compose 跑起完整生产环境：Nginx（前端静态资源 + 反向代理）、FastAPI、ARQ Worker、PostgreSQL、Redis。
>
> 本手册中的文件内容、路径、端口、环境变量名均已对照当前代码逐条核对（`backend/app/core/paths.py`、`backend/app/core/config.py`、`backend/app/main.py`、`backend/app/api/v1/__init__.py`、`backend/app/worker/settings.py`、`backend/Dockerfile`、`backend/scripts/fetch_fonts.py`、`frontend/vite.config.ts`、`frontend/src/render/design.ts`、根 `docker-compose.prod.yml`、`nginx.conf`）。
>
> 只部署 Python 后端（`backend/`）。`java_backend/` 是同一套业务逻辑的另一套实现，两者任务队列协议不同，**不要同时部署**。

---

## 命令执行位置约定（先看这一节）

本手册的命令分两个执行环境，全文一致：

| 代号 | 环境 | 怎么进入 |
| --- | --- | --- |
| 【云】 | 腾讯云 CVM 服务器（Linux） | 本机 PowerShell 里 `ssh root@<公网IP>`；或腾讯云控制台 → 实例 → 「登录」的网页终端 |
| 【本】 | 你自己的电脑（Windows） | 本机 PowerShell |

一句话规则：**装 Docker、拉代码、跑容器、改服务器上的文件 —— 全在【云】；改代码、构建并推送镜像、往服务器传文件 —— 在【本】。**

补充说明：

- **本机不需要安装 Docker** 也能完成部署，除非你选择第 5 章方案 A（本地构建镜像推到 TCR）。
- 不要在本机 PowerShell 里执行 `sudo`、`systemctl`、`docker compose up` 这类命令：本机是 Windows，既没有 `sudo`/`systemctl`，也不应该跑这套容器。
- **【云】和【本】是两个独立的系统**。在 SSH 会话里敲的命令不会影响你的本机，反过来也一样。

登录服务器后先确认自己"在哪儿"：

```bash
# 【云】登录后自检
hostname        # 应显示 CVM 实例名，而不是你电脑的名字
whoami          # root 或 ubuntu
pwd             # 部署时应是 /opt/ai-ppt-generator
```

> 提示符是最直观的判断依据：`root@VM-0-12-ubuntu:~#` 说明你在服务器上；`PS C:\...>` 说明你在本机。

### 全手册命令位置速查

| 章节 | 命令 / 操作 | 位置 |
| --- | --- | --- |
| 1.1 | `fallocate` / `mkswap` / `swapon` / `free -h` | 【云】 |
| 1.2 | `curl -fsSL https://get.docker.com \| sudo sh`、`systemctl`、`usermod`、写 `/etc/docker/daemon.json`、`docker info` | 【云】 |
| 1.3 | 配置安全组入站规则 | 腾讯云控制台网页（不是终端） |
| 1.4 | 添加 DNS A 记录 | 域名 DNS 控制台网页 |
| 1.5 | 创建 COS Bucket、子账号密钥 | 腾讯云控制台网页 |
| 1.6 | 申请 LLM / 生图 / Unsplash 密钥 | 各家平台网页 |
| 2.1–2.3 | 新建 `frontend/Dockerfile`、`nginx.prod.conf`、生产版 `docker-compose.prod.yml` | 【本】改好再 `git push`；或直接在【云】用 `nano` 建（二选一） |
| 2.4 | 加固 `backend/Dockerfile` | 【本】（同上） |
| 2.5 | `openssl rand -hex 32` 生成 `POSTGRES_PASSWORD`、创建根 `.env` | 【云】 |
| 2.6 | `cp backend/.env.example backend/.env.production`、编辑、`chmod 600` | 【云】 |
| 3 | `git clone <仓库地址>` | 【云】 |
| 3 | `rsync ...` 从本机推代码 | 【本】 |
| 4 | `dc config` / `dc up -d --build` / `dc ps` / `dc logs` | 【云】 |
| 4.1 | `curl` 健康检查、`dc exec`、`dc logs` | 【云】（`dc exec` 是进容器内部，不需要单独登录容器） |
| 5 方案 A | `docker build` / `docker push` 到 TCR | 【本】（本机 `backend/fonts/` 已有字体） |
| 5 方案 B | `scp` 传字体到服务器 | 【本】 |
| 5 方案 C | 配置 Docker daemon 代理后构建 | 【云】（改 daemon 配置在服务器上） |
| 6 方案 A | CLB / CDN 上加证书 | 腾讯云控制台网页 |
| 6 方案 B | 下载证书在【本】，放到服务器 `certs/` 与 `dc up -d --build nginx` 在【云】 | 混合，见该章 |
| 7 | `git pull` / `dc ...` / `pg_dump` / `crontab` | 【云】 |

一句话记忆：**第 3 章的 `rsync`、第 5 章的 `docker build/push/scp` 在自己电脑上敲，其余全部在服务器上敲。**

### Windows 本机命令的写法差异

手册中【本】的命令按 Linux 习惯书写，你在 Windows PowerShell 上要按下表替换；标注【云】的命令不受影响（它们是在 Linux 服务器上执行的）。

| 手册写法 | Windows PowerShell 写法 |
| --- | --- |
| `ssh root@1.2.3.4` | 一样可用（Win10+ 自带 OpenSSH） |
| `scp backend/fonts/*.ttf root@ip:/path/` | `scp C:\softWare\project\AiPPT\ai-ppt-generator\backend\fonts\NotoSans-Regular.ttf root@ip:/opt/ai-ppt-generator/backend/fonts/`（多文件用反引号换行） |
| `rsync -avz --delete ./ root@ip:/opt/...` | Windows 没有 rsync：用 `scp -r`、`wsl rsync`，或干脆走 `git push` + 【云】`git pull` |
| `docker build ...`（第 5 章方案 A） | 需要本机装 Docker Desktop，并用 `-f` 指向 `backend/Dockerfile` |
| `openssl rand -hex 32` | 该命令在【云】执行，本机无需处理 |

---

## 0. 部署前必读：仓库现状与差距

仓库里现有的 `docker-compose.prod.yml` 和 `nginx.conf` **不能直接用于生产**，缺 4 样东西。这是本手册第 2 章要补的文件：

| 现状 | 问题 | 处理 |
| --- | --- | --- |
| 没有 `frontend/Dockerfile` | 现有 compose 把 `./frontend/dist` 挂进 nginx，要求服务器上先手工 `npm run build`（要装 Node） | 新增 `frontend/Dockerfile`，多阶段构建 |
| `docker-compose.prod.yml` 无 `migrate` 服务 | 首次部署**不会建表**，接口全 500 | 新增一次性 `migrate` 服务 |
| 同上，无 `restart` 策略、端口是 `39880`、读 `backend/.env` | 容器挂了不自恢复；端口对外；生产密钥与开发密钥混用 | 换成第 2.2 节的生产版 |
| `nginx.conf` 无 `client_max_body_size` | Nginx 默认上限 **1MB**，而 `MAX_UPLOAD_MB=10` → 上传文档/图片直接 **413** | 换第 2.3 节的生产版 `nginx.prod.conf` |

另外 3 个**必须知道**的运行机制（踩坑高发区）：

1. **`shared/` 必须挂在容器内 `/shared`。**
   `backend/app/core/paths.py` 里 `REPO_ROOT = parents[3]`，镜像内 `/app/app/core/paths.py` 往上 3 层就是 `/`，所以后端读的版式/主题目录是 `/shared`。`- ./shared:/shared:ro` 不是可选优化，缺了启动即报错。

2. **生产必须用 COS 存储，或显式改本地存储目录。**
   `config.py` 的默认本地目录是 `REPO_ROOT/backend/var/storage`，在容器里等于 `/backend/var/storage`，而 api 和 worker 是**两个独立容器**，各写各的目录 → worker 写的图片 api 读不到，且重建容器数据全丢。所以要么 `STORAGE_DRIVER=cos`，要么设 `STORAGE_LOCAL_DIR=/var/storage` 并给 api、worker 挂同一个卷。

3. **前端构建依赖 `shared/`。**
   `frontend/src/render/design.ts` 用 `import.meta.glob('../../../shared/layouts/*.json')` 把版式/主题**打进前端包**，所以前端镜像的构建上下文必须是**仓库根目录**，且要同时 COPY `frontend/` 和 `shared/`。

---

## 1. 前置准备

> 本章除 1.3–1.6（安全组、域名、COS、密钥）是**控制台网页操作**外，其余命令都在【云】服务器上执行。

### 1.1 服务器

| 项 | 建议 |
| --- | --- |
| 规格 | 2 核 4GB 起步（构建前端时 Vite + tsc 峰值约 1GB） |
| 磁盘 | 40GB 起步 |
| 系统 | Ubuntu 22.04 / 24.04 LTS |

如果只有 2 核 2GB，先加 2GB swap，否则 `npm ci` / `vite build` 容易 OOM：

```bash
# 【云】在云服务器上执行
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

### 1.2 安装 Docker Engine + Compose Plugin

```bash
# 【云】在云服务器上执行
# 官方脚本
curl -fsSL https://get.docker.com | sudo sh
sudo systemctl enable --now docker
sudo usermod -aG docker $USER   # 重新登录后生效，之后不用 sudo

docker version
docker compose version
```

国内机器若拉取镜像慢，配置镜像加速（腾讯云内网用户可直接用 `mirror.ccs.tencentyun.com`）：

```bash
# 【云】在云服务器上执行
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<'EOF'
{
  "registry-mirrors": ["https://mirror.ccs.tencentyun.com"],
  "log-driver": "json-file",
  "log-opts": { "max-size": "50m", "max-file": "3" }
}
EOF
sudo systemctl restart docker
```

> `log-opts` 建议加上：Worker 日志量不小，不限制会撑满磁盘。

### 1.3 安全组（入站规则）

| 协议 | 端口 | 来源 | 用途 |
| --- | --- | --- | --- |
| TCP | 22 | 你的固定公网 IP | SSH |
| TCP | 80 | 0.0.0.0/0 | HTTP |
| TCP | 443 | 0.0.0.0/0 | HTTPS（配了再用） |

**不要开放**：`39800`（FastAPI）、`5432`（Postgres）、`6379`（Redis）、`39880`（本地调试）。生产 compose 里这三个端口不映射到宿主机，只在 Compose 内网互通。

### 1.4 域名

DNS 添加 A 记录，例如 `ppt.example.com -> CVM 公网 IP`。没有域名也能先用 IP 跑通，但 `CORS_ORIGINS` 和 Nginx `server_name` 要对应调整。

### 1.5 腾讯云 COS（推荐）

1. 控制台创建 Bucket（如 `aippt-prod-125xxxxxxx`，地域 `ap-guangzhou`），**权限设为私有读写**。
2. 访问管理 → 新建子账号，只授予该 Bucket 的读写策略，拿到 `SecretId` / `SecretKey`。
3. 后端通过 `/api/v1/media/...` 代理读取 COS 对象，所以 Bucket **不需要**开公网访问。

### 1.6 模型与图片服务密钥

- LLM：DeepSeek（OpenAI 兼容），需要 `LLM_API_KEY`。
- 生图：`IMAGE_PROVIDER=openai`（OpenAI 兼容）或 `bailian`（百炼 DashScope），可与 LLM 用不同密钥；两者是互相降级关系，只配一个也能跑。
- 图库兜底：`UNSPLASH_ACCESS_KEY`（可选）。

---

## 2. 需要新增 / 修改的文件

以下 5 个文件在**本地仓库改好、提交、推上去**，服务器上 `git pull` 即可；也可以直接在服务器上创建。

### 2.1 新增 `frontend/Dockerfile`

```dockerfile
# 构建上下文必须是仓库根目录（见 docker-compose.prod.yml 的 context: .）
FROM node:22-alpine AS build

WORKDIR /src

# 先装依赖，利用缓存
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci

# shared/ 必须与 frontend/ 保持同级：design.ts 里 import.meta.glob('../../../shared/...')
COPY shared ./shared
COPY frontend ./frontend

RUN cd frontend && npm run build

FROM nginx:alpine

COPY --from=build /src/frontend/dist /usr/share/nginx/html
COPY nginx.prod.conf /etc/nginx/conf.d/default.conf
```

### 2.2 覆盖 `docker-compose.prod.yml`

```yaml
name: aippt

services:
  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: aippt
      # 冒号问号：变量缺失时 Compose 直接报错，避免用默认弱密码上线
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
      POSTGRES_DB: aippt
    volumes:
      - postgres_data:/var/lib/postgresql/data
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

  # 一次性服务：执行 Alembic 迁移，成功后退出，api/worker 等它成功再起
  migrate:
    build: ./backend
    restart: "no"
    env_file: ./backend/.env.production
    environment:
      DATABASE_URL: postgresql+asyncpg://aippt:${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}@postgres:5432/aippt
      REDIS_URL: redis://redis:6379/0
    volumes:
      - ./shared:/shared:ro
    # 直接用镜像里的 venv 可执行文件，避免 uv run 在运行期再做一次环境同步
    command: ["/app/.venv/bin/alembic", "upgrade", "head"]
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
      # 用 COS 时不需要下面两行；用本地存储时打开，并设 STORAGE_LOCAL_DIR=/var/storage
      # - storage_data:/var/storage
    command: ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "39800"]
    healthcheck:
      test: ["CMD", "/app/.venv/bin/python", "-c", "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:39800/api/v1/health',timeout=5).status==200 else 1)"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 20s
    depends_on:
      migrate:
        condition: service_completed_successfully
      redis:
        condition: service_healthy

  worker:
    build: ./backend
    restart: unless-stopped
    env_file: ./backend/.env.production
    environment:
      DATABASE_URL: postgresql+asyncpg://aippt:${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}@postgres:5432/aippt
      REDIS_URL: redis://redis:6379/0
    volumes:
      - ./shared:/shared:ro
      # - storage_data:/var/storage
    command: ["/app/.venv/bin/arq", "app.worker.settings.WorkerSettings"]
    depends_on:
      migrate:
        condition: service_completed_successfully
      redis:
        condition: service_healthy

  nginx:
    build:
      context: .                     # 必须是仓库根，前端要读 shared/
      dockerfile: frontend/Dockerfile
    restart: unless-stopped
    ports:
      - "80:80"
      # 配 HTTPS 后打开，并把证书挂进来
      # - "443:443"
    # volumes:
    #   - ./certs:/etc/nginx/certs:ro
    depends_on:
      - api

volumes:
  postgres_data:
  redis_data:
  # storage_data:
```

要点：

- `postgres` / `redis` **不映射宿主机端口**，只在 Compose 内网可达。
- `migrate` 每次 `up` 都会重跑一次（Alembic 幂等，无新迁移时输出 `No new upgrade operations` 级别信息后退出 0）。
- 三个后端服务共用一个镜像，`build` 写三遍只构建一次。

### 2.3 新增 `nginx.prod.conf`

```nginx
server {
    listen 80;
    server_name huanliyu.cn www.huanliyu.cn;   # 换成你的域名；用 IP 访问就写 _

    root /usr/share/nginx/html;
    index index.html;

    # 必须与 backend 的 MAX_UPLOAD_MB 对齐，Nginx 默认只有 1m
    client_max_body_size 10m;

    # 前端是 SPA，未知路径回落 index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Vite 产物带内容哈希，可长缓存
    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }

    location /api/ {
        proxy_pass http://api:39800;      # api 是 compose 服务名，走内网 DNS
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE 实时进度：必须关缓冲，否则进度会被攒着不发
        proxy_buffering off;
        proxy_cache off;
        # ARQ 单任务上限 15 分钟（worker/settings.py），读超时要放宽
        proxy_read_timeout 1800s;
        proxy_send_timeout 1800s;
    }
}
```

> 为什么另起 `nginx.prod.conf` 而不改 `nginx.conf`：`nginx.conf` 还被本地 `docker-compose.yml`（39880 端口）使用，分开更干净。前端 Dockerfile 里 COPY 的是 `nginx.prod.conf`。

### 2.4 后端 Dockerfile 的两点加固（可选但建议）

`backend/Dockerfile` 现状：

```dockerfile
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN uv run python scripts/fetch_fonts.py || true
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "39800"]
```

建议改成：

```dockerfile
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /usr/local/bin/uv   # 固定版本，别用 latest
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .
# 去掉 || true：字体下载失败就直接构建失败，而不是悄悄产出一个度量退化的镜像
RUN uv run python scripts/fetch_fonts.py

EXPOSE 39800
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "39800"]
```

原因：`uv run` 在运行期会检查并同步环境（本项目 `dev` 依赖组是默认组，可能去装 pytest/ruff），直接调 `.venv/bin/*` 更确定、也不需要运行期访问 PyPI。

### 2.5 根目录 `.env`（Compose 变量插值用）

```bash
# 【云】在云服务器上执行
openssl rand -hex 32      # 生成密码，必须是纯 hex
```

```env
POSTGRES_PASSWORD=刚才生成的64位hex
```

> 用 hex 是为了避免 `@ : / ?` 破坏 `postgresql+asyncpg://aippt:PASSWORD@postgres:5432/aippt` 这个 URL。

### 2.6 `backend/.env.production`

```bash
# 【云】在云服务器上执行
cp backend/.env.example backend/.env.production
openssl rand -hex 32      # JWT_SECRET
```

```env
APP_ENV=production

# 生产由 Nginx 同源代理 /api，前端不发跨域请求；仍建议写正式域名
CORS_ORIGINS=["https://huanliyu.cn","https://www.huanliyu.cn"]

JWT_SECRET=上一步生成的hex
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=10080

LLM_API_KEY=你的密钥
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
MAX_UPLOAD_MB=10          # 改动必须同步 nginx.prod.conf 的 client_max_body_size

STORAGE_DRIVER=cos
COS_BUCKET=aippt-prod-125xxxxxxx
COS_REGION=ap-guangzhou
COS_SECRET_ID=你的SecretId
COS_SECRET_KEY=你的SecretKey
```

注意：

- `DATABASE_URL` / `REDIS_URL` **不要写在这里**，由 compose 的 `environment` 注入成服务名（`postgres` / `redis`）。compose 的 `environment` 优先级高于 `env_file`。
- `CORS_ORIGINS` 必须是合法 JSON 数组（pydantic-settings 按 JSON 解析）。
- 若用本地存储：`STORAGE_DRIVER=local` + `STORAGE_LOCAL_DIR=/var/storage` + 打开 compose 里的 `storage_data` 卷（api、worker 两个服务都要）。
- 权限收紧：

```bash
chmod 600 .env backend/.env.production
```

`.gitignore` 已经忽略 `.env` / `.env.*`，不要用 `git add -f` 绕过。

---

## 3. 上传代码

```bash
# 【云】在云服务器上执行
sudo mkdir -p /opt && cd /opt
git clone <你的仓库地址> ai-ppt-generator
cd /opt/ai-ppt-generator
```

私有仓库先配 Deploy Key。**注意**：`docs/`、`backend/fonts/*`、`.env*` 都在 `.gitignore` 里，`git clone` 拿不到这些，属正常（字体见第 5 章，环境变量见第 2.5/2.6 节）。

没有 Git 通道时用 rsync 从本地推（排除依赖与产物）：

```bash
# 【本】在你自己的电脑（Windows PowerShell）上执行；本机传文件到服务器只有这里和第 5 章的 scp
rsync -avz --delete \
  --exclude '.git' --exclude 'node_modules' --exclude 'dist' \
  --exclude '.venv' --exclude 'target' --exclude '__pycache__' \
  --exclude 'backend/var' --exclude '.env' \
  ./ root@<公网IP>:/opt/ai-ppt-generator/
```

---

## 4. 首次部署

> 本章命令**全部在【云】服务器上执行**。前提：第 2 章的 3 个文件已经提交到仓库并在服务器上 `git pull` 到位（或已在服务器上创建）。

```bash
# 【云】以下命令都在云服务器上执行（先 ssh 登录）
cd /opt/ai-ppt-generator

# 常用命令别名（可选）：之后用 dc 代替长命令
alias dc='docker compose -f docker-compose.prod.yml'

# 1) 先校验 Compose 展开结果，能在这一步发现变量缺失/语法错误
dc config

# 2) 构建并启动（首次约 5-15 分钟：npm ci + vite build + uv sync）
dc up -d --build

# 3) 看状态（migrate 应是 Exited (0)）
dc ps

# 4) 跟随日志
dc logs -f api worker nginx
```

> 根目录 `.env` 会被 Compose 自动读取做变量插值，所以不必每次写 `--env-file`；写全写法是 `docker compose --env-file .env -f docker-compose.prod.yml ...`。

### 4.1 验证清单

```bash
# 【云】在云服务器上执行
# 容器状态：postgres/redis 应为 healthy，api/worker/nginx 为 Up，migrate 为 Exited (0)
dc ps

# 健康检查（走 Nginx 入口）
curl -s http://127.0.0.1/api/v1/health
# 期望 {"status":"ok","database":"ok","redis":"ok"}
```

> ⚠️ `/api/v1/health` **即使数据库或 Redis 挂了也返回 HTTP 200**（这是刻意设计，让前端能区分"服务挂了"和"服务在但依赖不可用"）。所以必须看 `database` / `redis` 字段的值，不能只看状态码。

```bash
# 【云】在云服务器上执行
# 确认迁移真的建了表
dc exec postgres psql -U aippt -d aippt -c '\dt'

# 确认字体在位（导出的文字溢出检测依赖它）
dc exec api ls -l /app/fonts
# 期望看到 NotoSans-Regular.ttf 与 NotoSansSC-Regular.otf，且体积不为 0

# 确认 shared 挂在正确位置
dc exec api ls /shared/layouts | head

# 确认 Worker 连上了 Redis
dc logs worker | tail -20
```

浏览器端到端走一遍：注册/登录 → 创建项目 → 输入主题生成大纲 → 确认大纲生成页面（**观察进度是否实时刷新，这验证 SSE 通路**）→ 上传一份 PDF/Word → 编辑页面 → 导出 PPTX → 下载后打开确认是可编辑对象而不是整页截图。

---

## 5. 字体问题（国内服务器必读）

> 本章方案 A、方案 B 的构建与 `scp` 在【本】执行，方案 C 与最后的验证在【云】执行。

`backend/scripts/fetch_fonts.py` 从 `raw.githubusercontent.com` 下载两个 Noto 字体，用于**字形级文字溢出检测**（`backend/app/domain/text_metrics.py`）。两个事实：

- `backend/fonts/*` 在 `.gitignore` 里，`git clone` 到服务器后字体目录是空的。
- 国内 CVM 构建时大概率连不上 `raw.githubusercontent.com`；如果 Dockerfile 里保留 `|| true`，构建会"成功"，但镜像里没有字体，运行时 `fonts_available()` 返回 False，文字占用退化为**估算**（`used_estimate=True`），导出前溢出判定会不准。**这是最容易被忽略的隐性降级。**

三种处理方式，按推荐度排序：

**方案 A（推荐）：本地构建镜像 → 推送腾讯云 TCR → 服务器只 pull**

本地仓库的 `backend/fonts/` 已经有字体文件，构建时脚本检测到已存在会直接跳过下载，镜像里字体是齐的。

```bash
# 【本】在你自己的电脑上执行（需本机装 Docker Desktop；本机 backend/fonts/ 已有字体）
# 本地
docker build -t ccr.ccs.tencentyun.com/<命名空间>/aippt-backend:v1 ./backend
docker push ccr.ccs.tencentyun.com/<命名空间>/aippt-backend:v1
# 服务器上把 compose 里的 build: ./backend 换成 image: ccr.ccs.tencentyun.com/<命名空间>/aippt-backend:v1
```

顺带也解决了服务器内存小、构建慢的问题。

**方案 B：先把字体传到服务器，再在服务器构建**

```bash
# 【本】在你自己的电脑上执行
# 本地
scp backend/fonts/NotoSans-Regular.ttf backend/fonts/NotoSansSC-Regular.otf \
    root@<公网IP>:/opt/ai-ppt-generator/backend/fonts/
# 服务器
# 【云】回到服务器上重建
dc up -d --build
```

`fetch_fonts.py` 对已存在的非空文件会跳过，所以不会再联网。

**方案 C：让构建走代理**

配置 Docker daemon 代理（`/etc/systemd/system/docker.service.d/proxy.conf`）后重启 docker，再构建。Docker 构建**不会**继承宿主的 shell 代理环境变量。

无论哪种方式，部署后都要执行第 4.1 节的 `dc exec api ls -l /app/fonts` 确认。

---

## 6. HTTPS

### 方案 A（推荐）：腾讯云 CLB / CDN 终止 HTTPS

证书托管在腾讯云，CVM 上容器仍只监听 80，Nginx 配置不用动。此时要保证回源请求头带 `X-Forwarded-Proto`（第 2.3 节已配置）。同时把 `CORS_ORIGINS` 写成 `https://` 的正式域名。

### 方案 B：Nginx 容器直接配 443

1. 在腾讯云 SSL 证书控制台申请免费证书，下载 **Nginx 格式**，放到服务器 `/opt/ai-ppt-generator/certs/`（`fullchain.pem` + `privkey.pem`）。
2. `docker-compose.prod.yml` 的 nginx 服务打开 `443:443` 和 `./certs:/etc/nginx/certs:ro`（见 2.2 节注释）。
3. `nginx.prod.conf` 增加：

```nginx
server {
    listen 80;
    server_name ppt.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    http2 on;
    server_name ppt.example.com;

    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:SSL:10m;

    root /usr/share/nginx/html;
    index index.html;
    client_max_body_size 10m;

    location / { try_files $uri $uri/ /index.html; }

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
        proxy_send_timeout 1800s;
    }
}
```

4. `dc up -d --build nginx` 重建，再改安全组放开 443。

如果只想先跑通，可以先纯 HTTP，确认业务链路正常后再接证书。

---

## 7. 日常运维

> 本章命令**全部在【云】服务器上执行**。

### 7.1 发版

```bash
# 【云】在云服务器上执行
cd /opt/ai-ppt-generator
git pull
dc up -d --build          # 有变更的服务会重建；migrate 会自动先跑
dc logs migrate           # 确认迁移成功
dc ps
```

只更新后端（前端没动）：

```bash
dc up -d --build api worker
```

### 7.2 常用命令

```bash
dc ps                       # 状态
dc logs -f api worker       # 日志
dc restart api              # 重启单个服务
dc exec api bash            # 进容器
dc down                     # 停止（保留数据卷）
dc up -d                    # 再次启动
```

⚠️ **永远不要**执行 `dc down -v`：会删掉 `postgres_data` / `redis_data` 卷，数据全丢。

### 7.3 回滚

```bash
git log --oneline -5
git checkout <上一个可用提交或tag>
dc up -d --build
```

数据库回滚要谨慎（Alembic 的 downgrade 可能丢列数据）：

```bash
dc run --rm migrate /app/.venv/bin/alembic down -1    # 先 backup
```

### 7.4 备份与恢复

```bash
# 【云】在云服务器上执行
# 备份
mkdir -p /opt/backup
dc exec -T postgres pg_dump -U aippt -d aippt | gzip > /opt/backup/aippt-$(date +%F).sql.gz

# 恢复
gunzip -c /opt/backup/aippt-2026-09-14.sql.gz | dc exec -T postgres psql -U aippt -d aippt
```

建议配 crontab 每天备份并异地存放：

```bash
0 3 * * * cd /opt/ai-ppt-generator && dc exec -T postgres pg_dump -U aippt -d aippt | gzip > /opt/backup/aippt-$(date +\%F).sql.gz
```

COS 侧：开启版本控制 + 生命周期规则，用独立子账号最小权限访问。

---

## 8. 排错速查

| 现象 | 优先检查 |
| --- | --- |
| 页面打不开 | 安全组 80 是否开放；`dc logs nginx`；DNS 是否解析到 CVM；`server_name` 是否匹配 |
| 接口 502 | `dc logs api`；`migrate` 是否成功（Exited 0）；`DATABASE_URL` 是否正确；构建是否失败 |
| 接口全部 500 且日志报表不存在 | `migrate` 服务没跑成功，`dc logs migrate` |
| 上传文档/图片 413 | `nginx.prod.conf` 的 `client_max_body_size` 是否 ≥ `MAX_UPLOAD_MB` |
| 生成进度不刷新 | SSE 通路：`proxy_buffering off`、`proxy_http_version 1.1`、`Connection ""`；`dc logs worker` |
| 页面一直"排队中" | worker 没起 / `REDIS_URL` 不对 / LLM 密钥无效 / 供应商限流（`dc logs worker`） |
| 导出内容溢出、判定不准 | 字体是否缺失（第 5 章），`dc exec api ls -l /app/fonts` |
| 图片不显示 | COS 配置是否正确；`STORAGE_DRIVER` 是否与凭证匹配；若本地存储需确认 api/worker 挂了同一卷 |
| 数据库连接失败 | `POSTGRES_PASSWORD` 是否含特殊字符（用 `openssl rand -hex 32`）；`dc config` 看展开的 URL |
| 容器反复重启 | `dc logs --tail=100 <服务>`；常见是 env 缺失导致 pydantic 校验失败 |

日志里出现 `POSTGRES_PASSWORD is required` 说明根目录 `.env` 没建或变量名写错——这是 compose 的 `:?` 保护在生效。

---

## 9. 上线检查清单

- [ ] 服务器：Docker + Compose Plugin 已装，2 核 4GB 以上，磁盘 ≥40GB
- [ ] 安全组只开 22（限 IP）、80、（可选）443
- [ ] 域名 A 记录指向 CVM
- [ ] `frontend/Dockerfile` 已新增（构建上下文为仓库根）
- [ ] `nginx.prod.conf` 已新增，`client_max_body_size` 与 `MAX_UPLOAD_MB` 一致
- [ ] `docker-compose.prod.yml` 已换成生产版（有 `migrate`、有 `restart`、只映射 80/443）
- [ ] 根 `.env` 已创建，`POSTGRES_PASSWORD` 为 `openssl rand -hex 32`
- [ ] `backend/.env.production` 已创建，`JWT_SECRET` 为强随机值，且**未提交 Git**
- [ ] `APP_ENV=production`，`CORS_ORIGINS` 为正式域名 JSON 数组
- [ ] LLM / 生图 / Unsplash 密钥已配（生图与图库至少一个可用）
- [ ] COS 已配（或本地存储 + api/worker 共享卷已配）
- [ ] `dc config` 通过
- [ ] `migrate` 退出码 0，`\dt` 能看到表
- [ ] `/api/v1/health` 返回 `database: ok`、`redis: ok`
- [ ] `dc exec api ls -l /app/fonts` 两个字体都在
- [ ] `dc exec api ls /shared/layouts` 能看到 11 个版式
- [ ] 浏览器完成：注册 → 建项目 → 大纲 → 生成页面（进度实时）→ 上传文档 → 编辑 → 导出 PPTX 并确认可编辑
- [ ] 数据库每日备份已配置并验证过一次恢复
- [ ] 若需 HTTPS：证书已挂载或 CLB 已配置，`CORS_ORIGINS` 已改为 https

---

## 10. 相关文档

- 本手册：可执行步骤，已对照代码逐条核对。
- `docs/tencent-cloud-docker-compose-deploy.md`：早期版本的部署文档，包含更多设计缘由与背景说明，可作补充阅读；其中"建议新增前端 Dockerfile / 建议新增 migrate 服务"等条目，已在本手册第 2 章给出可直接使用的成品文件。
