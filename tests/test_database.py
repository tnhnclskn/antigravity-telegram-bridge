import pytest
import os
import aiosqlite
from pathlib import Path
from database import Database


@pytest.mark.asyncio
async def test_database_init_and_session(tmp_path: Path):
    db_file = tmp_path / "test.db"
    test_db = Database(db_path=db_file)
    await test_db.init()

    # Get session for new user
    session = await test_db.get_session(user_id=12345)
    assert session["user_id"] == 12345
    assert session["conversation_id"] is None

    # Update session
    await test_db.update_session(user_id=12345, conversation_id="uuid-abc-123", model="gemini-3.7-flash-high")
    updated = await test_db.get_session(user_id=12345)
    assert updated["conversation_id"] == "uuid-abc-123"
    assert updated["model"] == "gemini-3.7-flash-high"

    # Reset session
    await test_db.reset_session(user_id=12345)
    reset = await test_db.get_session(user_id=12345)
    assert reset["conversation_id"] is None


@pytest.mark.asyncio
async def test_database_whitelist_and_admin(tmp_path: Path):
    db_file = tmp_path / "test_auth.db"
    test_db = Database(db_path=db_file)
    await test_db.init()

    # Add whitelisted user
    await test_db.add_whitelisted_user(user_id=999, username="admin_user", role="admin")
    assert await test_db.is_whitelisted(user_id=999) is True
    assert await test_db.is_admin(user_id=999) is True

    # Check non-whitelisted user when list is not empty
    assert await test_db.is_whitelisted(user_id=888) is False

    # Remove user
    await test_db.remove_whitelisted_user(user_id=999)
    # List is now empty
    assert await test_db.count_whitelisted_users() == 0


@pytest.mark.asyncio
async def test_database_message_history(tmp_path: Path):
    db_file = tmp_path / "test_hist.db"
    test_db = Database(db_path=db_file)
    await test_db.init()

    await test_db.add_history(user_id=100, conversation_id="conv-1", role="user", content="Hello")
    await test_db.add_history(user_id=100, conversation_id="conv-1", role="assistant", content="Hi there!")

    history = await test_db.get_history(user_id=100, limit=10)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "Hi there!"


@pytest.mark.asyncio
async def test_database_usage_stats(tmp_path: Path):
    import json
    from database import get_codex_stats

    db_file = tmp_path / "test_usage.db"
    test_db = Database(db_path=db_file)
    await test_db.init()

    # Initial stats when empty
    empty_stats = await test_db.get_usage_stats()
    assert empty_stats["total_messages"] == 0
    assert empty_stats["total_sessions"] == 0
    assert empty_stats["avg_latency"] == 0.0

    # Add messages with metadata (usage and duration)
    meta1 = json.dumps({"usage": {"total_tokens": 150}, "duration_seconds": 2.5})
    await test_db.add_history(user_id=100, conversation_id="conv-1", role="user", content="Test 1")
    await test_db.add_history(user_id=100, conversation_id="conv-1", role="assistant", content="Response 1", metadata=meta1)

    meta2 = json.dumps({"usage": {"total_tokens": 250}, "duration_seconds": 1.5})
    await test_db.add_history(user_id=100, conversation_id="conv-2", role="user", content="Test 2")
    await test_db.add_history(user_id=100, conversation_id="conv-2", role="assistant", content="Response 2", metadata=meta2)

    stats = await test_db.get_usage_stats()
    assert stats["total_sessions"] == 2
    assert stats["total_messages"] == 4
    assert stats["user_messages"] == 2
    assert stats["assistant_messages"] == 2
    assert stats["messages_24h"] == 4
    assert stats["total_tokens_est"] >= 400  # 150 + 250 + estimated user tokens
    assert stats["tokens_24h_est"] >= 400
    assert stats["avg_latency"] == 2.0  # (2.5 + 1.5) / 2
    assert stats["total_duration"] == 4.0
    assert stats["recorded_latencies_count"] == 2


def test_codex_stats_helper(tmp_path: Path):
    import sqlite3
    from database import get_codex_stats

    # 1. Non-existent path
    non_existent = tmp_path / "does_not_exist"
    res_none = get_codex_stats(non_existent)
    assert res_none["exists"] is False
    assert res_none["logs_count"] == 0

    # 2. Existing path with simulated sqlite files
    codex_dir = tmp_path / "mock_codex"
    codex_dir.mkdir()

    # Create logs_2.sqlite
    logs_file = codex_dir / "logs_2.sqlite"
    with sqlite3.connect(str(logs_file)) as conn:
        conn.execute("CREATE TABLE logs (id INTEGER PRIMARY KEY, msg TEXT)")
        conn.execute("INSERT INTO logs (msg) VALUES ('log 1'), ('log 2'), ('log 3')")
        conn.commit()

    # Create state_5.sqlite
    state_file = codex_dir / "state_5.sqlite"
    with sqlite3.connect(str(state_file)) as conn:
        conn.execute("CREATE TABLE threads (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO threads (id) VALUES ('t1'), ('t2')")
        conn.commit()

    res = get_codex_stats(codex_dir)
    assert res["exists"] is True
    assert res["files_count"] >= 2
    assert res["logs_count"] == 3
    assert res["threads_count"] == 2
    assert res["total_size_mb"] >= 0.0

