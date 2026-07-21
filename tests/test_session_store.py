"""SessionStore 单元测试 — 使用临时数据库，不依赖运行中的服务"""
import json
import pytest
import pytest_asyncio
import tempfile
import os

from src.session.store import SessionStore


@pytest_asyncio.fixture
async def store(tmp_path):
    db_path = str(tmp_path / "test.db")
    s = SessionStore(db_path=db_path)
    await s.initialize()
    return s


# ── 初始化 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_initialize_creates_tables(tmp_path):
    import sqlite3
    db_path = str(tmp_path / "init.db")
    s = SessionStore(db_path=db_path)
    await s.initialize()
    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()
    assert "sessions" in tables
    assert "messages" in tables


@pytest.mark.asyncio
async def test_initialize_idempotent(tmp_path):
    db_path = str(tmp_path / "idempotent.db")
    s = SessionStore(db_path=db_path)
    await s.initialize()
    await s.initialize()  # 二次初始化不应报错


# ── 创建与列出会话 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_session_returns_id_and_title(store):
    session = await store.create_session("测试会话")
    assert session["id"]
    assert session["title"] == "测试会话"
    assert session["created_at"]
    assert session["updated_at"]


@pytest.mark.asyncio
async def test_list_sessions_empty(store):
    sessions = await store.list_sessions()
    assert sessions == []


@pytest.mark.asyncio
async def test_list_sessions_ordered_by_updated_at_desc(store):
    s1 = await store.create_session("第一条")
    s2 = await store.create_session("第二条")
    sessions = await store.list_sessions()
    ids = [s["id"] for s in sessions]
    assert ids[0] == s2["id"]
    assert ids[1] == s1["id"]


# ── 获取单个会话 ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_session_exists(store):
    created = await store.create_session("detail test")
    fetched = await store.get_session(created["id"])
    assert fetched is not None
    assert fetched["id"] == created["id"]
    assert fetched["title"] == "detail test"


@pytest.mark.asyncio
async def test_get_session_not_exists(store):
    result = await store.get_session("nonexistent-uuid")
    assert result is None


# ── 消息持久化 ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_messages_empty(store):
    s = await store.create_session("empty")
    msgs = await store.get_messages(s["id"])
    assert msgs == []


@pytest.mark.asyncio
async def test_replace_and_get_plain_messages(store):
    s = await store.create_session("plain")
    messages = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！有什么可以帮你的？"},
    ]
    await store.replace_messages(s["id"], messages)
    restored = await store.get_messages(s["id"])
    assert len(restored) == 3
    assert restored[0]["role"] == "system"
    assert restored[1]["content"] == "你好"
    assert restored[2]["content"] == "你好！有什么可以帮你的？"


@pytest.mark.asyncio
async def test_replace_messages_with_tool_calls(store):
    s = await store.create_session("tool_calls")
    tool_calls = [
        {
            "id": "call_123",
            "type": "function",
            "function": {"name": "datetime_now", "arguments": "{}"},
        }
    ]
    messages = [
        {"role": "user", "content": "现在几点"},
        {"role": "assistant", "content": "", "tool_calls": tool_calls},
        {"role": "tool", "content": "当前时间是10:00", "tool_call_id": "call_123"},
        {"role": "assistant", "content": "现在是10:00"},
    ]
    await store.replace_messages(s["id"], messages)
    restored = await store.get_messages(s["id"])

    assert len(restored) == 4
    ai_msg = restored[1]
    assert "tool_calls" in ai_msg
    assert ai_msg["tool_calls"][0]["id"] == "call_123"
    assert ai_msg["tool_calls"][0]["function"]["name"] == "datetime_now"

    tool_msg = restored[2]
    assert tool_msg["role"] == "tool"
    assert tool_msg["tool_call_id"] == "call_123"
    assert tool_msg["content"] == "当前时间是10:00"


@pytest.mark.asyncio
async def test_replace_messages_is_atomic(store):
    s = await store.create_session("atomic")
    first = [{"role": "user", "content": "第一轮"}]
    await store.replace_messages(s["id"], first)

    second = [
        {"role": "user", "content": "第一轮"},
        {"role": "assistant", "content": "回答"},
        {"role": "user", "content": "第二轮"},
    ]
    await store.replace_messages(s["id"], second)

    restored = await store.get_messages(s["id"])
    assert len(restored) == 3
    assert restored[2]["content"] == "第二轮"


@pytest.mark.asyncio
async def test_replace_messages_updates_title(store):
    s = await store.create_session("旧标题")
    await store.replace_messages(s["id"], [], new_title="新标题")
    updated = await store.get_session(s["id"])
    assert updated["title"] == "新标题"


@pytest.mark.asyncio
async def test_replace_messages_updates_updated_at(store):
    import time
    s = await store.create_session("ts test")
    old_ts = s["updated_at"]
    time.sleep(0.01)
    await store.replace_messages(s["id"], [{"role": "user", "content": "hi"}])
    updated = await store.get_session(s["id"])
    assert updated["updated_at"] >= old_ts


# ── 删除会话 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_session_removes_session(store):
    s = await store.create_session("to delete")
    deleted = await store.delete_session(s["id"])
    assert deleted is True
    assert await store.get_session(s["id"]) is None


@pytest.mark.asyncio
async def test_delete_session_cascades_messages(store):
    import sqlite3 as _sqlite3
    s = await store.create_session("cascade")
    await store.replace_messages(s["id"], [{"role": "user", "content": "hi"}])
    await store.delete_session(s["id"])

    conn = _sqlite3.connect(store._db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE session_id=?", (s["id"],)
    ).fetchone()[0]
    conn.close()
    assert count == 0


@pytest.mark.asyncio
async def test_delete_nonexistent_session_returns_false(store):
    result = await store.delete_session("no-such-id")
    assert result is False
