"""Generate a local travel sample through the real research, outline and PPT flows."""

import asyncio
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import httpx

from app.api.deps import get_queue
from app.llm.client import create_chat_model
from app.main import app
from app.worker.context import create_outline_generator, create_slide_generator
from app.worker.deck_tasks import generate_deck
from app.worker.tasks import generate_outline


async def main():
    output = Path("var/travel-smoke")
    output.mkdir(parents=True, exist_ok=True)
    queue = AsyncMock()
    app.dependency_overrides[get_queue] = lambda: queue
    model = create_chat_model()
    ctx = {
        "chat_model": model,
        "outline_generator": create_outline_generator(model),
        "slide_generator": create_slide_generator(model),
    }
    email = f"travel_smoke_{uuid.uuid4().hex[:8]}@example.com"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/auth/register", json={"email": email, "password": "local-travel-smoke-123"}
        )
        response.raise_for_status()
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

        async def request(method, path, **kwargs):
            response = await client.request(method, "/api/v1" + path, headers=headers, **kwargs)
            if response.status_code >= 400:
                raise RuntimeError(f"{path}: {response.status_code} {response.text[:300]}")
            return response

        topic = (
            "2027年2月6日至8日春节去北京旅游规划，从上海出发，2位成人，"
            "预算5000元，游览故宫和天坛，节奏轻松。"
        )
        project = (
            await request(
                "POST",
                "/projects",
                json={
                    "title": "春节去北京旅游规划（本地验收）",
                    "page_count": 5,
                    "report_brief": {"scenario": "travel_plan"},
                    "travel_conditions": {
                        "origin": "上海",
                        "destination": "北京",
                        "departure_date": "2027-02-06",
                        "return_date": "2027-02-08",
                        "adults": 2,
                        "budget": 5000,
                        "pace": "relaxed",
                        "interests": ["故宫", "天坛"],
                        "confirmed": True,
                    },
                },
            )
        ).json()
        identifier = project["id"]
        print(f"project={identifier} login={email}", flush=True)
        await request(
            "POST", f"/projects/{identifier}/sources", json={"kind": "topic", "content": topic}
        )
        accepted = (await request("POST", f"/projects/{identifier}/outline/generate")).json()
        await generate_outline(ctx, identifier, accepted["job_id"])
        research = (await request("GET", f"/projects/{identifier}/travel/research")).json()
        output.joinpath("research.json").write_text(
            json.dumps(research, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            f"research={research['status']} sources={len(research['data']['sources'])} "
            f"facts={len(research['data']['facts'])}",
            flush=True,
        )
        assert all(
            day["weather"]["status"] == "pending" for day in research["data"]["plan"]["days"]
        )
        outline = (await request("GET", f"/projects/{identifier}/outline")).json()
        print(f"outline={outline['status']}", flush=True)
        if outline["status"] != "draft":
            raise RuntimeError(f"outline failed: {outline.get('error_code')}")
        await request(
            "POST",
            f"/projects/{identifier}/outline/confirm",
            json={"revision": outline["revision"]},
        )
        await request("POST", f"/projects/{identifier}/deck/generate", json={})
        deck = (await request("GET", f"/projects/{identifier}/deck")).json()
        await generate_deck(ctx, identifier, [slide["id"] for slide in deck["slides"]])
        deck = (await request("GET", f"/projects/{identifier}/deck")).json()
        print(f"deck={deck['status']} ready={deck['ready']} failed={deck['failed']}", flush=True)
        assert deck["ready"] == 5
        pptx = await request("GET", f"/projects/{identifier}/deck/export")
        output.joinpath("travel.pptx").write_bytes(pptx.content)
        output.joinpath("result.json").write_text(
            json.dumps(
                {
                    "project_id": identifier,
                    "email": email,
                    "research_status": research["status"],
                    "sources": len(research["data"]["sources"]),
                    "facts": len(research["data"]["facts"]),
                    "ready_slides": deck["ready"],
                    "pptx_bytes": len(pptx.content),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"exported={output / 'travel.pptx'} bytes={len(pptx.content)}", flush=True)
    app.dependency_overrides.pop(get_queue, None)


if __name__ == "__main__":
    asyncio.run(main())
