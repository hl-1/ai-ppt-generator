# AI 智能 PPT 生成器

输入主题、长文本或文档，生成结构完整、可在线编辑、可导出为原生可编辑 PPTX 的 PPT。

## 环境要求

| 依赖 | 版本 |
| --- | --- |
| Python | >= 3.12 |
| Node.js | >= 20 |
| uv | >= 0.6 |
| Docker | 用于启动 PostgreSQL 与 Redis |

## 启动

```bash
cp backend/.env.example backend/.env   # 按需修改
make up        # 启动 PostgreSQL 与 Redis
make install   # 安装前后端依赖
make migrate   # 执行数据库迁移
make dev-api   # 启动 API，http://127.0.0.1:39800
make dev-web   # 另开一个终端，启动前端，http://localhost:39173
```

## 端口

所有服务统一占用 39xxx 段，避开各自的默认端口，本机已装同类服务时不会冲突。

| 服务 | 端口 |
| --- | --- |
| PostgreSQL | 39432 |
| Redis | 39379 |
| API | 39800 |
| 前端开发服务器 | 39173 |

## 其他命令

```bash
make test   # 后端测试
make lint   # 后端静态检查
make down   # 停止依赖服务
```

## 环境变量

见 `backend/.env.example`，每个变量都有中文注释。
