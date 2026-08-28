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
        """Update session fields."""
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


db = Database()
