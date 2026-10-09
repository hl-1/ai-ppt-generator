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

## 旅游视频攻略

Python 后端会搜索抖音和 B 站公开视频，读取单条视频的点赞、收藏与发布时间，筛选后提取平台字幕；无字幕时使用本地 faster-whisper 语音转写。抖音平台 AI 章节摘要作为最后的参考来源，并单独标注。视频体验不作为官方票价或预约依据。

旅行条件中可调整平台、点赞下限、收藏下限和发布时间范围。只参考时长不超过 15 分钟的视频；超时长或时长未知的候选直接跳过，不提取内容。默认筛选最近 180 天内点赞至少 1 万或收藏至少 1000 的相关视频。缺失热度或发布时间的候选不会自动入选。建议、原文、起止时间和来源保存在旅行资料中，并分别进入住宿、景点体验、餐饮页面及讲稿。

## 旅游规划页面

前四页固定为封面、路线与交通总览、天气与空气质量、住宿推荐，末页为消费成本汇总。用户选择的页数扣除这五页后，用于推荐景点数量，并结合旅行天数、节奏与必去地点调整；例如三日旅行选择 10 页时，优先安排最多 5 个景点。每个景点默认一页攻略，只展示营业、门票、预约、证件、入园、限制和体验要点，不粘贴官网长段原文；完整证据和来源保存在备注。较长的日程、天气或交通信息确实放不下时才增加页面，不生成重复的凑页内容，并同步实际项目页数。

旅行查询使用 `AMAP_API_KEY` 获取 POI、路线、景点周边餐饮及静态地图，使用 `QWEATHER_API_HOST` 和 `QWEATHER_API_KEY` 获取天气及空气质量，使用 `FIRECRAWL_API_KEY` 搜索官方规则与近期住宿、体验资料。高德密钥需开通静态地图权限；地图保留高德底图署名，坐标采用 GCJ-02，连线仅表示游览顺序。真实景点照片和地图会校验、保存到项目媒体存储，再进入预览与 PPTX，不依赖远端图片在导出时仍可访问。

天气仅匹配已发布的出行日期预报。空气质量采用每日预报接口，当前实况另列并注明适用日期，不补作未来预报。无预报、官方规则、合适视频或图片时保留缺失状态；生成后的编辑界面也显示资料与图片缺失。旧版旅行资料会提示刷新。

住宿按房间数和晚数计算，默认每间住两人并注明假设。仅在官方近期房价具有匹配日期、房型、每间每晚单位和税费条件时纳入参考报价，其他价格仍为参考或待确认。餐饮预算和团队备用金可在旅行条件中调整；缺价项目不按零元处理，部分合计不能视为完整报价。

Worker 安装后还需准备 Chromium 和系统 ffmpeg：

```bash
cd backend
uv sync
uv run python -m playwright install chromium
# Linux Worker: uv run python -m playwright install --with-deps chromium
```

语音模型默认使用 `small`，首次使用会下载到 `backend/var/video-models`。模型下载和转写均受超时限制，可事先预热：

```bash
uv run python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8', download_root='var/video-models')"
```

长视频超过转写限时后，会保留已转写的片段并标注“部分内容”，建议仅依据这些片段整理。没有字幕、语音或可用章节摘要的视频会显示读取未完成。

可在本地 `.env` 使用 `TRAVEL_VIDEO_COOKIE_FILE` 指定操作人员提供的 Netscape 格式 Cookie 文件，以读取该登录态有权访问的视频。Cookie 不进入 API 响应、旅行来源或日志，请放在仓库之外。未登录或平台访问受限时，已有资料仍会保存，失败候选会标明状态。

独立验证联网搜索到建议提取的流程，不修改已有项目：

```bash
uv run python scripts/smoke_travel_video.py --destination 北京 --platform douyin --output var/video-smoke.json
```

验证真实旅行资料、图片与路线图、全部页面和 PPTX 导出，可启动前端后运行：

```bash
uv run python scripts/smoke_travel_requirements.py --ui-url http://127.0.0.1:39173
# 复用已保存资料，检查固定版式，无需重复联网查询：
uv run python scripts/smoke_travel_requirements.py --resume --layout fixed --ui-url http://127.0.0.1:39173
```

结果保存到 `backend/var/travel-requirements-smoke/`，包含来源资料、PPTX、每页桌面/手机截图与检查报告。界面检查使用隔离的模拟响应，不修改已有项目；实际 PPTX 栅格预览仍需配置 LibreOffice。

## 金融科技主题

主题预设包含“金融科技蓝金”，提供金色标题、箭头业务面板、指标框与平台架构图。
在大纲或编辑器的主题列表中选择即可应用，也可通过 `/themes/financial-tech` 查看、编辑和导出配套示例。

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
