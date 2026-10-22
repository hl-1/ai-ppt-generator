# 配置位置、用途与读取顺序

| 文件/目录 | 用途 | Git |
| --- | --- | --- |
| `.env` | 本地开发 Compose 变量 | 忽略 |
| `.env.example` | 本地 Compose 变量模板 | 提交 |
| `backend/.env` | Python 开发 API/Worker 配置 | 忽略 |
| `backend/.env.example` | 后端配置字段和示例 | 提交 |
| `java-backend/.env` | 可选 Java 本机配置 | 忽略 |
| `deploy/.env.production` | 生产 Compose 和 API/Worker 配置 | 忽略 |
| `deploy/.env.production.example` | 生产配置模板 | 提交 |
| `deploy/certs/` | 当前 Nginx 的 TLS 证书及私钥 | 忽略 |
| `shared/` | 主题、布局和跨端设计规则 | 提交 |
| `.local/` | 本机运行数据、日志、报告和缓存 | 忽略 |

## Python

`Settings` 首先采用显式传入的字段，其次是进程环境变量，再读取环境文件，最后使用
代码默认值。进程环境变量 `APP_ENV=production` 选择 `deploy/.env.production`，
其他值选择 `backend/.env`。环境文件路径相对于仓库根，不受当前工作目录影响。
`Settings` 在进程内缓存，修改后需要重启 API 和 Worker。

生产 Compose 通过 `env_file` 注入 `deploy/.env.production`，并明确覆盖
`APP_ENV`、`DATABASE_URL`、`REDIS_URL`，使数据库和队列走容器内服务名。
根 `.env` 不作为 Python 开发设置的自动回退文件。

## Java

系统环境和 Spring 已有的非空配置优先。开发模式下使用 `java-backend/.env` 的非空值，
缺失字段回退至 `backend/.env`。生产模式通过 `APP_ENV=production` 选择
`deploy/.env.production`。目录统一由 `RepoPaths` 解析。

## 配置组

- 数据库/队列：`DATABASE_URL`、`REDIS_URL`。
- 认证/跨域：`JWT_SECRET`、`JWT_ALGORITHM`、`JWT_EXPIRE_MINUTES`、`CORS_ORIGINS`。
- 文本模型：`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、`LLM_TIMEOUT_SECONDS`。
- 图片：`IMAGE_PROVIDER`、`IMAGE_API_KEY`、`IMAGE_BASE_URL`、`IMAGE_MODEL`、`UNSPLASH_ACCESS_KEY`。
- 旅行：`AMAP_API_KEY`、`QWEATHER_API_HOST`、`QWEATHER_API_KEY`、`FIRECRAWL_API_KEY`，以及 `TRAVEL_*` 超时和并发配置。
- 视频：`TRAVEL_VIDEO_COOKIE_FILE`、`TRAVEL_VIDEO_ASR_ENABLED`、`TRAVEL_VIDEO_ASR_MODEL` 等。
- 媒体：`STORAGE_DRIVER=local|cos`、`STORAGE_LOCAL_DIR`、`COS_*`。
- PPTX 预览：`PREVIEW_SOFFICE`、`PREVIEW_PDFTOPPM`、`EXPORT_REQUIRE_PREVIEW`。
- Compose 数据库密码：`POSTGRES_PASSWORD`；生产环境必须填写。

Python 和 Java 默认本地媒体目录为 `.local/runtime/storage/`。生产 Compose 将同一
`storage_data` 卷挂载给 API 和 Worker。使用 COS 时通过 `STORAGE_DRIVER=cos` 选择驱动。
自定义 `STORAGE_LOCAL_DIR` 应使用绝对路径，并确保 API 和 Worker 指向相同位置。

Python 的统一路径定义在 `backend/app/core/paths.py`：字体位于 `backend/fonts/`，
流程图入口为 `tools/diagram-engine/engine.mjs`，测试报告位于 `.local/reports/`。
