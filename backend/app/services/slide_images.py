import logging
import uuid
from collections.abc import Awaitable, Callable
from hashlib import sha256

from app.domain.content import ImageBlock, Slide
from app.domain.geometry import CANVAS_HEIGHT_PT, CANVAS_WIDTH_PT, Rect
from app.domain.slide_geometry import placed_by_block_id
from app.domain.theme import Theme
from app.images.base import ImageRequest
from app.images.errors import ImageFetchError
from app.images.pipeline import ImagePipeline
from app.images.validate import ImageRejected, validate_image
from app.services.media import media_url, store_image

logger = logging.getLogger(__name__)


def _image_aspect(rect: Rect) -> float:
    height = rect.h * CANVAS_HEIGHT_PT
    if height <= 0:
        return 16 / 9
    return (rect.w * CANVAS_WIDTH_PT) / height


async def resolve_slide_images(
    pipeline: ImagePipeline,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    deck_title: str,
    page_title: str,
    slide: Slide,
    excluded_ids: set[str] | None = None,
    theme: Theme | None = None,
    attempts: int = 1,
    reserve: Callable[[str], Awaitable[bool]] | None = None,
) -> Slide:
    """为尚未填充的图片块拉取真实图源；失败则保留占位，绝不打断整页。"""
    placements = placed_by_block_id(slide)
    excluded_ids = excluded_ids if excluded_ids is not None else set()
    blocks = []
    for block in slide.blocks:
        if not isinstance(block, ImageBlock) or block.url is not None or block.locked:
            blocks.append(block)
            continue
        placed = placements.get(block.id)
        if placed is None:
            logger.warning("图片块无几何位置，保留占位图：%s", block.id)
            blocks.append(
                block.model_copy(
                    update={
                        "image_status": "failed",
                        "image_error": "图片没有可用位置，请调整版式后重试",
                    }
                )
            )
            continue
        resolved = await _resolve_one(
            pipeline,
            block=block,
            user_id=user_id,
            project_id=project_id,
            deck_title=deck_title,
            page_title=page_title,
            rect=placed.rect,
            excluded_ids=excluded_ids,
            theme=theme,
            attempts=attempts,
            reserve=reserve,
        )
        blocks.append(resolved)
        if resolved.image_asset_id:
            excluded_ids.add(resolved.image_asset_id)
    return slide.model_copy(update={"blocks": blocks})


async def _resolve_one(
    pipeline: ImagePipeline,
    *,
    block: ImageBlock,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    deck_title: str,
    page_title: str,
    rect: Rect,
    excluded_ids: set[str] | None = None,
    theme: Theme | None = None,
    attempts: int = 1,
    reserve: Callable[[str], Awaitable[bool]] | None = None,
) -> ImageBlock:
    try:
        aspect = _image_aspect(rect)
        # prompt 给生图、query 给图库：同一语义在两边的最佳措辞不同
        plan = block.image_plan
        palette = (
            f"整套配图统一使用主题强调色 {theme.palette.accent}、"
            f"背景色 {theme.palette.background} 和辅助色 {theme.palette.accent_soft}，"
            "这些颜色用于背景和点缀，保留主体自然色彩。"
            if theme else "整套配图保持克制的配色与柔和自然光。"
        )
        style = (
            "采用简洁的编辑插画风格，造型清晰，避免复杂纹理。"
            if plan and plan.source == "generated"
            else "采用清晰、自然的专业摄影风格，避免夸张特效。"
        )
        request = ImageRequest(
            prompt=(
                f"画面主体：{plan.subject if plan else block.alt}。"
                f"用于「{deck_title}」的「{page_title}」页面。{style}{palette}"
                f"画幅宽高比约 {aspect:.2f}:1，主体完整清晰，四周保留约 15% 裁切余量。"
                "背景简洁，突出一个与本页直接相关的场景，不拼贴无关元素。"
                "画面中不要出现文字、水印、品牌标志或虚构的可读界面。"
            ),
            query=block.alt,
            aspect_ratio=aspect,
            queries=plan.queries if plan else [],
            subject=plan.subject if plan else block.alt,
            preferred_source=plan.source if plan else "auto",
            require_real=plan.require_real if plan else False,
            excluded_ids=excluded_ids or set(),
        )
        if not pipeline.available_for(request):
            return block.model_copy(
                update={
                    "image_status": "failed",
                    "image_error": "所需图源尚未配置，请上传图片或检查配置",
                }
            )
        asset = None
        error_message = (
            "未找到描述匹配的真实照片，请搜索候选或上传图片"
            if request.require_real else "配图未成功，图源可能超时或不可用，请重试"
        )
        for attempt in range(max(1, min(attempts, 2))):
            current_request = request.model_copy(update={
                "prompt": request.prompt + (
                    "保持相同主体与风格，换一个清晰视角，避免重复画面。" if attempt else ""
                ),
            })
            try:
                asset = await pipeline.fetch(current_request)
                if asset is None:
                    continue
                extension, _content_type = validate_image(asset.data)
                asset_id = (
                    f"sha256:{sha256(asset.data).hexdigest()}"
                    if asset.source == "generated" or not asset.asset_id else asset.asset_id
                )
                if asset_id in request.excluded_ids or (
                    asset.source == "generated" and reserve and not await reserve(asset_id)
                ):
                    error_message = "图源返回了重复图片，请重试或上传其他图片"
                    asset = None
                    continue
                break
            except (ImageFetchError, ImageRejected) as error:
                error_message = str(error)
                asset = None
        if asset is None:
            return block.model_copy(update={
                "image_status": "failed", "image_error": error_message,
            })
        key = store_image(
            user_id=user_id,
            project_id=project_id,
            data=asset.data,
            extension=extension,
        )
        return block.model_copy(
            update={
                "url": media_url(key),
                "source": asset.source,
                "credit": asset.credit,
                "credit_url": asset.credit_url,
                "image_asset_id": asset_id,
                "image_status": "ready",
                "image_error": None,
                "image_job_id": None,
                "image_job_started_at": None,
            }
        )
    except ImageFetchError as error:
        return block.model_copy(update={"image_status": "failed", "image_error": str(error)})
    except Exception as error:
        # 一张图不该让整页失败：校验、存储、甚至意外异常都只降级到占位
        logger.warning("image resolution failed type=%s", type(error).__name__)
        return block.model_copy(
            update={"image_status": "failed", "image_error": "图片校验或保存失败，请重试或上传图片"}
        )
