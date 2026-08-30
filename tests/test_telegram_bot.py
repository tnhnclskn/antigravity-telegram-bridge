import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from telegram import Update, User, Message, Chat, CallbackQuery, BotCommand
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import settings
from database import Database, db
import telegram_bot
from telegram_bot import (
    BOT_COMMANDS,
    post_init,
    start_command,
    help_command,
    new_session_command,
    update_command,
    usage_command,
    status_command,
    model_command,
    effort_command,
    workspace_command,
    cancel_command,
    callback_handler,
    build_application,
    authorized_only
)


@pytest.fixture(autouse=True)
async def setup_test_db(tmp_path: Path, monkeypatch):
    """Setup clean temporary database for telegram tests."""
    test_db_path = tmp_path / "test_tg.db"
    test_db = Database(db_path=test_db_path)
    monkeypatch.setattr(telegram_bot, "db", test_db)
    monkeypatch.setattr("database.db", test_db)
    monkeypatch.setattr(settings, "AUTO_WHITELIST_FIRST_USER", True)
    await test_db.init()
    return test_db


def create_mock_update(user_id: int = 12345, username: str = "testuser", text: str = "") -> Update:
    """Helper to create realistic telegram Update mock."""
    update = MagicMock(spec=Update)
    user = MagicMock(spec=User)
    user.id = user_id
    user.first_name = "Test"
    user.username = username
    user.full_name = "Test User"
    
    chat = MagicMock(spec=Chat)
    chat.id = user_id

    message = AsyncMock(spec=Message)
    message.chat_id = user_id
    message.text = text
    message.caption = None
    message.photo = None
    message.document = None
    message.reply_text = AsyncMock()

    update.effective_user = user
    update.effective_chat = chat
    update.message = message
    update.callback_query = None
    return update


@pytest.mark.asyncio
async def test_bot_commands_list_and_post_init():
    """Verify that BOT_COMMANDS contains required commands and post_init registers them."""
    command_names = [cmd.command for cmd in BOT_COMMANDS]
    assert "newchat" in command_names
    assert "update" in command_names
    assert "usage" in command_names
    assert "model" in command_names
    assert "effort" in command_names
    assert "status" in command_names
    assert "help" in command_names
    assert "cancel" in command_names

    mock_app = MagicMock()
    mock_app.bot.set_my_commands = AsyncMock()

    await post_init(mock_app)
    mock_app.bot.set_my_commands.assert_awaited_once_with(BOT_COMMANDS)


@pytest.mark.asyncio
async def test_start_and_help_commands():
    """Test /start and /help command responses."""
    update = create_mock_update(user_id=1001, username="admin", text="/start")
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    # 1. /start
    await start_command(update, context)
    update.message.reply_text.assert_awaited_once()
    start_call_args = update.message.reply_text.call_args[0][0]
    assert "Antigravity CLI Telegram Köprüsüne Hoş Geldiniz" in start_call_args
    assert "Aktif Oturum Bilgileri" in start_call_args

    # 2. /help
    update.message.reply_text.reset_mock()
    await help_command(update, context)
    update.message.reply_text.assert_awaited_once()
    help_call_args = update.message.reply_text.call_args[0][0]
    assert "/newchat" in help_call_args
    assert "/update" in help_call_args
    assert "/usage" in help_call_args


@pytest.mark.asyncio
async def test_newchat_command():
    """Test /newchat resets session conversation_id."""
    update = create_mock_update(user_id=1002, username="user2", text="/newchat")
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    # Set existing conversation_id in session
    await telegram_bot.db.update_session(user_id=1002, conversation_id="conv-old-999")
    session_before = await telegram_bot.db.get_session(1002)
    assert session_before["conversation_id"] == "conv-old-999"

    await new_session_command(update, context)
    update.message.reply_text.assert_awaited_once()
    msg_sent = update.message.reply_text.call_args[0][0]
    assert "Sohbet oturumu sıfırlandı" in msg_sent

    session_after = await telegram_bot.db.get_session(1002)
    assert session_after["conversation_id"] is None


@pytest.mark.asyncio
async def test_update_command_success(monkeypatch):
    """Test /update command when git pull --rebase succeeds."""
    update = create_mock_update(user_id=1003, username="user3", text="/update")
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    # Mock reply_text to return an editable status_msg mock
    status_msg = AsyncMock()
    status_msg.edit_text = AsyncMock()
    update.message.reply_text.return_value = status_msg

    # Mock subprocess for git pull
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"Already up to date.\n", b"")

    async def mock_create_subprocess_exec(*args, **kwargs):
        return mock_proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess_exec)

    await update_command(update, context)
    status_msg.edit_text.assert_awaited_once()
    final_text = status_msg.edit_text.call_args[0][0]
    assert "Git Güncelleme Raporu" in final_text
    assert "Agentic OS" in final_text
    assert "Güncel" in final_text


@pytest.mark.asyncio
async def test_update_command_with_changes(monkeypatch):
    """Test /update command when git pull --rebase pulls new commits."""
    update = create_mock_update(user_id=1004, username="user4", text="/update")
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    status_msg = AsyncMock()
    status_msg.edit_text = AsyncMock()
    update.message.reply_text.return_value = status_msg

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate.return_value = (b"Updating 4a123..9b876\nFast-forward\n 3 files changed, 45 insertions(+)", b"")

    async def mock_create_subprocess_exec(*args, **kwargs):
        return mock_proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess_exec)

    await update_command(update, context)
    final_text = status_msg.edit_text.call_args[0][0]
    assert "Güncellendi!" in final_text
    assert "Fast-forward" in final_text


@pytest.mark.asyncio
async def test_usage_command(monkeypatch):
    """Test /usage command returns formatted Antigravity and Codex statistics."""
    update = create_mock_update(user_id=1005, username="user5", text="/usage")
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    # Populate some history in db
    await telegram_bot.db.add_history(1005, "conv-1", "user", "Prompt test")
    await telegram_bot.db.add_history(1005, "conv-1", "assistant", "Response test", metadata='{"usage": {"total_tokens": 120}, "duration_seconds": 1.2}')

    # Mock codex stats
    def mock_codex_stats(codex_dir=None):
        return {
            "exists": True,
            "path": "/root/.codex",
            "total_size_mb": 1.5,
            "files_count": 8,
            "logs_count": 686,
            "threads_count": 0
        }

    monkeypatch.setattr(telegram_bot, "get_codex_stats", mock_codex_stats)

    await usage_command(update, context)
    update.message.reply_text.assert_awaited_once()
    usage_text = update.message.reply_text.call_args[0][0]
    assert "Antigravity & Codex Kullanım İstatistikleri" in usage_text
    assert "Toplam Oturum:" in usage_text
    assert "Toplam Mesaj:" in usage_text
    assert "Tahmini Toplam Token:" in usage_text
    assert "Codex Ortamı:" in usage_text
    assert "686" in usage_text
    assert "1.5 MB" in usage_text


@pytest.mark.asyncio
async def test_callback_handler_actions(monkeypatch):
    """Test callback query interactions."""
    update = MagicMock(spec=Update)
    user = MagicMock(spec=User)
    user.id = 1006
    user.username = "user6"
    user.first_name = "UserSix"
    user.full_name = "User Six"

    query = AsyncMock(spec=CallbackQuery)
    query.from_user = user
    query.data = "cmd_new"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.message = AsyncMock()
    query.message.reply_text = AsyncMock()

    update.effective_user = user
    update.callback_query = query
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    # Allow user
    await telegram_bot.db.add_whitelisted_user(1006, username="user6", role="admin")

    # 1. cmd_new
    await callback_handler(update, context)
    query.edit_message_text.assert_awaited_once()
    assert "Yeni oturum başlatıldı" in query.edit_message_text.call_args[0][0]

    # 2. set_model
    query.edit_message_text.reset_mock()
    query.data = "set_model:gemini-3.7-flash-high"
    await callback_handler(update, context)
    query.edit_message_text.assert_awaited_once()
    assert "Model güncellendi" in query.edit_message_text.call_args[0][0]
    session = await telegram_bot.db.get_session(1006)
    assert session["model"] == "gemini-3.7-flash-high"

    # 3. set_effort
    query.edit_message_text.reset_mock()
    query.data = "set_effort:medium"
    await callback_handler(update, context)
    query.edit_message_text.assert_awaited_once()
    assert "Düşünme seviyesi güncellendi" in query.edit_message_text.call_args[0][0]
    session = await telegram_bot.db.get_session(1006)
    assert session["effort"] == "medium"


@pytest.mark.asyncio
async def test_build_application():
    """Test build_application sets up token and handlers properly."""
    with patch.object(settings, "TELEGRAM_BOT_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"):
        with patch.object(settings, "AGY_BIN_PATH", "/bin/sh"):
            app = build_application()
            assert app is not None
            # Check registered handler command names
            handlers = app.handlers[0]
            cmd_handlers = [h for h in handlers if hasattr(h, "commands")]
            registered_cmds = set()
            for h in cmd_handlers:
                for c in h.commands:
                    registered_cmds.add(c)

            assert "newchat" in registered_cmds
            assert "update" in registered_cmds
            assert "usage" in registered_cmds
            assert "model" in registered_cmds
            assert "effort" in registered_cmds
            assert "status" in registered_cmds
            assert "help" in registered_cmds
            assert "cancel" in registered_cmds
