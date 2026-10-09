"""Exercise live travel research, deterministic pages, PPTX and browser rendering."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

import httpx
from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.domain.content import Deck  # noqa: E402
from app.domain.export_check import run_export_check  # noqa: E402
from app.domain.theme import resolve_theme  # noqa: E402
from app.llm.base import OutlineGenerationInput, SlideGenerationInput  # noqa: E402
from app.llm.client import StructuredChatClient, create_chat_model  # noqa: E402
from app.llm.slide import DeepSeekSlideGenerator  # noqa: E402
from app.render.pptx import render_deck_to_pptx  # noqa: E402
from app.render.verify import verify_pptx  # noqa: E402
from app.schemas.travel import ResearchData, TravelConditions  # noqa: E402
from app.services.media import load_image, media_key_from_url  # noqa: E402
from app.services.travel_assets import collect_travel_assets  # noqa: E402
from app.services.travel_outline import build_travel_outline, travel_coverage_issues  # noqa: E402
from app.services.travel_planning import (  # noqa: E402
    build_travel_plan,
    travel_context,
    validate_facts,
)
from app.services.travel_providers import TravelProviders  # noqa: E402
from app.services.travel_research import extract_source_facts, source_ticket_facts  # noqa: E402
from app.workflows.slide import build_slide_workflow, run_slide_workflow  # noqa: E402


class SavedDataOnly:
    async def complete(self, *args, **kwargs):
        raise RuntimeError("Travel page unexpectedly requested model generation")


async def browser_check(deck, url, output):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        async def serve_media(route):
            key = media_key_from_url(route.request.url.split(url.rstrip("/"), 1)[-1])
            await route.fulfill(
                body=load_image(key),
                content_type="image/png" if key.endswith(".png") else "image/jpeg",
            )

        await page.route("**/api/v1/media/**", serve_media)
        await page.goto(url, wait_until="networkidle")
        await page.evaluate(
            """async (deck) => {
            const React = (await import('/node_modules/.vite/deps/react.js')).default;
            const Client = await import('/node_modules/.vite/deps/react-dom_client.js');
            const { createRoot } = Client.default;
            const { SlideView } = await import('/src/render/SlideView.tsx');
            const { getTheme } = await import('/src/render/design.ts');
            const gallery = document.createElement('div');
            gallery.id = 'travel-smoke-gallery';
            Object.assign(gallery.style, { width: 'min(960px, 100%)', margin: '0 auto' });
            document.body.replaceChildren(gallery);
            const theme = getTheme(deck.theme_id);
            createRoot(gallery).render(React.createElement(React.Fragment, null,
                ...deck.slides.map((slide, index) => React.createElement('section', {
                    key: slide.id, 'data-page': index + 1, style: { marginBottom: 24 }
                }, React.createElement(SlideView, { slide, theme, slideIndex: index + 1 })))));
        }""",
            deck.model_dump(mode="json"),
        )
        try:
            await page.locator("[data-page]").last.wait_for(timeout=10000)
        except Exception as error:
            raise RuntimeError(f"Slide gallery failed: {errors}") from error
        await page.wait_for_function(
            "[...document.querySelectorAll('#travel-smoke-gallery img')].every(img => img.complete)"
        )
        await page.evaluate("document.fonts.ready")
        checks = []
        for width, name in ((1440, "desktop"), (390, "mobile")):
            await page.set_viewport_size({"width": width, "height": 1000})
            await page.locator("[data-page='1']").screenshot(path=str(output / f"cover-{name}.png"))
            for index in range(1, len(deck.slides) + 1):
                await page.locator(f"[data-page='{index}']").screenshot(
                    path=str(output / f"page-{index}-{name}.png")
                )
            checks.append(
                await page.evaluate("""() => ({
                width: innerWidth, pageCount: document.querySelectorAll('[data-page]').length,
                horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
                brokenImages: [...document.querySelectorAll('#travel-smoke-gallery img')]
                    .filter(img => !img.naturalWidth).length
            })""")
            )
        await browser.close()
        return {"viewports": checks, "errors": errors}


async def browser_check_ui(deck, data, outline, url, output):
    project_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    project = {
        "id": project_id,
        "title": deck.title,
        "tone": "professional",
        "audience": None,
        "page_count": len(deck.slides),
        "theme_id": deck.theme_id,
        "theme_overrides": {},
        "layout_mode": deck.slides[0].layout_mode,
        "content_density": "medium",
        "status": "ready",
        "created_at": now,
        "updated_at": now,
        "sources": [],
        "report_brief": {"scenario": "travel_plan", "goal": "", "decision_request": ""},
        "travel_conditions": data.plan.conditions.model_dump(mode="json"),
    }
    research = {
        "id": str(uuid.uuid4()),
        "version": 1,
        "status": "partial",
        "stale": False,
        "progress": 100,
        "stage": "资料查询部分完成",
        "error_code": None,
        "conditions": project["travel_conditions"],
        "data": data.model_dump(mode="json"),
        "created_at": now,
        "completed_at": now,
    }
    public_deck = {
        "project_id": project_id,
        "title": deck.title,
        "theme_id": deck.theme_id,
        "status": "ready",
        "total": len(deck.slides),
        "ready": len(deck.slides),
        "failed": 0,
        "slides": [
            {
                **slide.model_dump(mode="json"),
                "status": "ready",
                "position": index,
                "title": outline.pages[index - 1].title,
                "revision": 1,
                "updated_at": now,
                "issues": [],
                "error": None,
                "outline_page_id": str(uuid.uuid4()),
            }
            for index, slide in enumerate(deck.slides, 1)
        ],
    }
    submissions, errors = [], []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.add_init_script("localStorage.setItem('aippt.token', 'local-ui-smoke')")

        async def mock_api(route):
            path = urlparse(route.request.url).path.removeprefix("/api/v1")
            if path.startswith("/media/"):
                key = media_key_from_url(urlparse(route.request.url).path)
                await route.fulfill(body=load_image(key), content_type="image/png")
                return
            if path == "/auth/me":
                response = {"id": str(uuid.uuid4()), "email": "travel-smoke@example.com"}
            elif path == "/projects" and route.request.method == "POST":
                submissions.append(route.request.post_data_json)
                response = project
            elif path == "/projects":
                response = []
            elif path == f"/projects/{project_id}":
                response = project
            elif path.endswith("/sources"):
                response = {"id": str(uuid.uuid4())}
            elif path.endswith("/outline/generate"):
                response = {"job_id": "local-smoke", "status": "generating"}
            elif path.endswith("/outline"):
                response = {"status": "confirmed", "pages": [], "revision": 1}
            elif path.endswith("/travel/research"):
                response = research
            elif path.endswith("/deck"):
                response = public_deck
            else:
                errors.append(f"Unexpected UI request: {path}")
                await route.fulfill(status=404, json={"detail": "Unexpected smoke endpoint"})
                return
            await route.fulfill(json=response)

        await page.route("**/api/v1/**", mock_api)
        await page.goto(url.rstrip("/") + "/create")
        await page.get_by_label("内容分类", exact=True).select_option("travel_plan")
        await page.get_by_placeholder("例如：春节去北京旅游规划，重点安排景点、交通和住宿").fill(
            "北京旅游规划"
        )
        await page.get_by_label("目的地", exact=True).fill("北京")
        await page.get_by_label("出发城市", exact=True).fill("上海")
        await page.get_by_label("房间数", exact=True).fill("2")
        await page.get_by_label("每日餐饮预算", exact=True).fill("80")
        await page.get_by_label("团队备用金", exact=True).fill("500")
        await page.get_by_label("必去地点", exact=True).press_sequentially(
            "故宫，天坛，颐和园，景山，北海，八达岭，圆明园，恭王府"
        )
        await page.get_by_label("查询视频攻略", exact=True).uncheck()
        await page.get_by_label("确认旅行条件", exact=True).check()
        await page.get_by_text("13 页", exact=False).first.wait_for()
        views = []
        for width, name in ((1440, "desktop"), (390, "mobile")):
            await page.set_viewport_size({"width": width, "height": 1000})
            await page.screenshot(path=str(output / f"create-{name}.png"), full_page=True)
            views.append(await page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        await page.get_by_role("button", name="生成大纲", exact=True).click()
        await page.wait_for_url(f"**/projects/{project_id}")
        await page.get_by_text("项资料待确认", exact=False).wait_for()
        assert submissions[0]["page_count"] == 13
        submitted = submissions[0]["travel_conditions"]
        assert len(submitted["must_visit"]) == 8
        assert submitted["room_count"] == 2 and submitted["meal_budget_per_day"] == 80
        assert submitted["contingency"] == 500
        assert await page.get_by_role("button", name="取消生成", exact=True).count() == 0
        assert await page.get_by_role("button", name="导出", exact=True).is_enabled()
        for width, name in ((1440, "desktop"), (390, "mobile")):
            await page.set_viewport_size({"width": width, "height": 1000})
            await page.screenshot(path=str(output / f"result-{name}.png"))
            views.append(await page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            if width == 390:
                assert await page.locator("main [data-slide-id]").first.evaluate(
                    "element => element.getBoundingClientRect().width > 280"
                )
        public_deck["slides"][0]["status"] = "failed"
        public_deck.update(status="partial", failed=1, ready=len(deck.slides) - 1)
        research["status"] = "failed"
        await page.reload()
        await page.get_by_text("1 页失败", exact=True).wait_for()
        await page.get_by_text("资料查询失败", exact=False).wait_for()
        assert await page.get_by_role("button", name="继续生成", exact=True).is_visible()
        await browser.close()
    assert all(views) and not errors, {"viewports": views, "errors": errors}
    return {
        "create_and_result_no_horizontal_overflow": views,
        "errors": errors,
        "submission_and_failure_states": "passed",
    }


async def main(args):
    settings = get_settings()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    conditions = TravelConditions(
        origin="上海",
        destination="北京",
        must_visit=["故宫"],
        departure_date=args.departure,
        return_date=args.departure + timedelta(days=2),
        adults=2,
        budget=5000,
        confirmed=True,
        video_preferences={"enabled": False},
    )
    data = ResearchData()
    if args.resume:
        data = ResearchData.model_validate_json(
            (output / "research.json").read_text(encoding="utf-8")
        )
        conditions = data.plan.conditions
    async with httpx.AsyncClient(follow_redirects=False) as client:
        providers = TravelProviders(client, settings, data)
        if args.resume:
            return await render_saved_data(data, conditions, args, output)
        print("Querying live places, lodging and forecasts", flush=True)
        places, hotels = await asyncio.gather(
            providers.places("北京", "故宫", limit=1),
            providers.places("北京", "王府井 酒店", hotel=True, limit=2),
        )
        data.places, data.hotels = places, hotels
        await providers.weather(conditions, places[0].location if places else None)
        print("Querying official entry rules and recent references", flush=True)
        await asyncio.gather(
            providers.search("北京 故宫 官网 开放 门票 预约 身份证 入园", official=True),
            providers.search("北京 故宫 打卡 排队 餐饮 近期"),
            *(providers.search(f"北京 {hotel.name} 官网 房型 入住 房价 税费") for hotel in hotels),
        )
        if places:
            data.restaurants = await providers.places("北京", "餐厅", near=places[0], limit=2)
        sources = [source for source in data.sources if source.service == "firecrawl"]
        facts = [fact for source in sources for fact in source_ticket_facts(source)]
        if settings.llm_api_key and not args.skip_extraction:
            chat = StructuredChatClient(model=create_chat_model(), api_key=settings.llm_api_key)
            for source in sorted(sources, key=lambda source: source.trust != "official")[:4]:
                try:
                    async with asyncio.timeout(20):
                        facts.extend(await extract_source_facts(chat, source, conditions))
                except Exception as error:
                    print(f"Source extraction incomplete: {type(error).__name__}", flush=True)
        data.facts = validate_facts(facts, data, conditions)
        data.plan = build_travel_plan(data, conditions)
        print("Downloading sourced photos and route map", flush=True)
        await collect_travel_assets(
            providers, data.plan, user_id=uuid.uuid4(), project_id=uuid.uuid4()
        )
        data.services = providers.statuses()
        data.plan = build_travel_plan(data, conditions)
    await render_saved_data(data, conditions, args, output)


async def render_saved_data(data, conditions, args, output):
    data.facts = validate_facts(data.facts, data, conditions)
    data.plan = build_travel_plan(data, conditions)
    context = travel_context(
        SimpleNamespace(
            id=uuid.uuid4(),
            version=1,
            stale=False,
            status="partial",
            data=data.model_dump(mode="json"),
            conditions=conditions.model_dump(mode="json"),
        )
    )
    outline = build_travel_outline(
        OutlineGenerationInput(
            title="北京三日旅游规划", tone="professional", page_count=5, travel_context=context
        )
    )
    assert not travel_coverage_issues(outline.pages, context)
    workflow = build_slide_workflow(DeepSeekSlideGenerator(chat=SavedDataOnly()))
    slides, issues = [], []
    print(f"Rendering {len(outline.pages)} saved-data pages", flush=True)
    for position, page in enumerate(outline.pages, 1):
        slide, page_issues = await run_slide_workflow(
            workflow,
            SlideGenerationInput(
                travel_context=context,
                travel_page=page.travel_page,
                deck_title="北京三日旅游规划",
                tone="professional",
                position=position,
                total_pages=len(outline.pages),
                page_title=page.title,
                objective=page.objective,
                key_points=page.key_points,
                layout_id=page.layout_id,
                layout_mode=args.layout,
                page_role=page.page_role,
            ),
            uuid.uuid4(),
        )
        slides.append(slide)
        issues.extend(page_issues)
    deck = Deck(id="live-travel-smoke", title="北京三日旅游规划", theme_id="ivory", slides=slides)
    pptx = render_deck_to_pptx(deck).getvalue()
    verification = verify_pptx(pptx, deck)
    export = run_export_check(
        deck,
        theme=resolve_theme("ivory"),
        load_image=load_image,
        media_key_from_url=media_key_from_url,
    )
    (output / "travel.pptx").write_bytes(pptx)
    (output / "deck.json").write_text(deck.model_dump_json(indent=2), encoding="utf-8")
    (output / "research.json").write_text(data.model_dump_json(indent=2), encoding="utf-8")
    report = {
        "pages": len(slides),
        "images": len(data.images),
        "map": data.route_map.status,
        "services": [service.model_dump() for service in data.services],
        "pptx_verified": verification.passed,
        "export_allowed": export.export_allowed,
        "issues": [issue.model_dump() for issue in issues],
    }
    if args.ui_url:
        report["browser"] = await browser_check(deck, args.ui_url, output)
        report["ui"] = await browser_check_ui(deck, data, outline, args.ui_url, output)
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: report[key]
                for key in ("pages", "images", "map", "pptx_verified", "export_allowed")
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    print(f"Artifacts: {output}", flush=True)
    assert verification.passed and export.export_allowed
    assert not any(issue.code == "overflow" or issue.severity == "error" for issue in issues)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--departure", type=date.fromisoformat, default=date(2026, 10, 9))
    parser.add_argument("--output", default="var/travel-requirements-smoke")
    parser.add_argument("--layout", choices=["flex", "fixed"], default="flex")
    parser.add_argument("--skip-extraction", action="store_true")
    parser.add_argument("--ui-url")
    parser.add_argument(
        "--resume", action="store_true", help="Render saved research without network queries"
    )
    asyncio.run(main(parser.parse_args()))
