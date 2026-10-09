import uuid
from types import SimpleNamespace

import pytest

from app.api.sse import event_stream_response
from app.schemas.outline import OutlineEvent


@pytest.mark.parametrize("stale_snapshot", [False, True])
async def test_stream_subscribes_before_snapshot_and_closes_terminal(monkeypatch, stale_snapshot):
    actions = []

    class Pubsub:
        async def subscribe(self, channel):
            actions.append("subscribe")

        async def unsubscribe(self, channel):
            actions.append("unsubscribe")

        async def aclose(self):
            actions.append("close")

        async def get_message(self, **kwargs):
            pytest.fail("A terminal initial snapshot must close without waiting for messages")

    class Stream:
        def channel(self, key):
            return "test:events"

        async def latest(self, key):
            assert actions == ["subscribe"]
            actions.append("snapshot")
            return OutlineEvent(
                type="failed" if stale_snapshot else "completed",
                status="failed" if stale_snapshot else "draft",
                progress=100,
                message="old failure" if stale_snapshot else "done",
                job_id="old" if stale_snapshot else "current",
            )

    monkeypatch.setattr("app.api.sse.get_redis", lambda: SimpleNamespace(pubsub=Pubsub))
    response = event_stream_response(
        SimpleNamespace(),
        stream=Stream(),
        key=uuid.uuid4(),
        fallback=OutlineEvent(
            type="completed",
            status="draft",
            progress=100,
            message="current result",
            job_id="current",
        ),
        terminal_types={"completed", "failed"},
        initial_filter=lambda event: event.job_id == "current",
    )
    frames = [frame async for frame in response.body_iterator]
    assert len(frames) == 1
    assert "event: completed" in frames[0]
    assert "old failure" not in frames[0]
    assert actions == ["subscribe", "snapshot", "unsubscribe", "close"]
