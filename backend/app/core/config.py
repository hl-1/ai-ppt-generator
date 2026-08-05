from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.paths import REPO_ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    # 本项目不做 refresh token，access token 默认 7 天
    jwt_expire_minutes: int = 60 * 24 * 7

    storage_driver: Literal["local", "cos"] = "local"
    storage_local_dir: str = str(REPO_ROOT / "backend" / "var" / "storage")
    cos_bucket: str = ""
    cos_region: str = ""
    cos_secret_id: str = ""
    cos_secret_key: str = ""

    # 上传体积上限。定得过大会让解析长时间占住请求线程
    max_upload_mb: int = 10

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    # 缓存避免每个请求重复解析环境变量
    return Settings()
