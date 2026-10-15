"""Inspect real renderer geometry using the repaired project's local fixture."""

import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path("var/visual-repair/6162531a-8914-43b2-a03c-92f844e7a98f")


async def main():
    fixture = (ROOT / "browser-preview.json").read_text(encoding="utf-8")
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(
            viewport={"width": 1440, "height": 1000}, device_scale_factor=1
        )
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.route(
            "**/__visual_fixture.json",
            lambda route: route.fulfill(content_type="application/json", body=fixture),
        )
        await page.goto("http://127.0.0.1:39173/.cache/visual-check.html")
        await page.wait_for_function("""() =>
          document.querySelectorAll('[data-diagram-engine="elk"]').length >= 3""")
        await page.evaluate("document.fonts.ready")
        for name, width in (("desktop", 1440), ("mobile", 390)):
            await page.set_viewport_size({"width": width, "height": 1000})
            await page.screenshot(path=str(ROOT / f"{name}-all.png"), full_page=True)
            for slide_id, kind in (
                ("048a32ff-cd14-49ce-8ccc-f1c07049e73f", "architecture"),
                ("b5884201-a00d-41da-88a6-3af518ccf010", "table"),
                ("6f8a4cfe-cd90-4ce4-b99f-170c212d4d18", "flow"),
                ("execution-flow-check", "execution"),
                ("48855ec6-3628-4840-a021-b5bcbad8d586", "rules"),
                ("612a1f56-24ac-4404-a263-5ec03ffe331b", "stages"),
            ):
                await page.locator(f'[data-slide="{slide_id}"]').screenshot(
                    path=str(ROOT / f"{name}-{kind}.png")
                )
            overflow = await page.evaluate("""() => [...document.querySelectorAll('th,td')]
              .filter(e => e.scrollWidth > e.clientWidth + 2 || e.scrollHeight > e.clientHeight + 2)
              .map(e => e.textContent)""")
            node_overflow = await page.evaluate("""() =>
              [...document.querySelectorAll('[data-node-id]')].flatMap(g => {
                const r = g.querySelector('rect').getBBox();
                return [...g.querySelectorAll('text')].filter(t => {
                  const b = t.getBBox();
                  return b.x < r.x - 0.5 || b.x + b.width > r.x + r.width + 0.5
                    || b.y < r.y - 0.5 || b.y + b.height > r.y + r.height + 0.5;
                }).map(t => ({ id: g.dataset.nodeId, text: t.textContent }));
              })""")
            print(
                json.dumps(
                    {
                        "viewport": name,
                        "table_overflow": overflow,
                        "node_overflow": node_overflow,
                        "errors": errors,
                    }
                )
            )
            assert not overflow and not node_overflow and not errors
        # Old diagrams without saved geometry, theme changes and inline editing use
        # the same renderer. Exercise each against the actual architecture fixture.
        architecture = next(
            s
            for s in json.loads(fixture)["slides"]
            if s["id"] == "048a32ff-cd14-49ce-8ccc-f1c07049e73f"
        )
        for block in architecture["blocks"]:
            if block["type"] == "diagram":
                block["geometry"] = None
        for theme in ("enterprise", "financial-tech"):
            await page.route(
                "**/__visual_fixture.json",
                lambda route, theme_id=theme: route.fulfill(
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "theme_id": theme_id,
                            "slides": [architecture],
                        }
                    ),
                ),
            )
            await page.set_viewport_size({"width": 1440, "height": 1000})
            await page.goto("http://127.0.0.1:39173/.cache/visual-check.html?editable=1")
            await page.wait_for_selector('[data-diagram-engine="elk"]')
            await page.evaluate("document.fonts.ready")
            colors = await page.evaluate("""() => ({
                background: document.querySelector('[data-flowchart-background]')
                  .getAttribute('fill'),
                nodes: document.querySelectorAll('[data-node-id]').length,
                failure: document.body.textContent.includes('流程图布局失败'),
            })""")
            assert colors["background"] == ("#0B1630" if theme == "financial-tech" else "#FFFFFF")
            assert colors["nodes"] == 9 and not colors["failure"]
            await page.locator("[data-slide]").screenshot(path=str(ROOT / f"fallback-{theme}.png"))
            editor = page.locator("[data-node-id] [contenteditable]").first
            await editor.click()
            await editor.fill("编辑完整节点说明")
            await page.locator("body").click(position={"x": 2, "y": 2})
            await page.wait_for_function("window.visualCommits?.length > 0")
            commit = await page.evaluate("window.visualCommits.at(-1)")
            assert commit[1]["nodes"][0]["title"] == "编辑完整节点说明"
            assert not errors
            print(json.dumps({"fallback_theme": theme, "inline_edit": True, **colors}))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
