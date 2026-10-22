from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import get_settings
from app.infrastructure.llm.base import OutlineGenerator, SlideEditGenerator, SlideGenerator
from app.infrastructure.llm.client import create_chat_model
from app.infrastructure.llm.deepseek import DeepSeekOutlineGenerator
from app.infrastructure.llm.relayout import DeepSeekRelayoutGenerator
from app.infrastructure.llm.slide import DeepSeekSlideGenerator
from app.infrastructure.llm.slide_edit import DeepSeekSlideEditGenerator


def create_outline_generator(model: BaseChatModel | None = None) -> OutlineGenerator:
    settings = get_settings()
    return DeepSeekOutlineGenerator(
        model=model or create_chat_model(),
        api_key=settings.llm_api_key,
    )


def create_slide_generator(model: BaseChatModel | None = None) -> SlideGenerator:
    settings = get_settings()
    return DeepSeekSlideGenerator(
        model=model or create_chat_model(),
        api_key=settings.llm_api_key,
    )


def create_slide_edit_generator(model: BaseChatModel | None = None) -> SlideEditGenerator:
    settings = get_settings()
    return DeepSeekSlideEditGenerator(
        model=model or create_chat_model(),
        api_key=settings.llm_api_key,
    )


def create_relayout_generator(model: BaseChatModel | None = None) -> DeepSeekRelayoutGenerator:
    settings = get_settings()
    return DeepSeekRelayoutGenerator(
        model=model or create_chat_model(),
        api_key=settings.llm_api_key,
    )
