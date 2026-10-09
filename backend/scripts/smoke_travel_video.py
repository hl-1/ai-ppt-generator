"""Run the real video research pipeline without creating or modifying a project."""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.llm.client import StructuredChatClient, create_chat_model
from app.schemas.travel import ResearchData, TravelConditions, TravelVideo
from app.services.travel_providers import TravelProviders
from app.services.travel_video import VideoReader, research_videos, video_url


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", default="北京")
    parser.add_argument("--interest", action="append", default=[])
    parser.add_argument("--platform", choices=["douyin", "bilibili"], default="douyin")
    parser.add_argument("--min-likes", type=int, default=10000)
    parser.add_argument("--min-favorites", type=int, default=1000)
    parser.add_argument("--lookback-days", type=int, default=180)
    parser.add_argument("--max-candidates", type=int, default=6)
    parser.add_argument("--max-selected", type=int, default=1)
    parser.add_argument("--skip-asr", action="store_true")
    parser.add_argument("--url", help="Inspect and extract one known video instead of searching")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    settings = get_settings().model_copy(
        update={
            "travel_video_max_candidates": args.max_candidates,
            "travel_video_max_selected": args.max_selected,
            "travel_video_asr_enabled": not args.skip_asr,
        }
    )
    data = ResearchData()
    conditions = TravelConditions(
        destination=args.destination,
        interests=args.interest,
        video_preferences={
            "platforms": [args.platform],
            "min_likes": args.min_likes,
            "min_favorites": args.min_favorites,
            "lookback_days": args.lookback_days,
        },
    )
    async with httpx.AsyncClient(follow_redirects=False) as client:
        providers = TravelProviders(client, settings, data)
        if args.url:
            parsed = video_url(args.url)
            if not parsed:
                parser.error("A public Douyin or Bilibili video URL is required")
            video = TravelVideo(
                id=f"{parsed[0]}:{parsed[1]}",
                platform=parsed[0],
                url=parsed[2],
                retrieved_at=datetime.now(UTC),
            )
            reader = VideoReader(providers)
            try:
                await reader.inspect(video)
                await reader.content(video)
                data.videos = [video]
            finally:
                await reader.close()
        else:
            chat = StructuredChatClient(
                model=create_chat_model(settings), api_key=settings.llm_api_key
            )
            await research_videos(providers, conditions, chat)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data.model_dump_json(indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "candidates": len(data.videos),
                "selected": sum(video.selected for video in data.videos),
                "advice_count": len(data.video_advice),
                "videos": [
                    {
                        "title": video.title,
                        "likes": video.likes,
                        "favorites": video.favorites,
                        "status": video.status,
                        "error_code": video.error_code,
                        "content_kind": video.content_kind,
                        "duration_seconds": video.duration_seconds,
                        "content_truncated": video.content_truncated,
                        "segments": len(video.segments),
                    }
                    for video in data.videos
                ],
                "advice": [
                    {
                        "kind": item.kind,
                        "place": item.place,
                        "suggestion": item.suggestion,
                        "timestamp_seconds": item.timestamp_seconds,
                    }
                    for item in data.video_advice
                ],
                "services": [service.model_dump(mode="json") for service in data.services],
            },
            ensure_ascii=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
