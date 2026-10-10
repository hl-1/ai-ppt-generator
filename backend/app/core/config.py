import os
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import REPO_ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / "backend" / (
            ".env.production" if os.getenv("APP_ENV") == "production" else ".env"
        ),
        extra="ignore",
    )

    app_env: str = "development"
    # 端口统一使用 39xxx 段，避开各服务默认端口，防止与本机已装的
    # PostgreSQL / Redis / 其他开发服务抢占端口
    database_url: str = "postgresql+asyncpg://aippt:aippt@localhost:39432/aippt"
    redis_url: str = "redis://localhost:39379/0"
    cors_origins: list[str] = ["http://localhost:39173"]
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-v4-flash"
    # 大纲默认关闭思考模式以满足首个结果 10 秒内返回的目标；
    # 遇到复杂主题时可通过环境变量开启，不把供应商参数写死在工作流里。
    llm_thinking_enabled: bool = False
    llm_timeout_seconds: float = 60
    # 单份 PPT 同时生成的页数。调高能缩短总时长，但容易触发供应商限流，
    # 且失败会成片出现；3 是延迟与稳定性之间比较稳妥的取值。
    slide_concurrency: int = 3
    # 仅 Worker 需要安装办公渲染引擎；API 与 Worker 配置相同的启用标记。
    preview_soffice: str = ""
    preview_pdftoppm: str = "pdftoppm"
    export_require_preview: bool = False
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    # 本项目不做 refresh token，access token 默认 7 天
    jwt_expire_minutes: int = 60 * 24 * 7

    # AI 生图与图库各自独立配置：两者是互相降级的关系，
    # 只配一个也要能正常工作，因此不共用 LLM 的凭证。
    # openai = OpenAI 兼容 /images/generations；bailian = 百炼 DashScope 原生接口
    image_provider: Literal["openai", "bailian"] = "openai"
    image_api_key: str = ""
    image_base_url: str = "https://api.openai.com/v1"
    image_model: str = "gpt-image-1"
    # 百炼业务空间 ID：填写后使用专属域名，覆盖 image_base_url
    image_workspace_id: str = ""
    unsplash_access_key: str = ""
    stock_search_timeout_seconds: float = 8
    qweather_api_host: str = ""
    qweather_api_key: str = ""
    amap_api_key: str = ""
    firecrawl_api_key: str = ""
    travel_service_timeout_seconds: float = 15
    travel_web_timeout_seconds: float = 60
    travel_web_concurrency: int = 2
    travel_web_requests_per_minute: int = 10
    travel_total_timeout_seconds: float = 300
    travel_service_retries: int = 1
    travel_video_max_candidates: int = 36
    travel_video_search_rounds: int = 3
    travel_video_max_selected: int = 4
    travel_video_timeout_seconds: float = 240
    travel_video_item_timeout_seconds: float = 40
    travel_video_max_duration_seconds: int = 900
    travel_video_max_download_mb: int = 100
    travel_video_cookie_file: str = ""
    travel_video_asr_enabled: bool = True
    travel_video_asr_model: str = "small"
    travel_video_asr_threads: int = 4
    travel_video_asr_timeout_seconds: float = 120
    image_timeout_seconds: float = 60

    storage_driver: Literal["local", "cos"] = "local"
    storage_local_dir: str = str(REPO_ROOT / "backend" / "var" / "storage")
    cos_bucket: str = ""
    cos_region: str = ""
    cos_secret_id: str = ""
    cos_secret_key: str = ""

    # 上传体积上限。定得过大会让解析长时间占住请求线程
    max_upload_mb: int = 10
    max_image_mb: int = 8

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_image_bytes(self) -> int:
        return self.max_image_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    # 缓存避免每个请求重复解析环境变量
    return Settings()
