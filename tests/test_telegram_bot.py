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
    projects_command,
    get_available_projects,
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
    message.voice = None
    message.audio = None
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
    assert "start" in command_names
    assert "help" in command_names
    assert "projects" in command_names
    assert "newchat" in command_names
    assert "update" in command_names
    assert "usage" in command_names
    assert "model" in command_names
    assert "effort" in command_names
    assert "status" in command_names
    assert "cancel" in command_names
    assert "workspace" in command_names
    assert "permissions" in command_names
    assert "history" in command_names
    assert "whitelist" in command_names

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
    assert "/projects" in help_call_args
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

    # 2. set_model (normalized without effort suffix)
    query.edit_message_text.reset_mock()
    query.data = "set_model:gemini-3.7-flash-high"
    await callback_handler(update, context)
    query.edit_message_text.assert_awaited_once()
    assert "Model güncellendi" in query.edit_message_text.call_args[0][0]
    session = await telegram_bot.db.get_session(1006)
    assert session["model"] == "gemini-3.7-flash"

    # 3. set_effort
    query.edit_message_text.reset_mock()
    query.data = "set_effort:medium"
    await callback_handler(update, context)
    query.edit_message_text.assert_awaited_once()
    assert "Düşünme seviyesi güncellendi" in query.edit_message_text.call_args[0][0]
    session = await telegram_bot.db.get_session(1006)
    assert session["effort"] == "medium"


@pytest.mark.asyncio
async def test_get_available_projects(tmp_path: Path, monkeypatch):
    """Test get_available_projects scans directory and falls back if empty."""
    # Custom projects directory with 2 mock folders
    p1 = tmp_path / "project-alpha"
    p1.mkdir()
    p2 = tmp_path / "project_beta"
    p2.mkdir()
    hidden = tmp_path / ".hidden_project"
    hidden.mkdir()

    monkeypatch.setattr(settings, "PROJECTS_DIR", tmp_path)
    projects = get_available_projects()
    slugs = [p["slug"] for p in projects]
    assert "project-alpha" in slugs
    assert "project_beta" in slugs
    assert ".hidden_project" not in slugs

    # Test fallback when directory does not exist
    non_existent = tmp_path / "non_existent_dir"
    monkeypatch.setattr(settings, "PROJECTS_DIR", non_existent)
    fallback_projects = get_available_projects()
    assert len(fallback_projects) > 0


@pytest.mark.asyncio
async def test_projects_command_interactive(monkeypatch, tmp_path: Path):
    """Test /projects command renders interactive inline keyboard."""
    p1 = tmp_path / "demo-project"
    p1.mkdir()
    monkeypatch.setattr(settings, "PROJECTS_DIR", tmp_path)

    update = create_mock_update(user_id=1010, username="user10", text="/projects")
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.args = []

    await projects_command(update, context)
    update.message.reply_text.assert_awaited_once()
    call_args = update.message.reply_text.call_args
    text = call_args[0][0]
    reply_markup = call_args[1]["reply_markup"]

    assert "Kullanılabilir Projeler" in text
    assert len(reply_markup.inline_keyboard) >= 1
    assert any("Demo Project" in btn.text for row in reply_markup.inline_keyboard for btn in row)


@pytest.mark.asyncio
async def test_projects_command_with_arg(monkeypatch, tmp_path: Path):
    """Test /projects <slug> directly switches workspace and resets conversation."""
    target_p = tmp_path / "my-target-proj"
    target_p.mkdir()
    monkeypatch.setattr(settings, "PROJECTS_DIR", tmp_path)

    # Set prior conversation
    await telegram_bot.db.update_session(1011, conversation_id="conv-prior-111", workspace="/root")
    update = create_mock_update(user_id=1011, username="user11", text="/projects my-target-proj")
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.args = ["my-target-proj"]

    await projects_command(update, context)
    update.message.reply_text.assert_awaited_once()
    msg = update.message.reply_text.call_args[0][0]
    assert "Aktif Proje Değiştirildi" in msg

    session = await telegram_bot.db.get_session(1011)
    assert session["workspace"] == str(target_p.resolve())
    assert session["conversation_id"] is None


@pytest.mark.asyncio
async def test_callback_handler_projects_and_select(monkeypatch, tmp_path: Path):
    """Test callback interactions for cmd_projects and select_project:slug."""
    target_p = tmp_path / "quick-tool"
    target_p.mkdir()
    monkeypatch.setattr(settings, "PROJECTS_DIR", tmp_path)

    update = MagicMock(spec=Update)
    user = MagicMock(spec=User)
    user.id = 1012
    user.username = "user12"
    user.first_name = "UserTwelve"
    user.full_name = "User Twelve"

    query = AsyncMock(spec=CallbackQuery)
    query.from_user = user
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.message = AsyncMock()
    query.message.reply_text = AsyncMock()

    update.effective_user = user
    update.callback_query = query
    update.message = None
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    await telegram_bot.db.add_whitelisted_user(1012, username="user12", role="admin")
    await telegram_bot.db.update_session(1012, conversation_id="conv-prior-222", workspace="/old/path")

    # 1. Trigger cmd_projects
    query.data = "cmd_projects"
    await callback_handler(update, context)
    query.message.reply_text.assert_awaited_once()
    assert "Kullanılabilir Projeler" in query.message.reply_text.call_args[0][0]

    # 2. Trigger select_project:quick-tool
    query.data = "select_project:quick-tool"
    await callback_handler(update, context)
    query.edit_message_text.assert_awaited_once()
    assert "Aktif Proje Değiştirildi" in query.edit_message_text.call_args[0][0]

    session = await telegram_bot.db.get_session(1012)
    assert session["workspace"] == str(target_p.resolve())
    assert session["conversation_id"] is None


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

            assert "projects" in registered_cmds
            assert "project" in registered_cmds
            assert "newchat" in registered_cmds
            assert "update" in registered_cmds
            assert "usage" in registered_cmds
            assert "model" in registered_cmds
            assert "effort" in registered_cmds
            assert "status" in registered_cmds
            assert "help" in registered_cmds
            assert "cancel" in registered_cmds


@pytest.mark.asyncio
async def test_handle_incoming_message_concurrent_guard(monkeypatch):
    """Test that concurrent messages are queued and notified."""
    import asyncio
    from telegram_bot import handle_incoming_message, USER_LOCKS
    update = create_mock_update(user_id=1007, username="user7", text="Hello while busy")
    update.message.photo = None
    update.message.document = None
    update.message.voice = None
    update.message.audio = None
    update.message.caption = None
    context = MagicMock()

    # Create a locked lock
    lock = asyncio.Lock()
    await lock.acquire()
    USER_LOCKS[1007] = lock
    
    # Run the handler as a task because it will block on async with lock
    task = asyncio.create_task(handle_incoming_message(update, context))
    
    # Yield control to let task run and print the queue message
    await asyncio.sleep(0.1)
    
    update.message.reply_text.assert_awaited_once()
    reply_text = update.message.reply_text.call_args[0][0]
    assert "kuyruğa alındı" in reply_text
    
    # Release the lock so task can finish, but we also mock agy_client stream to return immediately
    async def empty_stream(*args, **kwargs):
        if False:
            yield None
    monkeypatch.setattr("telegram_bot.agy_client.run_prompt_stream", empty_stream)
    lock.release()
    await task


@pytest.mark.asyncio
async def test_cancel_command_success(monkeypatch):
    """Test /cancel command when a task is active."""
    update = create_mock_update(user_id=1008, username="user8", text="/cancel")
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    # Mock agy_client.cancel_task
    monkeypatch.setattr(telegram_bot.agy_client, "cancel_task", lambda uid: True)

    await cancel_command(update, context)
    update.message.reply_text.assert_awaited_once()
    reply_text = update.message.reply_text.call_args[0][0]
    assert "Çalışan görev iptal edildi" in reply_text



@pytest.mark.asyncio
async def test_bot_commands_list_includes_daily():
    from telegram_bot import BOT_COMMANDS
    commands = [c.command for c in BOT_COMMANDS]
    assert "daily" in commands

@pytest.mark.asyncio
async def test_build_application_daily_command():
    from telegram_bot import build_application, settings
    with patch.object(settings, "TELEGRAM_BOT_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"), patch.object(settings, "AGY_BIN_PATH", "/bin/sh"):
        app = build_application()
        handlers = app.handlers[0]
        cmd_handlers = [h for h in handlers if hasattr(h, "commands")]
        registered_cmds = set()
        for h in cmd_handlers:
            for c in h.commands:
                registered_cmds.add(c)
        assert "daily" in registered_cmds

@pytest.mark.asyncio
async def test_daily_command_missing_directory(monkeypatch):
    from telegram_bot import daily_command
    update = create_mock_update(user_id=1010, username="user10", text="/daily")
    context = MagicMock()
    context.args = []
    
    # Mock Path to always return False for exists
    with patch("telegram_bot.Path.exists", return_value=False):
        await daily_command(update, context)
        
    update.message.reply_text.assert_awaited()
    msg = update.message.reply_text.call_args[0][0]
    assert "bulunamadı" in msg.lower() or "not found" in msg.lower() or "henüz bir günlük log kaydı" in msg.lower() or "agentic os dizini" in msg.lower()

@pytest.mark.asyncio
async def test_handle_incoming_media(monkeypatch):
    from telegram_bot import handle_incoming_message, settings
    import time
    update = create_mock_update(user_id=1010, username="user10", text="")
    context = MagicMock()
    
    # mock voice
    voice_mock = MagicMock()
    voice_file_mock = AsyncMock()
    voice_file_mock.file_unique_id = "v123"
    voice_mock.get_file = AsyncMock(return_value=voice_file_mock)
    update.message.voice = voice_mock
    update.message.text = ""
    update.message.caption = ""
    update.message.audio = None
    update.message.document = None
    update.message.photo = None
    
    # mock client
    monkeypatch.setattr("telegram_bot.agy_client.is_running", lambda uid: False)
    async def empty_stream(*args, **kwargs):
        if False:
            yield None
    monkeypatch.setattr("telegram_bot.agy_client.run_prompt_stream", empty_stream)
    
    await handle_incoming_message(update, context)
    voice_file_mock.download_to_drive.assert_awaited()


@pytest.mark.asyncio
async def test_telegram_live_updater_immediate_first_and_throttling():
    from telegram_bot import TelegramLiveUpdater
    mock_msg = AsyncMock()
    updater = TelegramLiveUpdater(mock_msg, interval=0.1)

    # First update should execute immediately without waiting
    await updater.update("Status 1")
    assert mock_msg.edit_text.await_count == 1
    assert mock_msg.edit_text.call_args[0][0] == "Status 1"

    # Rapid second update within 0.1s should schedule delayed update
    await updater.update("Status 2")
    assert mock_msg.edit_text.await_count == 1  # Not yet called synchronously

    # Wait for throttle interval to expire
    await asyncio.sleep(0.15)
    assert mock_msg.edit_text.await_count == 2
    assert mock_msg.edit_text.call_args[0][0] == "Status 2"

    await updater.close()


@pytest.mark.asyncio
async def test_telegram_live_updater_error_handling_and_fallback():
    from telegram_bot import TelegramLiveUpdater
    mock_msg = AsyncMock()
    # First edit raises entity parse error, second attempt in fallback succeeds
    call_count = 0

    async def fake_edit_text(text, parse_mode=None):
        nonlocal call_count
        call_count += 1
        if parse_mode is not None:
            raise Exception("Can't parse entities: unclosed tag")
        return True

    mock_msg.edit_text = fake_edit_text
    updater = TelegramLiveUpdater(mock_msg, interval=0.05)

    await updater.update("<b>Bold unclosed")
    assert call_count == 2  # Attempted HTML, caught error and retried without parse_mode
    await updater.close()


@pytest.mark.asyncio
async def test_handle_incoming_message_live_streaming_tools_and_final_response(monkeypatch):
    """Test full live streaming updates when tools are executed."""
    from telegram_bot import handle_incoming_message
    update = create_mock_update(user_id=1020, username="user20", text="Find files and summarize")
    context = MagicMock()

    status_msg = AsyncMock()
    final_reply_msg = AsyncMock()
    update.message.reply_text = AsyncMock(side_effect=[status_msg, final_reply_msg])

    async def mock_tool_stream(*args, **kwargs):
        yield {"type": "init", "conversation_id": "conv-test-live-1"}
        yield {
            "type": "step_update",
            "step_type": "tool",
            "state": "running",
            "tool_name": "find_by_name",
            "tool_info": {"parameters": {"Pattern": "*.py", "SearchDirectory": "/root"}}
        }
        yield {
            "type": "step_update",
            "step_type": "tool",
            "state": "completed",
            "tool_name": "find_by_name",
            "duration_seconds": 0.12,
            "tool_info": {"parameters": {"Pattern": "*.py", "SearchDirectory": "/root"}}
        }
        yield {
            "type": "result",
            "conversation_id": "conv-test-live-1",
            "response": "Here are your files:\n- main.py",
            "duration_seconds": 0.5,
            "usage": {"total_tokens": 120, "thinking_tokens": 40}
        }

    monkeypatch.setattr("telegram_bot.agy_client.run_prompt_stream", mock_tool_stream)

    await handle_incoming_message(update, context)

    # Initial status reply was created
    assert update.message.reply_text.call_count >= 2
    # status_msg.edit_text was called during streaming (live progress & stages summary)
    assert status_msg.edit_text.await_count >= 1
    # Check that final message reply was sent
    final_reply_msg_args = update.message.reply_text.call_args_list[-1][0][0]
    assert "Here are your files" in final_reply_msg_args


@pytest.mark.asyncio
async def test_handle_incoming_message_no_tools_deletes_thinking_message(monkeypatch):
    """Test that when no tools are executed, the temporary thinking status message is deleted."""
    from telegram_bot import handle_incoming_message
    update = create_mock_update(user_id=1021, username="user21", text="Hello world")
    context = MagicMock()

    status_msg = AsyncMock()
    final_reply_msg = AsyncMock()
    update.message.reply_text = AsyncMock(side_effect=[status_msg, final_reply_msg])

    async def mock_text_only_stream(*args, **kwargs):
        yield {"type": "init", "conversation_id": "conv-test-direct"}
        yield {
            "type": "step_update",
            "step_type": "agent_response",
            "text_delta": "Hello from LLM!"
        }
        yield {
            "type": "result",
            "conversation_id": "conv-test-direct",
            "response": "Hello from LLM!",
            "duration_seconds": 0.2
        }

    monkeypatch.setattr("telegram_bot.agy_client.run_prompt_stream", mock_text_only_stream)

    await handle_incoming_message(update, context)

    # status_msg should be deleted since no tools were executed
    status_msg.delete.assert_awaited_once()
    # Final response delivered
    final_reply_args = update.message.reply_text.call_args_list[-1][0][0]
    assert "Hello from LLM!" in final_reply_args


