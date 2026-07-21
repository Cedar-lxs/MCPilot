"""
会话持久化存储层 — SQLite 实现
每个方法通过 asyncio.to_thread 在线程池中执行同步 SQLite 操作，
避免在 FastAPI 事件循环中直接阻塞。
每次数据库操作独立创建短生命周期连接，不跨线程共享 connection。
"""
import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from src.utils.config import SESSION_DB_PATH
from src.utils.logger_handler import logger


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


# ── 同步实现（在 to_thread 内执行）──────────────────────────

def _initialize(db_path: str) -> None:
    conn = _connect(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL DEFAULT '',
                extra      TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_messages_session_id
            ON messages(session_id, id);
        """)
        conn.commit()
    finally:
        conn.close()


def _create_session(db_path: str, title: str) -> dict:
    session_id = str(uuid4())
    now = _now_iso()
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?,?,?,?)",
            (session_id, title, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": session_id, "title": title, "created_at": now, "updated_at": now}


def _list_sessions(db_path: str) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _get_session(db_path: str, session_id: str) -> dict | None:
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at FROM sessions WHERE id=?",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _get_messages(db_path: str, session_id: str) -> list[dict]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT role, content, extra FROM messages WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
        result = []
        for r in rows:
            entry: dict[str, Any] = {"role": r["role"], "content": r["content"]}
            extra = json.loads(r["extra"])
            entry.update(extra)
            result.append(entry)
        return result
    finally:
        conn.close()


def _replace_messages(db_path: str, session_id: str, messages: list[dict], new_title: str | None) -> None:
    """原子地替换会话的全部消息，并更新 updated_at（可选更新 title）。"""
    now = _now_iso()
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            extra_keys = {k: v for k, v in msg.items() if k not in ("role", "content")}
            extra = json.dumps(extra_keys, ensure_ascii=False)
            conn.execute(
                "INSERT INTO messages (session_id, role, content, extra, created_at) VALUES (?,?,?,?,?)",
                (session_id, role, content, extra, now),
            )
        if new_title:
            conn.execute(
                "UPDATE sessions SET updated_at=?, title=? WHERE id=?",
                (now, new_title, session_id),
            )
        else:
            conn.execute(
                "UPDATE sessions SET updated_at=? WHERE id=?",
                (now, session_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _delete_session(db_path: str, session_id: str) -> bool:
    conn = _connect(db_path)
    try:
        cur = conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ── 公共异步 API ─────────────────────────────────────────────

class SessionStore:
    def __init__(self, db_path: str = SESSION_DB_PATH):
        import os
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._db_path = db_path

    async def initialize(self) -> None:
        await asyncio.to_thread(_initialize, self._db_path)
        logger.info(f"SessionStore 初始化完成: {self._db_path}")

    async def create_session(self, title: str = "新对话") -> dict:
        return await asyncio.to_thread(_create_session, self._db_path, title)

    async def list_sessions(self) -> list[dict]:
        return await asyncio.to_thread(_list_sessions, self._db_path)

    async def get_session(self, session_id: str) -> dict | None:
        return await asyncio.to_thread(_get_session, self._db_path, session_id)

    async def get_messages(self, session_id: str) -> list[dict]:
        return await asyncio.to_thread(_get_messages, self._db_path, session_id)

    async def replace_messages(
        self,
        session_id: str,
        messages: list[dict],
        new_title: str | None = None,
    ) -> None:
        await asyncio.to_thread(_replace_messages, self._db_path, session_id, messages, new_title)

    async def delete_session(self, session_id: str) -> bool:
        return await asyncio.to_thread(_delete_session, self._db_path, session_id)
