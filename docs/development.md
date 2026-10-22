# 安装、启动、调试和测试

## 环境

需要 Python 3.12+、uv、Node.js 22+、npm、Docker Compose v2。
可选 Java 后端需要 JDK 21 和 Maven。Windows 终端推荐 PowerShell 7。

在仓库根目录执行：

```bash
python scripts/dev.py init
make install
make fonts
make up
make migrate
```

`init` 只补充缺失的根 `.env`、`backend/.env` 和本地运行目录。
也可用 `python scripts/dev.py install` 完成初始化和依赖安装。
填写 `backend/.env` 中的模型及外部服务凭证后，分别启动：

```bash
make dev-api
make dev-worker
make dev-web
```

API 为 `http://127.0.0.1:39800`，前端为 `http://127.0.0.1:39173`。
PostgreSQL 和 Redis 宿主机端口分别为 39432、39379。

也可在根目录使用统一后台管理入口：

```bash
make start
make restart
make stop
```

对应 `python scripts/dev.py start|restart|stop`，可从任意工作目录调用脚本的完整路径。
启动会等待基础设施就绪并执行迁移；服务输出保存在 `.local/logs/`，进程记录保存在
`.local/runtime/dev-processes.json`。`stop` 关闭该入口启动的 API、Worker 和 Web；
`make down` 关闭开发 Compose。独立启动的服务请在原终端停止后再使用后台入口。
Windows 可运行 `scripts/restart.cmd` 或 `pwsh -File scripts/restart.ps1`。

## 可选 Java 后端

```bash
make dev-java-api
make dev-java-worker
```

Java API 与 Python API 共用 39800 端口，选择一种实现运行。
Python 继续负责数据库迁移。Java 默认回退读取 `backend/.env`；独立配置放在
`java-backend/.env`。两种实现均使用 `tools/diagram-engine/`。

## 检查

```bash
make lint
make test
make build-web
make test-java
make regression
make check
# 包含可选 Java 后端：
python scripts/check.py --java
```

Python 测试固定从 `backend/tests/` 收集；集成测试需要迁移后的 PostgreSQL 和 Redis。
测试媒体使用临时目录，避免写入真实媒体存储。固定回归语料在
`backend/regression/corpus/`，执行器在 `app/engine/quality/regression/`。

生成前端 API 类型：

```bash
make gen-api
```

OpenAPI 中间文件写入 `.local/reports/openapi.json`，生成类型写入
`frontend/src/api/schema.d.ts`。

## 旅行与渲染专项检查

旅行视频读取需要系统 ffmpeg 和 Playwright Chromium。首次安装浏览器：

```bash
cd backend
uv run python -m playwright install chromium
# Linux Worker:
# uv run python -m playwright install --with-deps chromium
```

语音模型缓存位于 `.local/runtime/video-models/`。模型、Cookie、地图、天气和网页研究的
配置含义见 [configuration.md](configuration.md)。本机 Cookie 放在仓库之外。

在 `backend/` 运行：

```bash
uv run python scripts/smoke_travel_video.py --destination 北京 --platform douyin --output ../.local/reports/video-smoke.json
uv run python scripts/smoke_travel_requirements.py --ui-url http://127.0.0.1:39173
uv run python scripts/check_theme_layouts.py --url http://127.0.0.1:39173
uv run python scripts/dump_diagram_fixture.py
```

旅行及主题检查的默认输出位于 `.local/reports/`。真实 PPTX 栅格预览需要
LibreOffice 和 Poppler，配置 `PREVIEW_SOFFICE`、`PREVIEW_PDFTOPPM`。
修改 Python 生成逻辑后同时重启 API 和 Worker，再重新生成页面验证。

历史功能说明和专项实施记录位于 [archive/](archive/)。
