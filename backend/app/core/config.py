from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    # 端口统一使用 39xxx 段，避开各服务默认端口，防止与本机已装的
    # PostgreSQL / Redis / 其他开发服务抢占端口
    database_url: str = "postgresql+asyncpg://aippt:aippt@localhost:39432/aippt"
    redis_url: str = "redis://localhost:39379/0"
    cors_origins: list[str] = ["http://localhost:39173"]
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    # 本项目不做 refresh token，access token 默认 7 天
    jwt_expire_minutes: int = 60 * 24 * 7


@lru_cache
def get_settings() -> Settings:
    # 缓存避免每个请求重复解析环境变量
    return Settings()
