# 当前生产部署

生产配置统一放在仓库根的 `deploy/`，构建上下文为仓库根。

```text
deploy/
├── docker-compose.prod.yml
├── backend.Dockerfile
├── frontend.Dockerfile
├── worker-preview.Dockerfile
├── nginx.prod.conf
├── .env.production.example
├── .env.production          # 本机填写，Git 忽略
└── certs/                   # TLS 证书与私钥，Git 忽略
```

## 准备与启动

```bash
cp deploy/.env.production.example deploy/.env.production
# 编辑 POSTGRES_PASSWORD、JWT_SECRET、模型、存储及外部服务配置
make prod-config
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml up -d --build
```

Windows 可用 `Copy-Item` 复制环境模板。现有环境文件迁移到新路径后直接复用。
生产数据库密码只在 `deploy/.env.production` 中维护，Compose 自动注入数据库连接串。

Compose 包含 PostgreSQL、Redis、一次性 Alembic 迁移、API、Worker 和 Nginx。
API/Worker 等待迁移成功和 Redis 健康后启动，内部端口 39800，外部入口为 80/443。
API、Worker 使用相同镜像及共享设计规则，媒体使用共同的持久化卷。

## 当前入口依赖

`deploy/nginx.prod.conf` 保留当前 `huanliyu.cn`、`www.huanliyu.cn` 和
`code.huanliyu.cn` 的代理配置。AI PPT 证书放在 `deploy/certs/`，文件名对应 Nginx 配置。
代码生成器证书仍来自宿主机 `/opt/code-generator/certs`。

代码生成器通过外部 Docker 网络 `huanliyu-ingress` 连接，服务别名为
`code-generator-web`。首次部署需要准备该共享网络及对应服务：

```bash
docker network create huanliyu-ingress
```

已有共享网络时跳过创建。迁移到其他域名/服务器时，应同时调整 Nginx 的域名、证书名、
证书挂载和共享网络。SSE 代理关闭缓冲，读取超时与 Worker 任务时限保持匹配。

## 运维

```bash
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml ps
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml logs -f api worker
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml down
```

生产 Compose 项目名保持 `aippt`，数据库和 Redis 卷名保持原项目名规则。
停止服务时保留持久化卷。使用本地媒体且原来显式配置了其他挂载位置时，继续保留相同的
`STORAGE_LOCAL_DIR` 及卷挂载，或先迁移媒体后再切换到新的默认卷。

## 真实 PPTX 预览镜像

需要 LibreOffice/Poppler 时可在基础后端镜像上构建：

```bash
docker build -f deploy/backend.Dockerfile -t aippt-backend .
docker build -f deploy/worker-preview.Dockerfile --build-arg BASE_IMAGE=aippt-backend -t aippt-backend-preview .
```

`worker-preview.Dockerfile` 安装预览工具；按运行需要在 Compose 的 API/Worker 中选择
该镜像。旅行视频功能还需要为 Worker 安装 ffmpeg、Playwright Chromium 和相应系统依赖，
安装命令见 [development.md](development.md)。

旧部署过程与实施记录见 [archive/](archive/)，当前路径和入口以本文为准。
