import asyncio
import json

import pytest
from agy_client import AgyClient


@pytest.mark.asyncio
async def test_agy_models():
    client = AgyClient()
    models = await client.get_available_models()
    assert isinstance(models, list)
    assert len(models) > 0
    # Should include some gemini or claude models
    assert any("gemini" in m or "claude" in m for m in models)


@pytest.mark.asyncio
async def test_prompt_stream_omits_conflicting_effort(monkeypatch):
    client = AgyClient(bin_path="agy")
    captured = {}

    class FakeReader:
        def __init__(self, lines):
            self.lines = iter(lines)

        async def readline(self):
            try:
                return next(self.lines)
            except StopIteration:
                await asyncio.sleep(0)
                return b""

    class FakeProcess:
        returncode = 0

        def __init__(self):
            result = {"event": "result", "result": {"response": "OK"}}
            self.stdout = FakeReader([json.dumps(result).encode() + b"\n"])
            self.stderr = FakeReader([])

        async def wait(self):
            return self.returncode

    async def fake_create(*args, **kwargs):
        captured["args"] = args
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    events = [event async for event in client.run_prompt_stream(
        user_id="test",
        prompt="Selam",
        workspace="/tmp",
        model="gemini-3.1-pro-low",
        effort="high",
    )]

    assert "--effort" not in captured["args"]
    assert events[-1]["response"] == "OK"


def test_agy_cancel_nonexistent_task():
    client = AgyClient()
    # Cancelling a non-running task should return False gracefully
    assert client.cancel_task(999999) is False
    assert client.is_running(999999) is False
    # cancel_all should not error when no tasks active
    client.cancel_all()


def test_model_effort_is_not_duplicated():
    client = AgyClient()

    assert client._model_embeds_effort("gemini-3.1-pro-low") is True
    assert client._model_embeds_effort("gemini-3.7-flash-high") is True
    assert client._model_embeds_effort("claude-sonnet-4-6") is False
    assert client._model_embeds_effort(None) is False
