# AI PPT Generator

AI PPT Generator 是一个前后端分离的 AI 幻灯片生成与编辑工具。项目支持从主题、长文本或文档生成大纲，并通过异步任务生成页面，最后导出可编辑的 PPTX 文件。

## 功能概览

- 主题、长文本、PDF、Word、Markdown、TXT 等输入方式
- 大纲生成、编辑、排序和确认
- 基于 Redis/ARQ 的异步页面生成
- 前端 SSE 实时展示生成进度
- 在线编辑幻灯片内容、主题和布局
- 原生可编辑 PPTX 导出
- FastAPI 后端、React 前端，以及可选 Java 后端实现

## 技术栈

- 前端：React、TypeScript、Vite、Tailwind CSS
- Python 后端：FastAPI、SQLAlchemy、Alembic、ARQ、Redis、LangChain、LangGraph
- Java 后端：Spring Boot、Maven
- 数据库与基础设施：PostgreSQL、Redis、Docker Compose
- PPTX 导出：python-pptx、FontTools

## 本地开发

安装依赖：

```bash
make install
```

准备字体资源：

```bash
make fonts
```

执行数据库迁移：

```bash
make migrate
```

分别启动 API、Worker 和前端：

```bash
make dev-api
make dev-worker
make dev-web
```

前端默认运行在 Vite 开发服务端口，API 默认运行在 `http://127.0.0.1:39800`。

## 常用命令

```bash
make test       # 运行 Python 后端测试
make lint       # 运行 Python 后端 lint
make gen-api    # 从 FastAPI OpenAPI 生成前端类型
make regression # 运行固定回归集
```

## 生产部署

项目提供了 `docker-compose.prod.yml`、`frontend/Dockerfile` 和 `nginx.prod.conf` 作为生产部署参考。

启动前需要准备生产环境变量文件，例如：

```text
backend/.env.production
POSTGRES_PASSWORD
```

证书文件建议放在本地 `certs/` 或部署目录中，并确保私钥、环境变量和部署证书不提交到 Git。
