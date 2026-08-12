import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.v1.deck._shared import SessionDep, _commit_slide_edit, _ensure_editable, _find_slide
from app.api.v1.projects import OwnedProject
from app.domain.flex_layout import FlexContainer
from app.domain.slide_patch import (
    apply_patches,
    content_snapshot,
    filter_patches,
    unlocked_editable_blocks,
)
from app.llm.base import SlideEditInput
from app.llm.errors import InvalidSlideEditOutputError, LLMNotConfiguredError
from app.llm.slide_edit import block_to_edit_input
from app.schemas.deck import (
    AiEditApplyRequest,
    AiEditOperationPublic,
    AiEditProposalPublic,
    AiEditRequest,
    DiscardedOperationPublic,
    SlidePublic,
)
from app.services.deck import load_slides
from app.worker.context import create_slide_edit_generator
from app.workflows.slide_edit import (
    build_slide_edit_workflow,
    parse_slide_blocks,
    run_slide_edit_workflow,
)

router = APIRouter(prefix="/projects/{project_id}/deck", tags=["deck"])


@router.post(
    "/slides/{slide_id}/ai-edit",
    response_model=AiEditProposalPublic,
)
async def propose_slide_ai_edit(
    slide_id: uuid.UUID,
    body: AiEditRequest,
    project: OwnedProject,
    session: SessionDep,
) -> AiEditProposalPublic:
    slides = await load_slides(session, project.id)
    slide = _find_slide(slides, slide_id)
    _ensure_editable(slide, body.revision)

    blocks = parse_slide_blocks(slide.blocks)
    editable = unlocked_editable_blocks(blocks)
    if not editable:
        return AiEditProposalPublic(
            revision=slide.revision,
            operations=[],
            discarded=[],
            warnings=[],
        )

    instruction = body.instruction.strip() if body.instruction else None
    layout_tree = (
        FlexContainer.model_validate(slide.layout_tree)
        if slide.layout_mode == "flex" and slide.layout_tree is not None
        else None
    )
    payload = SlideEditInput(
        deck_title=project.title,
        audience=project.audience,
        tone=project.tone,
        page_title=slide.title,
        layout_id=slide.layout_id,
        layout_mode=slide.layout_mode,
        action=body.action,
        instruction=instruction or None,
        blocks=[block_to_edit_input(block) for block in editable],
    )

    workflow = build_slide_edit_workflow(create_slide_edit_generator())
    try:
        operations, discarded, issues, _patched = await run_slide_edit_workflow(
            workflow,
            payload=payload,
            slide_id=str(slide.id),
            layout_id=slide.layout_id,
            layout_mode=slide.layout_mode,
            layout_tree=layout_tree,
            blocks=blocks,
            theme_id=project.theme_id,
            theme_overrides=dict(project.theme_overrides or {}),
        )
    except LLMNotConfiguredError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except InvalidSlideEditOutputError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    by_id = {block.id: block for block in blocks}
    preview: list[AiEditOperationPublic] = []
    for op in operations:
        block = by_id[op.block_id]
        preview.append(
            AiEditOperationPublic(
                block_id=op.block_id,
                slot_id=block.slot_id,
                type=op.type,
                before=content_snapshot(block),
                after=op,
            )
        )

    return AiEditProposalPublic(
        revision=slide.revision,
        operations=preview,
        discarded=[
            DiscardedOperationPublic(block_id=item.block_id, reason=item.reason)
            for item in discarded
        ],
        warnings=[issue for issue in issues if issue.severity == "warning"],
    )


@router.post(
    "/slides/{slide_id}/ai-edit/apply",
    response_model=SlidePublic,
)
async def apply_slide_ai_edit(
    slide_id: uuid.UUID,
    body: AiEditApplyRequest,
    project: OwnedProject,
    session: SessionDep,
) -> SlidePublic:
    slides = await load_slides(session, project.id)
    slide = _find_slide(slides, slide_id)
    _ensure_editable(slide, body.revision)

    blocks = parse_slide_blocks(slide.blocks)
    filtered = filter_patches(blocks, list(body.operations))
    patched = apply_patches(blocks, filtered.accepted)
    # AI 改过的块不置 locked：locked 表示「人工修改过」；若 AI 也置位，
    # 一页被 AI 改过后就再也改不动了。
    slide.blocks = [block.model_dump(mode="json") for block in patched]
    return await _commit_slide_edit(session, project, slide)
