# 目录职责与依赖关系

## 工程顶层

| 目录 | 职责 |
| --- | --- |
| `backend/` | Python API、Worker、数据库迁移、测试和后端专项脚本 |
| `frontend/` | React 编辑器、浏览器渲染和前端校验脚本 |
| `java-backend/` | 可选 Java 后端，与 Python 使用相同接口及共享设计资产 |
| `shared/` | 前后端共用的主题、布局、排版规则、样例和对齐夹具 |
| `tools/diagram-engine/` | Python、Java 共用的 Node.js Mermaid / ELK 流程图引擎 |
| `scripts/` | 工程初始化、启动、停止、重启和检查入口 |
| `ops/compose/` | 本地开发 PostgreSQL、Redis 的 Compose 配置 |
| `deploy/` | 生产 Compose、Nginx、Dockerfile、环境变量模板及本机证书 |
| `docs/` | 当前架构、开发、配置和部署说明；历史记录在 `archive/` |
| `.local/` | 本机日志、报告、截图、缓存、临时文件和运行数据，Git 忽略 |

## Python 应用

```text
backend/app/
├── main.py
├── api/                    # API 聚合、健康检查、公共依赖、SSE
├── core/                   # 配置、统一路径
├── infrastructure/
│   ├── database/           # SQLAlchemy 会话、模型注册
│   ├── redis/              # Redis 客户端、ARQ 队列、事件流
│   ├── llm/                # 模型客户端、适配器、调用契约、模型工厂
│   ├── storage/            # 本地/COS 存储、媒体键和 URL 转换
│   └── providers/          # 图片、天气、地图、网页研究等外部服务
├── modules/
│   ├── auth/               # 用户、认证接口、密码和 JWT
│   ├── projects/           # 项目、来源管理、输入文档解析
│   ├── outlines/           # 大纲模型、接口、工作流、任务、进度
│   ├── decks/              # 幻灯片接口、编辑、生成、预览、导出编排
│   ├── media/              # 图片搜索、候选、任务、页面配图
│   └── travel/             # 旅行资料、规划、页面与视频提取
├── engine/
│   ├── content/            # 内容/来源模型、规范化、编辑操作、分页
│   ├── layout/             # Flex、卡片、表格、主题和企业排版
│   ├── diagram/            # 流程图规则、样式与 Node.js 引擎适配
│   ├── quality/            # 内容/视觉检查、导出检查、固定回归集执行器
│   └── pptx/               # PPTX 原生对象渲染、回读验证和栅格预览
└── worker/                 # ARQ 任务注册、进程生命周期、重试约定
```

业务模块集中保存自己的 `router`、`schemas`、`models` 和业务编排。复杂的
幻灯片路由继续按编辑、分页、布局、图片和导出拆分到 `decks/router/`。
ARQ 的函数名保持 `generate_outline`、`generate_deck`、`generate_preview`、
`generate_slide_images`、`generate_travel_research`，已有任务按这些名字注册。

## 依赖约定

- `main` 负责应用创建与资源清理，`api/router.py` 仅聚合业务路由。
- `modules` 调用 `engine` 和 `infrastructure`；跨业务模块的协作使用明确导入。
- 内容、布局、流程图和质量算法不依赖 API 或 Worker。PPTX 渲染通过存储适配器读取媒体。
- 模型工厂位于 `infrastructure/llm/factory.py`，API 和 Worker 使用同一套创建逻辑。
- `worker` 仅保留任务注册、生命周期和重试；业务任务实现放在所属模块。
- `core/paths.py` 是 Python 路径的统一入口，移动模块时避免使用模块深度推导资源位置。
- 来源契约位于 `engine/content/source.py`，文档解析器与内容引擎共同使用。
- ORM 模型由 `infrastructure/database/models.py` 统一注册；API、测试和 Alembic 使用同一注册入口。

本次迁移保留 `/api/v1` 接口、SQL 表名和 Alembic 修订历史，目录迁移不需要新增数据库迁移。
