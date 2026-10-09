import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import Settings
from app.domain.outline import OutlineDraft
from app.llm.base import OutlineGenerationInput, SlideGenerationInput
from app.schemas.travel import ResearchData, TravelConditions, TravelVideo, VideoSegment
from app.services.travel_outline import build_travel_outline
from app.services.travel_planning import build_travel_plan, travel_context
from app.services.travel_providers import TravelProviders
from app.services.travel_video import (
    AdviceSelections,
    VideoReader,
    apply_metadata,
    discover_videos,
    extract_video_advice,
    interaction_count,
    public_media_url,
    research_videos,
    select_videos,
    video_url,
)
from app.services.travel_video_extract import parse_subtitles


def video(identifier="7692431224540035506", **changes):
    values = {
        "id": f"douyin:{identifier}",
        "platform": "douyin",
        "url": f"https://www.douyin.com/video/{identifier}",
        "title": "北京住宿避坑",
        "retrieved_at": datetime.now(UTC),
        "published_at": datetime.now(UTC) - timedelta(days=10),
        "likes": 12000,
        "favorites": 1800,
        "duration_seconds": 120,
        "topics": ["住宿推荐 避坑"],
    }
    return TravelVideo(**{**values, **changes})


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1.5万", (15000, True)),
        ("6571", (6571, False)),
        ("2.3k", (2300, True)),
        ("1.2亿", (120000000, True)),
        ("收藏", (None, False)),
        (None, (None, False)),
        ("作者获赞5.5万", (None, False)),
        (-1, (None, False)),
        (True, (None, False)),
    ],
)
def test_counts_keep_unknown_and_distinguish_rounded_counts(value, expected):
    assert interaction_count(value) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://localhost/video/7692431224540035506",
        "https://www.douyin.com.evil.example/video/7692431224540035506",
        "https://user:password@www.douyin.com/video/7692431224540035506",
        "https://www.douyin.com:443/video/7692431224540035506",
        "https://www.douyin.com/search/北京旅游",
        "https://www.douyin.com:invalid/video/7692431224540035506",
    ],
)
def test_discovery_only_accepts_public_platform_video_links(url):
    assert video_url(url) is None


def test_media_urls_are_restricted_to_platform_cdn_hosts():
    assert public_media_url("https://v1.douyinvod.com/video.mp4")
    assert not public_media_url("https://127.0.0.1/video.mp4")
    assert not public_media_url("https://douyinvod.com.evil.example/video.mp4")


def test_popularity_is_or_and_never_infers_missing_metadata():
    videos = [
        video(str(7692431224540035506 + i), **changes)
        for i, changes in enumerate(
            [
                {"likes": 10000, "favorites": None},
                {"likes": 10, "favorites": 1000},
                {"likes": None, "favorites": None},
                {"likes": 9999, "favorites": 999},
                {"published_at": None},
                {"published_at": datetime.now(UTC) - timedelta(days=200)},
                {"title": "上海酒店"},
                {"duration_seconds": 3600},
            ]
        )
    ]
    selected = select_videos(videos, TravelConditions(destination="北京"), Settings())
    assert set(item.id for item in selected) == {videos[0].id, videos[1].id}
    assert [item.error_code for item in videos[2:]] == [
        "popularity_unknown",
        "below_popularity_threshold",
        "publication_unknown",
        "outside_date_range",
        "irrelevant_video",
        "video_too_long",
    ]


def test_author_total_is_not_video_popularity():
    item = video(likes=None, favorites=None)
    apply_metadata(item, {"author_likes": 999999, "likes": "收藏"})
    assert item.likes is None and item.favorites is None


@pytest.mark.parametrize(
    "duration,accepted", [(899, True), (900, True), (901, False), (None, False), (0, False)]
)
async def test_fifteen_minute_limit_cannot_be_relaxed_and_blocks_content(
    monkeypatch, duration, accepted
):
    from app.services import travel_video

    item = video(duration_seconds=duration)
    settings = Settings(travel_video_max_duration_seconds=3600)
    assert bool(select_videos([item], TravelConditions(destination="北京"), settings)) is accepted
    if not accepted:

        async def forbidden_worker(*args):
            pytest.fail("Excluded videos must not be read or transcribed")

        monkeypatch.setattr(travel_video, "run_video_worker", forbidden_worker)
        async with httpx.AsyncClient() as client:
            await VideoReader(TravelProviders(client, settings, ResearchData())).content(item)
        assert item.status == "rejected" and not item.selected and not item.segments


@pytest.mark.parametrize(
    "content,ext",
    [
        ('{"body":[{"from":1.5,"to":3,"content":"地铁附近住宿"}]}', "json"),
        (
            '{"events":[{"tStartMs":1500,"dDurationMs":1500,"segs":[{"utf8":"地铁附近住宿"}]}]}',
            "json3",
        ),
        ("1\n00:00:01,500 --> 00:00:03,000\n地铁附近住宿\n", "srt"),
        ("WEBVTT\n\n00:00:01.500 --> 00:00:03.000\n<b>地铁附近住宿</b>\n", "vtt"),
    ],
)
def test_subtitles_preserve_original_evidence_and_timestamp(content, ext):
    assert parse_subtitles(content, ext) == [{"start": 1.5, "end": 3.0, "text": "地铁附近住宿"}]


async def test_video_search_preserves_social_query_and_does_not_trust_excerpt_popularity():
    queries = []

    async def respond(request):
        import json

        queries.append(json.loads(request.content)["query"])
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "web": [
                        {
                            "url": "https://www.douyin.com/video/7692431224540035506",
                            "title": "北京故宫攻略，获赞99万",
                        },
                        {"url": "https://www.douyin.com/search/北京故宫", "title": "搜索页"},
                    ]
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        providers = TravelProviders(client, Settings(firecrawl_api_key="test"), ResearchData())
        found = await discover_videos(
            providers,
            TravelConditions(
                destination="北京", interests=["故宫"], video_preferences={"platforms": ["douyin"]}
            ),
        )
    assert len(found) == 1
    assert found[0].likes is None and found[0].favorites is None
    assert any("故宫" in query for query in queries)
    assert all("site:douyin.com/video" in query and "dpm.org.cn" not in query for query in queries)


class AdviceChat:
    async def complete(self, schema, **kwargs):
        assert schema is AdviceSelections
        return AdviceSelections(
            items=[
                {
                    "segment": 0,
                    "kind": "lodging",
                    "place": "北京",
                    "suggestion": "优先选择靠近地铁的住宿",
                },
                {
                    "segment": 1,
                    "kind": "restaurant",
                    "place": "牛街",
                    "suggestion": "牛街就餐，预留排队时间",
                },
                {"segment": 99, "kind": "pitfall", "place": "故宫", "suggestion": "不存在的片段"},
                {"segment": 0, "kind": "price", "place": "故宫", "suggestion": "门票80元"},
                {"segment": 1, "kind": "restaurant", "place": "牛街", "suggestion": "人均100元"},
            ]
        )


async def test_advice_binds_exact_original_segment_and_rejects_official_rules():
    item = video(
        source_id="R3",
        segments=[
            VideoSegment(start=5, text="住地铁附近，出行方便"),
            VideoSegment(start=12, text="牛街可以吃饭，但热门店需要排队"),
        ],
    )
    advice = await extract_video_advice(AdviceChat(), item, TravelConditions(destination="北京"))
    assert len(advice) == 2
    assert advice[0].quote == item.segments[0].text
    assert advice[1].timestamp_seconds == 12
    assert all(item.source_id == "R3" and item.status == "reference" for item in advice)


async def test_advice_keeps_all_cited_segments_and_rejects_invalid_ranges():
    class SpanChat:
        async def complete(self, schema, **kwargs):
            return AdviceSelections(
                items=[
                    {
                        "segment": 0,
                        "end_segment": 1,
                        "kind": "restaurant",
                        "place": "牛街",
                        "suggestion": "牛街吃饭预留排队时间",
                    },
                    {
                        "segment": 1,
                        "end_segment": 99,
                        "kind": "restaurant",
                        "place": "牛街",
                        "suggestion": "无效范围",
                    },
                ]
            )

    item = video(
        source_id="R1",
        segments=[
            VideoSegment(start=5, text="牛街可以吃饭"),
            VideoSegment(start=12, text="热门店需要排队"),
        ],
    )
    advice = await extract_video_advice(SpanChat(), item, TravelConditions(destination="北京"))
    assert len(advice) == 1 and advice[0].timestamp_seconds == 5
    assert advice[0].quote == "[5.0s] 牛街可以吃饭\n[12.0s] 热门店需要排队"


@pytest.mark.parametrize("layout_mode", ["flex", "fixed"])
@pytest.mark.parametrize("page_count", [5, 10])
async def test_search_to_advice_to_ppt_chain(monkeypatch, layout_mode, page_count):
    from app.domain.content import Deck
    from app.domain.export_check import run_export_check
    from app.domain.theme import resolve_theme
    from app.llm.slide import DeepSeekSlideGenerator
    from app.workflows.slide import build_slide_workflow, run_slide_workflow

    async def respond(request):
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "web": [
                        {
                            "url": "https://www.douyin.com/video/7692431224540035506",
                            "title": "北京住宿避坑",
                        },
                    ]
                },
            },
        )

    async def inspect(self, item):
        apply_metadata(
            item,
            {
                "likes": "1.5万",
                "favorites": 6571,
                "timestamp": datetime.now(UTC).timestamp(),
                "duration_seconds": 16,
            },
        )

    async def content(self, item):
        item.segments = [
            VideoSegment(start=5, text="住地铁附近，出行方便"),
            VideoSegment(start=12, text="牛街可以吃饭，但热门店需要排队"),
        ]
        item.status, item.content_kind = "ready", "transcription"

    monkeypatch.setattr(VideoReader, "inspect", inspect)
    monkeypatch.setattr(VideoReader, "content", content)
    data = ResearchData()
    conditions = TravelConditions(
        destination="北京", confirmed=True, video_preferences={"platforms": ["douyin"]}
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        await research_videos(
            TravelProviders(client, Settings(firecrawl_api_key="test"), data),
            conditions,
            AdviceChat(),
        )
    assert data.services[-1].status == "ready"
    assert len(data.video_advice) == 2
    assert data.sources[0].service == "video" and data.sources[0].trust == "unverified"
    assert data.video_advice[0].quote in data.sources[0].text
    assert data.videos[0].likes == 15000 and data.videos[0].counts_approximate
    data.plan = build_travel_plan(data, conditions)
    context = travel_context(
        SimpleNamespace(
            id=uuid.uuid4(),
            version=1,
            stale=False,
            status="ready",
            data=data.model_dump(mode="json"),
            conditions=conditions.model_dump(mode="json"),
        )
    )
    outline: OutlineDraft = build_travel_outline(
        OutlineGenerationInput(
            title="北京旅游",
            page_count=page_count,
            tone="professional",
            sections=[],
            travel_context=context,
        )
    )
    page = next(page for page in outline.pages if page.travel_page.kind == "lodging")
    assert len(outline.pages) >= page_count and outline.pages[-1].title == "消费成本汇总"
    assert outline.pages[3].title == "住宿推荐"
    slide, _ = await run_slide_workflow(
        build_slide_workflow(DeepSeekSlideGenerator(chat=AdviceChat())),
        SlideGenerationInput(
            deck_title="北京旅游",
            tone="professional",
            position=4,
            total_pages=page_count,
            page_title=page.title,
            objective=page.objective,
            key_points=page.key_points,
            layout_id="bullets",
            layout_mode=layout_mode,
            travel_context=context,
            travel_page=page.travel_page,
        ),
        uuid.uuid4(),
    )
    assert "https://www.douyin.com/video/" in slide.speaker_notes
    assert '"timestamp_seconds": 5.0' in slide.speaker_notes and "住地铁附近" in slide.speaker_notes
    report = run_export_check(
        Deck(id="test", title="北京旅游", theme_id="ivory", slides=[slide]),
        theme=resolve_theme("ivory"),
    )
    assert report.export_allowed, [
        (item.code, item.message) for item in report.issues if item.severity == "error"
    ]


async def test_subtitle_failure_uses_local_asr_and_retains_timestamps(monkeypatch):
    from app.services import travel_video

    actions = []

    async def worker(payload, timeout):
        actions.append(payload["action"])
        return {
            "inspect": {"segments": []},
            "audio": {"path": "audio.mp3"},
            "transcribe": {"segments": [{"start": 3, "end": 5, "text": "酒店靠近地铁"}]},
        }[payload["action"]]

    monkeypatch.setattr(travel_video, "run_video_worker", worker)
    async with httpx.AsyncClient() as client:
        reader = VideoReader(TravelProviders(client, Settings(), ResearchData()))
        item = video()
        await reader.content(item)
    assert actions == ["inspect", "audio", "transcribe"]
    assert item.content_kind == "transcription" and item.segments[0].start == 3


async def test_no_captions_or_audio_does_not_summarize_title(monkeypatch):
    from app.services import travel_video

    async def worker(payload, timeout):
        return {"error_code": "access_restricted"}

    monkeypatch.setattr(travel_video, "run_video_worker", worker)
    async with httpx.AsyncClient() as client:
        reader = VideoReader(TravelProviders(client, Settings(), ResearchData()))
        item = video()
        await reader.content(item)
    assert item.status == "unavailable" and item.segments == [] and item.content_kind is None


async def test_transcription_timeout_keeps_saved_evidence_and_marks_it_partial(monkeypatch):
    from app.services import travel_video

    async def worker(payload, timeout):
        if payload["action"] == "transcribe":
            Path(payload["progress_path"]).write_text(
                json.dumps({"segments": [{"start": 75, "text": "牛街热门店需要排队"}]}),
                encoding="utf-8",
            )
            raise TimeoutError
        return {"path": "audio.mp3"} if payload["action"] == "audio" else {}

    monkeypatch.setattr(travel_video, "run_video_worker", worker)
    async with httpx.AsyncClient() as client:
        reader = VideoReader(TravelProviders(client, Settings(), ResearchData()))
        item = video()
        await reader.content(item)
    assert item.status == "ready" and item.content_kind == "transcription"
    assert item.content_truncated and item.error_code == "content_partial"
    assert item.segments[0].text == "牛街热门店需要排队" and item.segments[0].start == 75


@pytest.mark.parametrize("recover", [False, True])
async def test_advice_failure_is_partial_or_recovers_after_one_retry(monkeypatch, recover):
    from app.services import travel_video

    async def discover(*args):
        return [video(), video("7692431224540035507", title="北京住宿建议")]

    async def inspect(self, item):
        pass

    async def content(self, item):
        item.status, item.content_kind = "ready", "subtitles"
        item.segments = [VideoSegment(start=5, text="住地铁附近，出行方便")]

    attempts = 0

    class PartlyFailingChat(AdviceChat):
        async def complete(self, schema, **kwargs):
            nonlocal attempts
            if json.loads(kwargs["user"])["title"] == "北京住宿建议":
                attempts += 1
                if recover and attempts == 1:
                    raise TimeoutError
                if not recover:
                    raise RuntimeError("unavailable")
            return await super().complete(schema, **kwargs)

    monkeypatch.setattr(travel_video, "discover_videos", discover)
    monkeypatch.setattr(VideoReader, "inspect", inspect)
    monkeypatch.setattr(VideoReader, "content", content)
    data = ResearchData()
    async with httpx.AsyncClient() as client:
        await research_videos(
            TravelProviders(client, Settings(firecrawl_api_key="test"), data),
            TravelConditions(destination="北京"),
            PartlyFailingChat(),
        )
    assert data.video_advice and data.services[-1].status == ("ready" if recover else "partial")
    assert data.videos[1].error_code == (None if recover else "advice_extraction_failed")
    assert attempts == (2 if recover else 1)


async def test_platform_chapters_remain_labeled_as_ai_summary(monkeypatch):
    from app.services import travel_video

    async def worker(payload, timeout):
        return {"error_code": "access_restricted"}

    monkeypatch.setattr(travel_video, "run_video_worker", worker)
    async with httpx.AsyncClient() as client:
        reader = VideoReader(TravelProviders(client, Settings(), ResearchData()))
        item = video()
        reader._summaries[item.id] = [VideoSegment(start=49, text="仁寿殿")]
        await reader.content(item)
    assert item.content_kind == "platform_summary" and item.segments[0].start == 49


async def test_video_research_disabled_does_not_query_anything():
    data = ResearchData()
    async with httpx.AsyncClient() as client:
        await research_videos(
            TravelProviders(client, Settings(), data),
            TravelConditions(video_preferences={"enabled": False}),
            AdviceChat(),
        )
    assert data.videos == [] and data.sources == [] and data.services == []


async def test_douyin_dom_reads_numeric_controls_and_ai_chapters_even_with_hidden_player():
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context()
        html = """
            <h1>北京颐和园攻略</h1>
            <div data-e2e="video-player-digg" style="display:none">--</div>
            <div data-e2e="video-player-digg">1.5万</div>
            <div data-e2e="video-player-collect">6571</div>
            <span data-e2e="user-name">北京导览</span>
            <p>发布时间：2026-08-19 19:39</p>
            <p>00:00 / 10:00</p>
            <section><div><div><span>章节要点</span></div></div>
            <p>00:49</p><p>仁寿殿</p><p>庭院中有寿星石</p>
            <p>04:54</p><p>长廊</p><p>沿湖游览</p><p>内容由AI生成</p></section>
        """

        async def respond(route):
            await route.fulfill(body=html, content_type="text/html; charset=utf-8")

        await context.route("**/*", respond)
        async with httpx.AsyncClient() as client:
            reader = VideoReader(TravelProviders(client, Settings(), ResearchData()))
            reader._context = context
            item = video()
            raw = await reader.douyin_metadata(item)
        await browser.close()
    assert raw["likes"] == "1.5万" and raw["favorites"] == "6571"
    assert raw["published_at"] == "2026-08-19T19:39"
    assert "04:54" in raw["chapters"] and "长廊" in raw["chapters"]
    assert reader._summaries[item.id][0].start == 49
    assert "庭院中有寿星石" in reader._summaries[item.id][0].text
    assert reader._summaries[item.id][1].start == 294
