from arq.connections import RedisSettings

from app.core.config import get_settings
from app.infrastructure.database import models  # noqa: F401  # Worker 独立启动时注册全部模型
from app.modules.decks.preview_tasks import generate_preview
from app.modules.decks.tasks import generate_deck
from app.modules.media.tasks import generate_slide_images
from app.modules.outlines.tasks import generate_outline
from app.modules.travel.research import generate_travel_research
from app.worker.context import shutdown, startup
from app.worker.retry import MAX_TRIES


class WorkerSettings:
    functions = [
        generate_outline,
        generate_deck,
        generate_preview,
        generate_slide_images,
        generate_travel_research,
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 3
    # 整份生成在任务内部并发，耗时随页数增长，超时需要比大纲宽松得多
    job_timeout = 15 * 60
    max_tries = MAX_TRIES
    allow_abort_jobs = True
