"""测试 note 工具"""
import pytest

from src.mcp_server.tools.note import NoteTool


@pytest.fixture
def note():
    return NoteTool()


@pytest.mark.asyncio
async def test_write_and_read(note: NoteTool):
    await note.execute("write", key="test_key", content="hello world")
    result = await note.execute("read", key="test_key")
    assert "hello world" in result


@pytest.mark.asyncio
async def test_read_nonexistent(note: NoteTool):
    result = await note.execute("read", key="no_such_key")
    assert "不存在" in result


@pytest.mark.asyncio
async def test_list(note: NoteTool):
    await note.execute("write", key="a", content="1")
    await note.execute("write", key="b", content="2")
    result = await note.execute("list")
    assert "a" in result
    assert "b" in result


@pytest.mark.asyncio
async def test_delete(note: NoteTool):
    await note.execute("write", key="to_delete", content="x")
    result = await note.execute("delete", key="to_delete")
    assert "已经删除" in result
    # 确认已删
    result2 = await note.execute("read", key="to_delete")
    assert "不存在" in result2


@pytest.mark.asyncio
async def test_write_requires_key_and_content(note: NoteTool):
    result = await note.execute("write")
    assert "需要 key 和 content" in result


@pytest.mark.asyncio
async def test_unknown_action(note: NoteTool):
    result = await note.execute("unknown_action")
    assert "未知操作" in result
