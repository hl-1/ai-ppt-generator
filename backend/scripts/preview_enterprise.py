"""Exercise the production slide workflow and PPTX renderer with labelled synthetic data.

Run from backend: uv run python scripts/preview_enterprise.py
No LLM, database, remote media or customer data is used.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.content import Deck  # noqa: E402
from app.domain.outline import DeckBlueprint, EvidenceItem  # noqa: E402
from app.domain.slide_draft import FlexSlideDraft  # noqa: E402
from app.domain.theme import get_theme  # noqa: E402
from app.llm.base import OutlineSourceSection, SlideGenerationInput  # noqa: E402
from app.render.pptx import render_deck_to_pptx  # noqa: E402
from app.render.verify import verify_pptx  # noqa: E402
from app.workflows.slide import build_slide_workflow, run_slide_workflow  # noqa: E402


def text(block_id, value):
    return {"id": block_id, "type": "text", "text": value}


def cards(items):
    return {
        "id": "cards",
        "type": "cards",
        "items": [{"title": title, "desc": desc} for title, desc in items],
    }


def evidence(metric, value, unit, period):
    return EvidenceItem(
        source_ref="S1:1",
        metric=metric,
        value=value,
        unit=unit,
        period=period,
        scope="示例业务",
        quote=f"{period}示例业务{metric}{value}{unit}。",
    )


TREND = [
    evidence("收入", value, "万元", period)
    for value, period in [("820", "第一季度"), ("950", "第二季度"), ("1080", "第三季度")]
]
METRICS = [
    TREND[-1],
    evidence("毛利率", "38", "%", "第三季度"),
    evidence("续约率", "91", "%", "第三季度"),
]
PAGES = [
    (
        "季度经营复盘与下一步决策",
        "cover",
        "narrative",
        [
            text("subtitle", "业务增长与交付能力建设"),
            text("meta", "管理层汇报 · 演示样例 · 全部数字为合成测试数据"),
        ],
        [],
    ),
    (
        "增长已形成，下一阶段聚焦交付质量",
        "executive_summary",
        "narrative",
        [
            cards(
                [
                    ("经营结果", "收入连续提升，经营质量仍需与规模增长同步观察。"),
                    ("核心约束", "交付标准尚未统一，跨团队协同仍是下一阶段重点。"),
                    ("建议动作", "先开展标准化交付试点，再依据验收结果决定推广范围。"),
                ]
            )
        ],
        [],
    ),
    (
        "收入持续提升，增长质量需同步跟踪",
        "performance",
        "trend",
        [
            text("insight", "收入逐季提升\n\n建议结合毛利率和客户续约情况评估增长质量。"),
        ],
        TREND,
    ),
    (
        "收入、毛利与续约共同衡量经营质量",
        "performance",
        "kpi",
        [
            text("insight", "三个指标分别反映规模、盈利与客户关系；后续持续按相同口径跟踪。"),
        ],
        METRICS,
    ),
    (
        "标准化试点更适合当前的能力建设阶段",
        "driver",
        "comparison",
        [
            cards([("全面推广", "覆盖范围广，但对交付标准和组织协同的要求较高。")]),
            {
                "id": "option-b",
                "type": "cards",
                "items": [
                    {
                        "title": "先行试点 · 建议",
                        "desc": "先验证流程与验收标准，再根据结果分阶段推广。",
                    }
                ],
            },
        ],
        [],
    ),
    (
        "优先管理交付一致性与范围扩张风险",
        "risk",
        "narrative",
        [
            cards(
                [
                    (
                        "交付一致性",
                        "风险：不同团队执行标准不一。\n应对：统一验收清单与例外处理流程。",
                    ),
                    (
                        "范围扩张",
                        "风险：推广节奏超过当前承载能力。\n应对：设置试点退出条件与复盘节点。",
                    ),
                ]
            )
        ],
        [],
    ),
    (
        "以试点验收结果作为推广的前置条件",
        "action",
        "timeline",
        [
            text("step1", "明确标准\n梳理输入、交付物和验收要求。"),
            text("step2", "执行试点\n记录流程偏差与客户反馈。"),
            text("step3", "复盘决策\n依据验收结果确定后续推广范围。"),
        ],
        [],
    ),
    (
        "行动计划明确交付物，责任与期限待确认",
        "action",
        "actions",
        [
            {
                "id": "actions",
                "type": "table",
                "header": ["行动", "交付物", "负责人", "期限"],
                "rows": [
                    ["统一验收标准", "验收清单", "待确定", "待确定"],
                    ["开展交付试点", "试点记录", "待确定", "待确定"],
                    ["组织阶段复盘", "推广建议", "待确定", "待确定"],
                ],
            }
        ],
        [],
    ),
    (
        "建议批准试点方向，推广范围另行评审",
        "decision",
        "narrative",
        [
            cards(
                [
                    ("本次决策", "确认先试点、再评审的推进方向。"),
                    ("决策依据", "在扩大覆盖前，先验证交付标准和执行条件。"),
                    ("后续确认", "负责人、试点范围与资源投入由管理层进一步明确。"),
                ]
            )
        ],
        [],
    ),
]


class FixtureGenerator:
    def __init__(self, draft):
        self.draft = draft

    async def generate(self, payload):
        return self.draft


async def main():
    output = Path(__file__).resolve().parents[1] / "var" / "enterprise-qa"
    output.mkdir(parents=True, exist_ok=True)
    for theme_id in ("enterprise", "enterprise-dark"):
        slides, issues = [], []
        for index, (title, role, kind, body, facts) in enumerate(PAGES, 1):
            blocks = [text("title", title), *body]
            draft = FlexSlideDraft.model_validate(
                {
                    "blocks": blocks,
                    "layout_tree": {
                        "type": "column",
                        "id": "root",
                        "children": [
                            {
                                "type": "block",
                                "id": f"leaf-{b['id']}",
                                "block_id": b["id"],
                                "text_style": "title" if b["id"] == "title" else "body",
                            }
                            for b in blocks
                        ],
                    },
                    "speaker_notes": "这是合成测试样例，内容不代表任何真实企业经营情况。",
                }
            )
            payload = SlideGenerationInput(
                deck_title="经营汇报演示（合成数据）",
                tone="professional",
                position=index,
                total_pages=len(PAGES),
                page_title=title,
                objective=title,
                key_points=["核心判断", "支撑与行动"],
                key_message=title,
                layout_id="bullets",
                narrative_role=role,
                evidence_kind=kind,
                evidence=facts,
                page_role="cover" if role == "cover" else "content",
                blueprint=DeckBlueprint(core_message="以交付标准化支撑增长质量"),
                sections=[
                    OutlineSourceSection(
                        ref="S1:1",
                        heading="合成测试数据",
                        level=0,
                        locator="演示材料",
                        text="".join(e.quote for e in facts),
                    )
                ],
            )
            slide, found = await run_slide_workflow(
                build_slide_workflow(FixtureGenerator(draft)),
                payload,
                uuid.uuid5(uuid.NAMESPACE_URL, f"enterprise-qa/{index}"),
                theme_id=theme_id,
            )
            slides.append(slide)
            issues.extend(i.model_dump() for i in found)
        deck = Deck(
            id="enterprise-qa", title="经营汇报演示（合成数据）", theme_id=theme_id, slides=slides
        )
        data = render_deck_to_pptx(deck, theme=get_theme(theme_id)).getvalue()
        verified = verify_pptx(data, deck)
        (output / f"{theme_id}.pptx").write_bytes(data)
        (output / f"{theme_id}.json").write_text(deck.model_dump_json(indent=2), encoding="utf-8")
        (output / f"{theme_id}-checks.json").write_text(
            json.dumps(
                {
                    "issues": issues,
                    "pptx": verified.model_dump(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(
            f"{theme_id}: {len(slides)} pages, PPTX verified={verified.passed}, "
            f"errors={sum(i['severity'] == 'error' for i in issues)}"
        )
        if not verified.passed or any(i["severity"] == "error" for i in issues):
            raise SystemExit("Sample quality checks failed; inspect checks.json")


if __name__ == "__main__":
    asyncio.run(main())
