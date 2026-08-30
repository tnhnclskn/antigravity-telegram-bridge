import asyncio
import json

import pytest
from agy_client import AgyClient, normalize_model_name


@pytest.mark.asyncio
async def test_agy_models():
    client = AgyClient()
    models = await client.get_available_models()
    assert isinstance(models, list)
    assert len(models) > 0
    # Should include some gemini or claude models
    assert any("gemini" in m or "claude" in m for m in models)


@pytest.mark.asyncio
async def test_prompt_stream_normalizes_model_and_passes_effort(monkeypatch):
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

    assert "--model" in captured["args"]
    assert captured["args"][captured["args"].index("--model") + 1] == "gemini-3.1-pro"
    assert captured["args"][captured["args"].index("--effort") + 1] == "high"
    assert events[-1]["response"] == "OK"


def test_agy_cancel_nonexistent_task():
    client = AgyClient()
    # Cancelling a non-running task should return False gracefully
    assert client.cancel_task(999999) is False
    assert client.is_running(999999) is False
    # cancel_all should not error when no tasks active
    client.cancel_all()


def test_model_names_are_normalized_for_separate_effort_selection():
    assert normalize_model_name("gemini-3.1-pro-low") == "gemini-3.1-pro"
    assert normalize_model_name("gemini-3.7-flash-high") == "gemini-3.7-flash"
    assert normalize_model_name("gpt-oss-120b-medium") == "gpt-oss-120b"
    assert normalize_model_name("claude-sonnet-4-6") == "claude-sonnet-4-6"
    assert normalize_model_name(None) is None


def test_normalize_event_state():
    from agy_client import normalize_event_state
    assert normalize_event_state("ACTIVE") == "running"
    assert normalize_event_state("active") == "running"
    assert normalize_event_state("RUNNING") == "running"
    assert normalize_event_state("running") == "running"
    assert normalize_event_state("start") == "running"
    assert normalize_event_state("started") == "running"
    assert normalize_event_state("DONE") == "completed"
    assert normalize_event_state("done") == "completed"
    assert normalize_event_state("COMPLETED") == "completed"
    assert normalize_event_state("completed") == "completed"
    assert normalize_event_state("SUCCESS") == "completed"
    assert normalize_event_state(None) == "running"
    assert normalize_event_state("") == "running"


@pytest.mark.asyncio
async def test_prompt_stream_normalizes_step_update_states(monkeypatch):
    from agy_client import AgyClient
    client = AgyClient(bin_path="agy")

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
            lines = [
                json.dumps({"event": "init", "conversation_id": "c-1"}).encode() + b"\n",
                json.dumps({
                    "event": "step_update",
                    "step_update": {
                        "step_type": "tool",
                        "state": "ACTIVE",
                        "tool_name": "find_by_name",
                        "tool_info": {"parameters": {"Pattern": "*.py"}}
                    }
                }).encode() + b"\n",
                json.dumps({
                    "event": "step_update",
                    "step_update": {
                        "step_type": "tool",
                        "state": "DONE",
                        "tool_name": "find_by_name",
                        "duration_seconds": 0.05,
                        "tool_info": {"parameters": {"Pattern": "*.py"}}
                    }
                }).encode() + b"\n",
                json.dumps({"event": "result", "result": {"response": "Found files"}}).encode() + b"\n",
            ]
            self.stdout = FakeReader(lines)
            self.stderr = FakeReader([])

        async def wait(self):
            return self.returncode

    async def fake_create(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    events = [event async for event in client.run_prompt_stream(
        user_id="test",
        prompt="Find files",
    )]

    assert len(events) == 4
    assert events[0]["type"] == "init"
    assert events[1]["type"] == "step_update"
    assert events[1]["state"] == "running"  # Normalized from ACTIVE
    assert events[2]["type"] == "step_update"
    assert events[2]["state"] == "completed"  # Normalized from DONE
    assert events[3]["type"] == "result"
    assert events[3]["response"] == "Found files"


def test_agy_get_active_count():
    from unittest.mock import MagicMock
    client = AgyClient()
    assert client.get_active_count() == 0

    mock_proc1 = MagicMock()
    mock_proc1.returncode = None
    client._active_processes["user1"] = mock_proc1

    mock_proc2 = MagicMock()
    mock_proc2.returncode = None
    client._active_processes["user2"] = mock_proc2

    assert client.get_active_count() == 2

    # If a process finishes (returncode set), get_active_count should clean it up
    mock_proc1.returncode = 0
    assert client.get_active_count() == 1
    assert "user1" not in client._active_processes
    assert "user2" in client._active_processes


@pytest.mark.asyncio
async def test_agy_send_input():
    client = AgyClient()
    
    class DummyStdin:
        def __init__(self):
            self.written = b""
        def write(self, data):
            self.written += data
        async def drain(self):
            pass
            
    class DummyProc:
        def __init__(self):
            self.returncode = None
            self.stdin = DummyStdin()
            self.pid = 12345
            
    proc = DummyProc()
    client._active_processes[1] = proc
    
    success = await client.send_input(1, "my input text")
    assert success is True
    assert proc.stdin.written == b"my input text\n"
    
    # Test non-existent process
    success = await client.send_input(2, "fail")
    assert success is False


@pytest.mark.asyncio
async def test_prompt_stream_with_active_subagents_event(monkeypatch):
    client = AgyClient(bin_path="agy")

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
            events = [
                {"event": "init", "conversation_id": "conv-sub-1"},
                {
                    "event": "step_update",
                    "step_update": {
                        "step_type": "tool",
                        "state": "ACTIVE",
                        "tool_name": "invoke_subagent",
                        "active_subagents": [{"name": "Araştırmacı", "status": "running"}]
                    }
                },
                {"event": "result", "result": {"response": "Done"}}
            ]
            self.stdout = FakeReader([json.dumps(e).encode() + b"\n" for e in events])
            self.stderr = FakeReader([])

        async def wait(self):
            return self.returncode

    async def fake_create(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    events = [event async for event in client.run_prompt_stream(
        user_id="test_sub",
        prompt="Execute task with subagent"
    )]

    assert len(events) == 3
    assert events[1]["type"] == "step_update"
    assert events[1]["active_subagents"] == [{"name": "Araştırmacı", "status": "running"}]


@pytest.mark.asyncio
async def test_get_official_quotas_structured(monkeypatch):
    client = AgyClient(bin_path="agy")

    sample_output = {
        "conversation_id": "",
        "status": "SUCCESS",
        "response": "Gemini Models\tWeekly Limit Remaining\t50%\t2026-09-02T09:13:21Z\n",
        "command": {
            "name": "usage",
            "data": {
                "description": "Within each group, models share a weekly limit and a 5-hour limit.",
                "groups": [
                    {
                        "name": "Gemini Models",
                        "description": "Models: Gemini Flash, Gemini Pro",
                        "buckets": [
                            {
                                "id": "gemini-weekly",
                                "name": "Weekly Limit Remaining",
                                "description": "Weekly refresh in 2 days",
                                "window": "weekly",
                                "remaining_fraction": 0.49777,
                                "reset_time": "2026-09-02T09:13:21Z"
                            },
                            {
                                "id": "gemini-5h",
                                "name": "Five Hour Limit Remaining",
                                "description": "5-hour refresh in 1 hour",
                                "window": "5h",
                                "remaining_fraction": 0.61812,
                                "reset_time": "2026-08-30T16:49:12Z"
                            }
                        ]
                    },
                    {
                        "name": "Claude and GPT models",
                        "description": "Models: Claude, GPT",
                        "buckets": [
                            {
                                "id": "3p-weekly",
                                "name": "Weekly Limit Remaining",
                                "window": "weekly",
                                "remaining_fraction": 0.268,
                                "reset_time": "2026-08-31T11:41:54Z"
                            },
                            {
                                "id": "3p-5h",
                                "name": "Five Hour Limit Remaining",
                                "window": "5h",
                                "remaining_fraction": 1.0,
                                "reset_time": "2026-08-30T20:43:53Z"
                            }
                        ]
                    }
                ]
            }
        }
    }

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return json.dumps(sample_output).encode(), b""

    async def fake_create(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    res = await client.get_official_quotas()
    assert res["success"] is True
    assert len(res["groups"]) == 2
    assert res["groups"][0]["name"] == "Gemini Models"
    assert len(res["groups"][0]["buckets"]) == 2
    assert res["groups"][0]["buckets"][0]["window"] == "weekly"
    assert res["groups"][0]["buckets"][0]["remaining_percent"] == 49.8
    assert res["groups"][0]["buckets"][1]["window"] == "5h"
    assert res["groups"][0]["buckets"][1]["remaining_percent"] == 61.8
    assert res["groups"][1]["name"] == "Claude and GPT models"
    assert res["groups"][1]["buckets"][1]["remaining_percent"] == 100.0


@pytest.mark.asyncio
async def test_get_official_quotas_fallback_tsv(monkeypatch):
    client = AgyClient(bin_path="agy")

    sample_output = {
        "status": "SUCCESS",
        "response": (
            "Gemini Models\tWeekly Limit Remaining\t50%\t2026-09-02T09:13:21Z\n"
            "Gemini Models\tFive Hour Limit Remaining\t62%\t2026-08-30T16:49:12Z\n"
            "Claude and GPT models\tWeekly Limit Remaining\t27%\t2026-08-31T11:41:54Z\n"
            "Claude and GPT models\tFive Hour Limit Remaining\t100%\t2026-08-30T20:43:53Z\n"
        )
    }

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return json.dumps(sample_output).encode(), b""

    async def fake_create(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    res = await client.get_official_quotas()
    assert res["success"] is True
    assert len(res["groups"]) == 2
    gemini_group = next(g for g in res["groups"] if g["name"] == "Gemini Models")
    assert len(gemini_group["buckets"]) == 2
    assert gemini_group["buckets"][0]["window"] == "weekly"
    assert gemini_group["buckets"][0]["remaining_percent"] == 50.0
    assert gemini_group["buckets"][1]["window"] == "5h"
    assert gemini_group["buckets"][1]["remaining_percent"] == 62.0


@pytest.mark.asyncio
async def test_get_official_quotas_error_handling(monkeypatch):
    client = AgyClient(bin_path="agy")

    async def fake_create(*args, **kwargs):
        raise RuntimeError("Subprocess exec failed")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)

    res = await client.get_official_quotas()
    assert res["success"] is False
    assert res["groups"] == []
    assert "Subprocess exec failed" in res["error"]

