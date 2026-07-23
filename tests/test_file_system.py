"""测试受限文件系统 MCP 工具。"""

from pathlib import Path

import pytest

from src.mcp_server.tools.file_system import FileSystemTool


@pytest.fixture
def file_tool(tmp_path: Path) -> FileSystemTool:
    return FileSystemTool(
        root=tmp_path,
        max_read_chars=20,
        max_write_chars=20,
        max_list_entries=3,
    )


def test_definition(file_tool: FileSystemTool):
    definition = file_tool.get_definition()
    assert definition["name"] == "file_system"
    assert definition["inputSchema"]["properties"]["action"]["enum"] == [
        "list", "read", "mkdir", "write", "append"
    ]


@pytest.mark.asyncio
async def test_mkdir_write_append_read_and_list(file_tool: FileSystemTool):
    assert await file_tool.execute("mkdir", "notes", recursive=True) == "目录已创建"
    assert await file_tool.execute("write", "notes/todo.md", content="first") == "文件已写入"
    assert await file_tool.execute("append", "notes/todo.md", content=" second") == "文件已追加"
    assert await file_tool.execute("read", "notes/todo.md") == "first second"

    result = await file_tool.execute("list", "notes")
    assert "notes/todo.md（文件，12 bytes）" in result


@pytest.mark.asyncio
async def test_recursive_list_is_limited(file_tool: FileSystemTool, tmp_path: Path):
    for name in ("a.txt", "b.txt", "c.txt", "d.txt"):
        (tmp_path / name).write_text(name, encoding="utf-8")

    result = await file_tool.execute("list", ".", recursive=True)

    assert result.count("（文件，") == 3
    assert "结果已截断，最多显示 3 项" in result


@pytest.mark.asyncio
async def test_read_truncates_content(file_tool: FileSystemTool, tmp_path: Path):
    (tmp_path / "long.txt").write_text("1234567890123456789012", encoding="utf-8")

    result = await file_tool.execute("read", "long.txt")

    assert result.startswith("12345678901234567890")
    assert "内容已截断，最多返回 20 个字符" in result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"action": "remove", "path": "file.txt"}, "未知操作"),
        ({"action": "read", "path": ""}, "path 不能为空"),
        ({"action": "read", "path": "missing.txt"}, "路径不存在"),
        ({"action": "read", "path": "folder"}, "该路径是目录"),
        ({"action": "write", "path": "file.txt"}, "需要 content 文本"),
        ({"action": "write", "path": "file.exe", "content": "x"}, "不支持写入该文件类型"),
        ({"action": "write", "path": "missing/file.txt", "content": "x"}, "父目录不存在"),
        ({"action": "read", "path": "file.txt", "max_chars": 21}, "max_chars 不能超过 20"),
        ({"action": "read", "path": "file.txt", "max_chars": True}, "max_chars 必须是正整数"),
    ],
)
async def test_rejects_invalid_operations(
    file_tool: FileSystemTool, tmp_path: Path, kwargs: dict, expected: str
):
    (tmp_path / "file.txt").write_text("content", encoding="utf-8")
    (tmp_path / "folder").mkdir()

    assert expected in await file_tool.execute(**kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "../outside.txt",
        "/etc/passwd",
        "C:/Windows/system.ini",
        r"\\server\share\file.txt",
        ".env",
        ".git/config",
        "__pycache__/config.pyc",
        "private.pem",
        "service.key",
        "credentials.json",
        "id_rsa",
    ],
)
async def test_rejects_unsafe_paths(file_tool: FileSystemTool, path: str):
    result = await file_tool.execute("read", path)
    assert any(message in result for message in ("不允许", "敏感"))


@pytest.mark.asyncio
async def test_rejects_symlink_escape(file_tool: FileSystemTool, tmp_path: Path):
    outside_file = tmp_path.parent / "outside.txt"
    outside_file.write_text("secret", encoding="utf-8")
    link = tmp_path / "escape.txt"
    try:
        link.symlink_to(outside_file)
    except OSError as error:
        pytest.skip(f"当前环境不允许创建符号链接: {error}")

    assert "不允许访问符号链接" in await file_tool.execute("read", "escape.txt")


@pytest.mark.asyncio
async def test_rejects_binary_file(file_tool: FileSystemTool, tmp_path: Path):
    (tmp_path / "binary.txt").write_bytes(b"\xff\xfe")

    assert await file_tool.execute("read", "binary.txt") == "仅支持读取 UTF-8 文本文件"


@pytest.mark.asyncio
async def test_rejects_large_write(file_tool: FileSystemTool):
    result = await file_tool.execute("write", "large.txt", content="x" * 21)
    assert result == "单次写入内容不能超过 20 个字符"
