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
