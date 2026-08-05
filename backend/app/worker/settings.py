from arq.connections import RedisSettings

from app.core.config import get_settings
from app.worker.tasks import generate_outline, shutdown, startup


class WorkerSettings:
    functions = [generate_outline]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 3
    job_timeout = 90
    max_tries = 2
    allow_abort_jobs = True
