"""Check the same content in every theme, in the browser and native PPTX export.

Run against a local Vite dev server: uv run python scripts/check_theme_layouts.py
All requests are isolated fixture previews; no saved projects are changed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

from app.domain.card_layout import card_grid
from app.domain.content import (
    BulletsBlock,
    CardItem,
    CardsBlock,
    Deck,
    DiagramBlock,
    Slide,
    TextBlock,
)
from app.domain.content_pagination import split_generated_slide
from app.domain.diagram_layout import parse_mermaid
from app.domain.enterprise_layout import compose_report_slide
from app.domain.flex_layout import FlexContainer, FlexLeaf
from app.domain.generated_layout import normalize_generated_diagrams
from app.domain.outline import OutlinePageDraft
from app.domain.theme import load_themes
from app.domain.theme_layout import reflow_slide_to_theme
from app.domain.validation import validate_slide
from app.render.pptx import render_deck_to_pptx
from app.render.verify import verify_pptx


def fixture_slide(count: int, *, split: bool = False, long_title: bool = False) -> Slide:
    cards = CardsBlock(
        id="cards",
        slot_id="body",
        items=[
            CardItem(
                title=f"任务 {index + 1}：持续改进"
                if not long_title
                else "在真实工作任务中明确练习目标并持续记录结果与改进反馈",
                desc="在真实任务中练习，结合测试结果记录反馈并改进。",
            )
            for index in range(count)
        ],
    )

    title = TextBlock(id="title", slot_id="title", text="把工作任务变成刻意练习")
    body = BulletsBlock(
        id="body",
        slot_id="body",
        items=[
            "明确练习目标，记录完成结果。",
            "根据反馈调整下一次任务。",
        ],
    )
    main = FlexLeaf(id="cards-leaf", block_id="cards", grow=1)
    blocks = [title, cards]
    if split:
        main = FlexContainer(
            type="row",
            id="main",
            ratios=[67, 33],
            gap_pt=16,
            children=[FlexLeaf(id="body-leaf", block_id="body", text_style="bullet"), main],
        )
        blocks.append(body)
    return Slide(
        id=f"cards-{count}-{split}",
        layout_id="bullets",
        layout_mode="flex",
        blocks=blocks,
        layout_tree=FlexContainer(
            type="column",
            id="root",
            gap_pt=16,
            children=[
                FlexLeaf(id="title-leaf", block_id="title", text_style="title"),
                main,
            ],
        ),
    )


FLOW_SOURCES = [
    "flowchart LR\n A[接收请求] --> B[处理任务] --> C[完成交付]",
    "flowchart TB\n A{条件是否满足} -->|通过| B[继续处理]\n A -->|未通过| C[退回修改]",
    "flowchart TB\n A[接收任务] --> B[校验资料]\n A --> C[查询结果]\n B --> D[汇总结果]\n C --> D",
    "flowchart LR\n A[执行任务] --> B{结果是否通过}\n B -->|重试| A\n B -->|通过| C[完成]",
]


def flow_slide(source: str, index: int) -> Slide:
    nodes, edges, direction = parse_mermaid(source)
    return Slide(
        id=f"flow-{index}",
        layout_id="bullets",
        layout_mode="flex",
        blocks=[
            DiagramBlock(
                id="flow",
                slot_id="visual",
                diagram_type="flow",
                nodes=nodes,
                edges=edges,
                direction=direction,
            )
        ],
        layout_tree=FlexContainer(
            id="root", type="column", children=[FlexLeaf(id="leaf", block_id="flow")]
        ),
    )


async def check(url: str, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    report = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            for theme in load_themes().values():
                slides = [
                    reflow_slide_to_theme(fixture_slide(count, split=split), theme)
                    for count, split in [(3, False), (6, False), (2, True)]
                ]
                slides.append(reflow_slide_to_theme(fixture_slide(3, long_title=True), theme))
                slides.extend(
                    reflow_slide_to_theme(flow_slide(source, i), theme)
                    for i, source in enumerate(FLOW_SOURCES)
                )
                cases = json.loads(
                    (
                        Path(__file__).parents[1] / "tests/fixtures/generated_format_slides.json"
                    ).read_text(encoding="utf-8")
                )
                for case in cases:
                    generated = normalize_generated_diagrams(Slide.model_validate(case["slide"]))
                    plan = OutlinePageDraft.model_validate(case["plan"])
                    if plan.page_role == "toc":
                        generated = compose_report_slide(generated, plan)
                    slides.extend(split_generated_slide(generated, theme))
                for slide in slides:
                    issues = [
                        i
                        for i in validate_slide(slide, theme=theme)
                        if i.code == "overflow" or i.severity == "error"
                    ]
                    assert not issues, (theme.id, slide.id, issues)
                deck = Deck(
                    id="theme-layout-check", title="主题排版检查", theme_id=theme.id, slides=slides
                )
                pptx = render_deck_to_pptx(deck)
                verified = verify_pptx(pptx, deck)
                assert verified.passed, (theme.id, verified.issues)
                (output / f"{theme.id}.pptx").write_bytes(pptx.getvalue())
                (output / f"{theme.id}.json").write_text(
                    deck.model_dump_json(indent=2), encoding="utf-8"
                )
                for width in (1280, 390):
                    page = await browser.new_page(viewport={"width": width, "height": 900})
                    errors = []
                    page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
                    await page.route(
                        "**/shared/financial-tech-sample.json*",
                        preview_route(deck),
                    )
                    await page.goto(f"{url}/themes/{theme.id}")
                    await page.locator("section > [data-slide-canvas]").wait_for()
                    await page.evaluate("document.fonts.ready")
                    for index in range(len(slides)):
                        await page.get_by_role(
                            "button", name=f"第 {index + 1} 页", exact=True
                        ).click()
                        canvas = page.locator("section > [data-slide-canvas]")
                        for editing in (False, True):
                            await page.get_by_role("checkbox", name="编辑", exact=True).set_checked(
                                editing
                            )
                            failures = await canvas.locator("[data-card-grid]").evaluate_all("""
                            grids => {
                              const bad = [];
                              for (const grid of grids) for (const card of grid.children) {
                                for (const el of [card, ...card.querySelectorAll('*')]) {
                                  if (el.scrollHeight > el.clientHeight + 2 && el.clientHeight > 0)
                                    bad.push({text: el.textContent, height: el.clientHeight,
                                      needed: el.scrollHeight});
                                }
                              }
                              return bad;
                            }""")
                            assert not failures, (theme.id, width, index, editing, failures)
                            clipped_text = await canvas.locator("[data-block-id]").evaluate_all("""
                            blocks => blocks.flatMap(block => {
                              const bounds = block.getBoundingClientRect();
                              const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
                              const bad = [];
                              while (walker.nextNode()) {
                                const node = walker.currentNode;
                                if (!node.textContent.trim() || node.parentElement.closest('svg'))
                                  continue;
                                const range = document.createRange();
                                range.selectNodeContents(node);
                                for (const r of range.getClientRects()) {
                                  if (r.left < bounds.left-2 || r.right > bounds.right+2 ||
                                      r.top < bounds.top-2 || r.bottom > bounds.bottom+2) {
                                    bad.push(node.textContent);
                                    break;
                                  }
                                }
                              }
                              return bad;
                            })""")
                            assert not clipped_text, (theme.id, width, index, editing, clipped_text)
                            clipped_headers = await canvas.locator(
                                "[data-card-header]"
                            ).evaluate_all(
                                """headers => headers.flatMap(h => {
                                  const r = h.getBoundingClientRect();
                                  const safe = r.width * 0.06;
                                  return [...h.children].filter(c => {
                                    const b = c.getBoundingClientRect();
                                    return b.left < r.left+safe || b.right > r.right-safe;
                                  }).map(c => c.textContent);
                                })"""
                            )
                            assert not clipped_headers, (theme.id, width, index, clipped_headers)
                            if slides[index].blocks[0].type == "diagram":
                                block = slides[index].blocks[0]
                                diagram = canvas.locator('[data-diagram-engine="elk"]')
                                await diagram.wait_for()
                                assert await diagram.locator("[data-node-id]").count() == len(
                                    block.nodes
                                )
                                assert await diagram.locator("[data-edge-index]").count() == len(
                                    block.edges
                                )
                                actual = await diagram.locator(
                                    "[data-node-id] > rect"
                                ).evaluate_all(
                                    """nodes => nodes.map(n =>
                                      ['x','y','width','height'].map(k => +n.getAttribute(k)))"""
                                )
                                expected_nodes = [
                                    [n.x, n.y, n.width, n.height] for n in block.geometry.nodes
                                ]
                                for a, e in zip(actual, expected_nodes, strict=True):
                                    assert all(abs(x - y) < 0.01 for x, y in zip(a, e, strict=True))
                                overflow = await diagram.locator("[data-node-id]").evaluate_all("""
                                nodes => nodes.flatMap(n => {
                                  const r = n.querySelector('rect').getBBox();
                                  return [...n.querySelectorAll('text')].filter(t => {
                                    const b = t.getBBox();
                                    return b.x < r.x - 1 || b.y < r.y - 1
                                      || b.x+b.width > r.x+r.width+1
                                      || b.y+b.height > r.y+r.height+1;
                                  }).map(t => t.textContent);
                                })""")
                                assert not overflow, (theme.id, width, index, overflow)
                        await canvas.screenshot(
                            path=str(output / f"{theme.id}-{width}-{index + 1}.png")
                        )
                        grid = canvas.locator("[data-card-grid]")
                        if not await grid.count():
                            continue
                        actual_columns = await grid.evaluate(
                            "el => getComputedStyle(el).gridTemplateColumns.split(' ').length"
                        )
                        block = next(b for b in slides[index].blocks if b.type == "cards")
                        bounds = await grid.bounding_box()
                        canvas_bounds = await canvas.bounding_box()
                        expected, _, _ = card_grid(
                            len(block.items),
                            bounds["width"] / canvas_bounds["width"] * 960,
                            bounds["height"] / canvas_bounds["height"] * 540,
                            visual_style=theme.visual_style,
                        )
                        assert actual_columns == expected, (theme.id, actual_columns, expected)
                    assert not errors, errors
                    report.append(
                        {
                            "theme": theme.id,
                            "viewport": width,
                            "slides": len(slides),
                            "editable_and_readonly": "passed",
                            "pptx": "passed",
                        }
                    )
                    await page.close()
            await check_failed_draft(browser, url, slides[-1], output)
        finally:
            await browser.close()
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"Passed: {len(report)} theme/viewport cases; editable, readonly and native PPTX. {output}"
    )


async def check_failed_draft(browser, url: str, source: Slide, output: Path) -> None:
    """A format failure must leave a visible draft and a working retry action."""
    draft = {
        **source.model_dump(mode="json"),
        "status": "failed",
        "revision": 1,
        "title": "保留的草稿",
        "error": "页面尚未通过格式验收，草稿已保留。",
        "issues": [],
    }
    for width in (1280, 390):
        page = await browser.new_page(viewport={"width": width, "height": 900})
        errors = []
        retried = []
        page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))

        async def retry(route, *, retried=retried):
            retried.append(route.request.method)
            await route.fulfill(status=202, json={})

        await page.route("**/api/v1/projects/draft-check/deck/slides/*/retry", retry)
        await page.goto(f"{url}/themes/enterprise")
        await page.evaluate(
            """async draft => {
            const React = (await import('/node_modules/.vite/deps/react.js')).default;
            const client = await import('/node_modules/.vite/deps/react-dom_client.js');
            const { createRoot } = client.default;
            const moduleText = await (await fetch('/src/features/deck/api.ts')).text();
            const queryUrl = moduleText.match(/from "([^"]*@tanstack_react-query[^"]*)"/)[1];
            const query = await import(queryUrl);
            const { QueryClient, QueryClientProvider } = query;
            const { SlidePage } = await import('/src/features/deck/SlidePage.tsx');
            const { getTheme } = await import('/src/render/design.ts');
            const host = document.createElement('div');
            host.style.cssText = 'width:min(960px,100%);margin:24px auto';
            document.body.replaceChildren(host);
            createRoot(host).render(React.createElement(QueryClientProvider,
                { client: new QueryClient() },
                React.createElement(SlidePage, {
                    projectId: 'draft-check', slide: draft, theme: getTheme('enterprise'),
                    locked: false, zoom: 1, index: 0, total: 1, active: true,
                    selectedBlockId: null, onSelectBlock: () => {},
                    onOpenRelayout: () => {}, bindEl: () => {},
                })));
        }""",
            draft,
        )
        try:
            await page.get_by_role("alert").filter(has_text="草稿已保留").wait_for(timeout=10000)
        except Exception as error:
            raise RuntimeError(f"Draft preview failed: {errors}") from error
        assert await page.locator("[data-slide-canvas] [data-block-id]").count() == len(
            source.blocks
        )
        assert not await page.locator('[contenteditable="true"]').count()
        await page.screenshot(path=str(output / f"failed-draft-{width}.png"))
        await page.get_by_role("button", name="重试这一页", exact=True).click()
        await page.wait_for_function("!document.querySelector('button:disabled')")
        assert retried == ["POST"]
        assert not errors, errors
        await page.close()


def preview_route(deck: Deck):
    payload = f"export default {deck.model_dump_json()}"

    async def handler(route):
        await route.fulfill(content_type="application/javascript", body=payload)

    return handler


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:39173")
    parser.add_argument("--output", type=Path, default=Path("var/theme-layout-qa"))
    args = parser.parse_args()
    asyncio.run(check(args.url.rstrip("/"), args.output.resolve()))
