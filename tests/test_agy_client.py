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


def test_agy_cancel_nonexistent_task():
    client = AgyClient()
    # Cancelling a non-running task should return False gracefully
    assert client.cancel_task(999999) is False
    assert client.is_running(999999) is False
    # cancel_all should not error when no tasks active
    client.cancel_all()
