# AI PPT Generator

从主题、长文本或 PDF / Word / Markdown 文档生成大纲，通过异步任务生成和编辑幻灯片，
导出可编辑的 PPTX。项目提供 React 前端、FastAPI API/ARQ Worker，以及可选 Java 后端。

## 项目结构

```text
ai-ppt-generator/
├── backend/                # Python API、Worker、迁移和测试
├── frontend/               # React 前端
├── java-backend/            # 可选 Java 后端
├── shared/                 # 跨端设计规则、主题、布局和样例
├── tools/diagram-engine/   # Python、Java 共用流程图引擎
├── scripts/                # 初始化、启动、停止、重启和检查
├── ops/                    # 开发环境 Compose
├── deploy/                 # 全部生产配置、Dockerfile、环境模板
├── docs/                   # 当前文档及 archive/ 历史记录
├── .local/                 # 本地运行数据、日志、报告、截图和缓存
├── .env                    # 本地 Compose 变量，Git 忽略
└── Makefile                # 常用命令
```

后端应用按 `api / core / infrastructure / modules / engine / worker` 组织，
业务模块包括认证、项目、大纲、幻灯片、媒体和旅行。目录职责见
[架构说明](docs/architecture.md)。

## 快速开始

需要 Python 3.12+、uv、Node.js 22+ 和 Docker Compose v2。在根目录执行：

```bash
python scripts/dev.py init
make install
make fonts
# 编辑 backend/.env，填写模型与外部服务配置
make start
```

前端：`http://127.0.0.1:39173`；API：`http://127.0.0.1:39800`。
后台日志位于 `.local/logs/`。使用 `make stop` 停止本项目管理的服务，
`make restart` 同时重启 API、Worker 和前端。

需要分别调试时使用 `make up`、`make migrate`，再分别运行
`make dev-api`、`make dev-worker`、`make dev-web`。

## 常用命令

| 命令 | 用途 |
| --- | --- |
| `make test` / `make lint` | Python 测试和代码检查 |
| `make build-web` | 前端类型检查和生产构建 |
| `make test-java` | 可选 Java 后端测试 |
| `make check` | 后端检查、测试与前端检查、构建 |
| `make gen-api` | 从 OpenAPI 更新前端接口类型 |
| `make regression` | 固定语料的可编辑性、排版和主题回归 |
| `make prod-config` | 校验生产 Compose 配置 |

## 生产部署

生产配置集中在 [deploy/](deploy/README.md)：

```bash
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml up -d --build
```

首次部署请按 [部署说明](docs/deployment.md) 准备环境变量、证书和入口网络。

## 文档

- [架构与依赖](docs/architecture.md)
- [安装、开发、调试和测试](docs/development.md)
- [配置位置与读取顺序](docs/configuration.md)
- [当前生产部署](docs/deployment.md)
- [历史功能说明与实施记录](docs/archive/README-before-restructure.md)
