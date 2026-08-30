"""
Database module for Antigravity Hub Bridge.
Uses SQLite with aiosqlite for asynchronous persistent storage.
Supports both Telegram users and WebUI sessions.
"""

import aiosqlite
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from config import settings

logger = logging.getLogger(__name__)


def _utc_now_str() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.DB_PATH

    async def init(self):
        """Initialize database schema and tables."""
        settings.ensure_directories()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            
            # User / Web sessions table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    user_id INTEGER PRIMARY KEY,
                    chat_id INTEGER,
                    conversation_id TEXT,
                    model TEXT,
                    effort TEXT,
                    workspace TEXT,
                    auto_approve INTEGER DEFAULT 1,
                    created_at TEXT,
                    updated_at TEXT
                )
            """)

            # Message history table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS message_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    conversation_id TEXT,
                    role TEXT,
                    content TEXT,
                    metadata TEXT,
                    timestamp TEXT
                )
            """)

            # Whitelisted users table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS whitelisted_users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    role TEXT DEFAULT 'user',
                    created_at TEXT
                )
            """)

            # Schema Migration: Ensure metadata column exists in message_history
            async with db.execute("PRAGMA table_info(message_history)") as cursor:
                columns = [row[1] for row in await cursor.fetchall()]
                if "metadata" not in columns:
                    await db.execute("ALTER TABLE message_history ADD COLUMN metadata TEXT;")

            # Pre-populate whitelist from settings if provided for main db
            if self.db_path == settings.DB_PATH:
                for uid in settings.ALLOWED_USER_IDS:
                    await db.execute("""
                        INSERT OR IGNORE INTO whitelisted_users (user_id, role, created_at)
                        VALUES (?, 'user', ?)
                    """, (uid, _utc_now_str()))

                for uid in settings.ADMIN_USER_IDS:
                    await db.execute("""
                        INSERT INTO whitelisted_users (user_id, role, created_at)
                        VALUES (?, 'admin', ?)
                        ON CONFLICT(user_id) DO UPDATE SET role='admin'
                    """, (uid, _utc_now_str()))

            await db.commit()
        logger.info(f"Database initialized at {self.db_path}")

    # ---------------- Whitelist Management ---------------- #

    async def is_whitelisted(self, user_id: int) -> bool:
        """Check if a user is whitelisted or if whitelist is empty."""
        async with aiosqlite.connect(self.db_path) as db:
            # Check if any whitelisted users exist
            async with db.execute("SELECT COUNT(*) FROM whitelisted_users") as cursor:
                row = await cursor.fetchone()
                total_users = row[0] if row else 0

            # If no users in whitelist and auto-whitelist first user is enabled
            if total_users == 0 and settings.AUTO_WHITELIST_FIRST_USER:
                return True

            async with db.execute("SELECT 1 FROM whitelisted_users WHERE user_id = ?", (user_id,)) as cursor:
                return (await cursor.fetchone()) is not None

    async def is_admin(self, user_id: int) -> bool:
        """Check if a user is an admin."""
        if user_id in settings.ADMIN_USER_IDS:
            return True
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT role FROM whitelisted_users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return row is not None and row[0] == "admin"

    async def add_whitelisted_user(self, user_id: int, username: Optional[str] = None,
                                   full_name: Optional[str] = None, role: str = "user"):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO whitelisted_users (user_id, username, full_name, role, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = COALESCE(excluded.username, whitelisted_users.username),
                    full_name = COALESCE(excluded.full_name, whitelisted_users.full_name),
                    role = excluded.role
            """, (user_id, username, full_name, role, _utc_now_str()))
            await db.commit()

    async def remove_whitelisted_user(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM whitelisted_users WHERE user_id = ?", (user_id,))
            await db.commit()

    async def get_whitelisted_users(self) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM whitelisted_users ORDER BY created_at ASC") as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def count_whitelisted_users(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM whitelisted_users") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    # ---------------- Session Management ---------------- #

    async def get_session(self, user_id: int = 0) -> Dict[str, Any]:
        """Get or create session settings for user (default 0 for WebUI)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            now = _utc_now_str()
            default_session = {
                "user_id": user_id,
                "chat_id": user_id,
                "conversation_id": None,
                "model": settings.DEFAULT_MODEL,
                "effort": settings.DEFAULT_EFFORT,
                "workspace": settings.DEFAULT_WORKSPACE,
                "auto_approve": 1 if settings.AUTO_APPROVE_PERMISSIONS else 0,
                "created_at": now,
                "updated_at": now
            }
            await db.execute("""
                INSERT OR IGNORE INTO user_sessions (user_id, chat_id, conversation_id, model, effort, workspace, auto_approve, created_at, updated_at)
                VALUES (:user_id, :chat_id, :conversation_id, :model, :effort, :workspace, :auto_approve, :created_at, :updated_at)
            """, default_session)
            await db.commit()

            async with db.execute("SELECT * FROM user_sessions WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else default_session

    async def update_session(self, user_id: int = 0, **kwargs):
        """Update session fields, ensuring session exists first."""
        await self.get_session(user_id)
        if not kwargs:
            return
        kwargs["updated_at"] = _utc_now_str()
        fields = ", ".join(f"{k} = :{k}" for k in kwargs.keys())
        kwargs["user_id"] = user_id

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"UPDATE user_sessions SET {fields} WHERE user_id = :user_id", kwargs)
            await db.commit()

    async def reset_session(self, user_id: int = 0) -> str:
        """Reset conversation ID to start a fresh Antigravity session."""
        await self.get_session(user_id)
        now = _utc_now_str()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE user_sessions
                SET conversation_id = NULL, updated_at = ?
                WHERE user_id = ?
            """, (now, user_id))
            await db.commit()
        return "Session reset"

    # ---------------- Message History ---------------- #

    async def add_history(self, user_id: int, conversation_id: Optional[str], role: str, content: str, metadata: Optional[str] = None):
        now = _utc_now_str()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO message_history (user_id, conversation_id, role, content, metadata, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, conversation_id, role, content, metadata, now))
            await db.commit()

    async def get_history(self, user_id: int = 0, conversation_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if conversation_id:
                query = "SELECT * FROM message_history WHERE conversation_id = ? ORDER BY id ASC LIMIT ?"
                params = (conversation_id, limit)
            else:
                query = "SELECT * FROM message_history WHERE user_id = ? ORDER BY id DESC LIMIT ?"
                params = (user_id, limit)

            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                result = [dict(r) for r in rows]
                if not conversation_id:
                    result.reverse()
                return result

    async def get_recent_conversations(self, user_id: int = 0, limit: int = 20) -> List[Dict[str, Any]]:
        """Get distinct recent conversations with last message snippet."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = """
                SELECT conversation_id, MAX(timestamp) as last_activity,
                       (SELECT content FROM message_history m2 WHERE m2.conversation_id = m1.conversation_id ORDER BY id ASC LIMIT 1) as title
                FROM message_history m1
                WHERE user_id = ? AND conversation_id IS NOT NULL AND conversation_id != ''
                GROUP BY conversation_id
                ORDER BY last_activity DESC
                LIMIT ?
            """
            async with db.execute(query, (user_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def delete_conversation(self, conversation_id: str, user_id: int = 0):
        """Delete all messages associated with a specific conversation."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM message_history WHERE conversation_id = ? AND user_id = ?", (conversation_id, user_id))
            await db.commit()

    async def clear_history(self, user_id: int = 0):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM message_history WHERE user_id = ?", (user_id,))
            await db.commit()

    # ---------------- Usage Statistics ---------------- #

    async def get_usage_stats(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Calculate comprehensive usage statistics from message history and metadata.
        Returns total sessions, message counts (all, user, assistant, last 24h),
        estimated/exact token usage, and latency metrics.
        """
        import json
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 1. Total distinct conversations
            conv_query = "SELECT COUNT(DISTINCT conversation_id) FROM message_history WHERE conversation_id IS NOT NULL AND conversation_id != ''"
            conv_params = ()
            if user_id is not None:
                conv_query += " AND user_id = ?"
                conv_params = (user_id,)

            async with db.execute(conv_query, conv_params) as cur:
                row = await cur.fetchone()
                total_sessions = row[0] if row else 0

            # 2. Fetch all messages
            msg_query = "SELECT id, user_id, conversation_id, role, content, metadata, timestamp FROM message_history"
            msg_params = ()
            if user_id is not None:
                msg_query += " WHERE user_id = ?"
                msg_params = (user_id,)

            async with db.execute(msg_query, msg_params) as cur:
                rows = await cur.fetchall()

            total_messages = len(rows)
            user_messages = 0
            assistant_messages = 0
            messages_24h = 0

            total_tokens = 0
            tokens_24h = 0
            total_duration = 0.0
            duration_count = 0

            now = datetime.now(timezone.utc)
            one_day_ago = now.timestamp() - 86400

            for r in rows:
                role = r["role"]
                content = r["content"] or ""
                metadata_str = r["metadata"]
                ts_str = r["timestamp"]

                if role == "user":
                    user_messages += 1
                elif role == "assistant":
                    assistant_messages += 1

                # Parse timestamp for 24h calculation
                is_last_24h = False
                if ts_str:
                    try:
                        dt = datetime.fromisoformat(ts_str)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        if dt.timestamp() >= one_day_ago:
                            is_last_24h = True
                            messages_24h += 1
                    except Exception:
                        pass

                # Parse token & latency from metadata or fallback to estimation
                item_tokens = 0
                has_metadata_tokens = False

                if metadata_str:
                    try:
                        meta = json.loads(metadata_str)
                        usage = meta.get("usage", {})
                        if isinstance(usage, dict) and "total_tokens" in usage and usage["total_tokens"]:
                            item_tokens = int(usage["total_tokens"])
                            has_metadata_tokens = True
                        if "duration_seconds" in meta and meta["duration_seconds"] is not None:
                            item_duration = float(meta["duration_seconds"])
                            total_duration += item_duration
                            duration_count += 1
                    except Exception:
                        pass

                if not has_metadata_tokens:
                    # Estimate tokens: approx 1 token per 4 chars
                    item_tokens = max(1, len(content) // 4) if content else 0

                total_tokens += item_tokens
                if is_last_24h:
                    tokens_24h += item_tokens

            avg_latency = round(total_duration / duration_count, 2) if duration_count > 0 else 0.0

            return {
                "total_sessions": total_sessions,
                "total_messages": total_messages,
                "user_messages": user_messages,
                "assistant_messages": assistant_messages,
                "messages_24h": messages_24h,
                "total_tokens_est": total_tokens,
                "tokens_24h_est": tokens_24h,
                "avg_latency": avg_latency,
                "total_duration": round(total_duration, 2),
                "recorded_latencies_count": duration_count
            }


def get_codex_stats(codex_dir: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
    """
    Analyze /root/.codex directory structure, database sizes, log entries, and session metrics.
    """
    import os
    import sqlite3
    target_path = Path(codex_dir) if codex_dir else Path("/root/.codex")
    if not target_path.exists() or not target_path.is_dir():
        return {
            "exists": False,
            "path": str(target_path),
            "total_size_mb": 0.0,
            "files_count": 0,
            "logs_count": 0,
            "threads_count": 0
        }

    total_size_bytes = 0
    files_count = 0
    for root, _, files in os.walk(target_path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total_size_bytes += os.path.getsize(fp)
                files_count += 1
            except OSError:
                pass

    total_size_mb = round(total_size_bytes / (1024 * 1024), 2)

    # Inspect logs_2.sqlite
    logs_db_path = target_path / "logs_2.sqlite"
    logs_count = 0
    if logs_db_path.exists():
        try:
            with sqlite3.connect(str(logs_db_path)) as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM logs")
                row = cur.fetchone()
                if row:
                    logs_count = row[0]
        except Exception:
            pass

    # Inspect state_5.sqlite for threads
    state_db_path = target_path / "state_5.sqlite"
    threads_count = 0
    if state_db_path.exists():
        try:
            with sqlite3.connect(str(state_db_path)) as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM threads")
                row = cur.fetchone()
                if row:
                    threads_count = row[0]
        except Exception:
            pass

    return {
        "exists": True,
        "path": str(target_path),
        "total_size_mb": total_size_mb,
        "files_count": files_count,
        "logs_count": logs_count,
        "threads_count": threads_count
    }


db = Database()

