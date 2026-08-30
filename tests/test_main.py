"""
Unit tests for main.py startup and lifecycle coordination.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest

from config import settings


@pytest.mark.asyncio
async def test_main_telegram_startup_executes_post_init(monkeypatch):
    """Verify that main() executes tg_app.post_init(tg_app) right after tg_app.initialize()."""
    import main

    call_order = []

    mock_db_init = AsyncMock(side_effect=lambda: call_order.append("db.init"))
    monkeypatch.setattr(main.db, "init", mock_db_init)

    monkeypatch.setattr(settings, "ENABLE_TELEGRAM", True)
    monkeypatch.setattr(settings, "ENABLE_WEBUI", False)
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")

    mock_tg_app = MagicMock()
    mock_tg_app.initialize = AsyncMock(side_effect=lambda: call_order.append("tg_app.initialize"))
    mock_tg_app.post_init = AsyncMock(side_effect=lambda app: call_order.append("tg_app.post_init"))
    mock_tg_app.start = AsyncMock(side_effect=lambda: call_order.append("tg_app.start"))
    mock_bot_info = MagicMock()
    mock_bot_info.username = "test_bot"
    mock_bot_info.id = 123456
    mock_tg_app.bot.get_me = AsyncMock(return_value=mock_bot_info)
    mock_tg_app.updater.start_polling = AsyncMock(side_effect=lambda **kwargs: call_order.append("updater.start_polling"))
    mock_tg_app.updater.running = True
    mock_tg_app.updater.stop = AsyncMock()
    mock_tg_app.running = True
    mock_tg_app.stop = AsyncMock()
    mock_tg_app.shutdown = AsyncMock()

    mock_post_init = AsyncMock(side_effect=lambda app: call_order.append("post_init"))
    monkeypatch.setattr("telegram_bot.post_init", mock_post_init)

    mock_build_app = MagicMock(return_value=mock_tg_app)
    monkeypatch.setattr("telegram_bot.build_application", mock_build_app)

    # Let asyncio.sleep raise asyncio.CancelledError or break the loop after 1 tick
    async def mock_sleep(secs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    try:
        await main.main()
    except asyncio.CancelledError:
        pass

    assert "tg_app.initialize" in call_order
    assert "post_init" in call_order
    assert "tg_app.start" in call_order

    init_idx = call_order.index("tg_app.initialize")
    post_init_idx = call_order.index("post_init")
    start_idx = call_order.index("tg_app.start")

    assert init_idx < post_init_idx < start_idx
    mock_post_init.assert_awaited_once_with(mock_tg_app)
