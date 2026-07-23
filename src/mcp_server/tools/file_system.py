"""MCP Tool: sandboxed file system operations."""

import asyncio
from pathlib import Path, PurePosixPath, PureWindowsPath

from src.utils.config import (
    FILE_SYSTEM_MAX_LIST_ENTRIES,
    FILE_SYSTEM_MAX_READ_CHARS,
    FILE_SYSTEM_MAX_WRITE_CHARS,
    FILE_SYSTEM_ROOT,
)
from src.utils.logger_handler import logger


class FileSystemTool:
    """在受限根目录内安全地读写常见文本文件。"""

    ACTIONS = {"list", "read", "mkdir", "write", "append"}
    WRITABLE_SUFFIXES = {
        ".txt", ".md", ".json", ".yaml", ".yml", ".csv", ".py", ".js", ".ts",
        ".html", ".css", ".xml", ".toml", ".ini", ".log",
    }
    SENSITIVE_PARTS = {".git", ".env", "__pycache__"}
    SENSITIVE_FILE_NAMES = {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}
    SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}

    def __init__(
        self,
        root: str | Path | None = None,
        max_read_chars: int | None = None,
        max_write_chars: int | None = None,
        max_list_entries: int | None = None,
    ) -> None:
        configured_root = FILE_SYSTEM_ROOT if root is None else root
        self.root = Path(configured_root).resolve()
        self.max_read_chars = FILE_SYSTEM_MAX_READ_CHARS if max_read_chars is None else max_read_chars
        self.max_write_chars = FILE_SYSTEM_MAX_WRITE_CHARS if max_write_chars is None else max_write_chars
        self.max_list_entries = FILE_SYSTEM_MAX_LIST_ENTRIES if max_list_entries is None else max_list_entries

    def get_definition(self) -> dict:
        return {
            "name": "file_system",
            "description": "在项目受限目录内列出、读取、创建及写入常见文本文件；无法删除、移动或访问敏感文件",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "read", "mkdir", "write", "append"],
                        "description": "操作类型：列出、读取、创建目录、覆写或追加文本文件",
                    },
                    "path": {
                        "type": "string",
                        "description": "相对于项目根目录的路径；禁止绝对路径、.. 和敏感路径",
                    },
                    "content": {"type": "string", "description": "write 或 append 的 UTF-8 文本内容"},
                    "recursive": {
                        "type": "boolean",
                        "description": "list 或 mkdir 是否递归处理，默认 false",
                        "default": False,
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "read 最大返回字符数，受服务端上限约束",
                        "minimum": 1,
                    },
                },
                "required": ["action", "path"],
            },
        }

    async def execute(
        self,
        action: str,
        path: str,
        content: str | None = None,
        recursive: bool = False,
        max_chars: int | None = None,
    ) -> str:
        if action not in self.ACTIONS:
            return "未知操作，可选: list, read, mkdir, write, append"
        if not isinstance(recursive, bool):
            return "recursive 必须是布尔值"
        if max_chars is not None and (not isinstance(max_chars, int) or isinstance(max_chars, bool) or max_chars < 1):
            return "max_chars 必须是正整数"
        if max_chars is not None and max_chars > self.max_read_chars:
            return f"max_chars 不能超过 {self.max_read_chars}"

        try:
            target = self._resolve_path(path)
            if action in {"write", "append"}:
                self._validate_write(target, content)
            logger.info("文件系统操作: action=%s, path=%s", action, target.relative_to(self.root))
            if action == "list":
                return await asyncio.to_thread(self._list, target, recursive)
            if action == "read":
                return await asyncio.to_thread(self._read, target, max_chars or self.max_read_chars)
            if action == "mkdir":
                return await asyncio.to_thread(self._mkdir, target, recursive)
            return await asyncio.to_thread(self._write, target, content or "", action == "append")
        except UnicodeDecodeError:
            return "仅支持读取 UTF-8 文本文件"
        except FileNotFoundError:
            return "路径不存在"
        except IsADirectoryError:
            return "该路径是目录，不能作为文件操作"
        except PermissionError:
            return "没有权限访问该路径"
        except ValueError as error:
            logger.warning("文件系统操作被拒绝: action=%s, reason=%s", action, error)
            return str(error)
        except OSError as error:
            logger.error("文件系统操作失败: action=%s, error=%s", action, error)
            return "文件系统操作失败，请检查路径后重试"

    def _resolve_path(self, user_path: str) -> Path:
        if not isinstance(user_path, str) or not user_path.strip():
            raise ValueError("path 不能为空")
        normalized = user_path.strip().replace("\\", "/")
        windows_path = PureWindowsPath(normalized)
        posix_path = PurePosixPath(normalized)
        relative_path = Path(normalized)
        if relative_path.is_absolute() or posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
            raise ValueError("不允许使用绝对路径")
        if any(part == ".." for part in relative_path.parts):
            raise ValueError("不允许使用路径穿越")
        if self._is_sensitive(relative_path):
            raise ValueError("不允许访问敏感路径或文件")

        candidate = self.root / relative_path
        current = self.root
        for part in relative_path.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("不允许访问符号链接")
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as error:
            raise ValueError("路径超出允许范围") from error
        return resolved

    def _is_sensitive(self, relative_path: Path) -> bool:
        parts = {part.lower() for part in relative_path.parts}
        filename = relative_path.name.lower()
        return (
            bool(parts & self.SENSITIVE_PARTS)
            or filename in self.SENSITIVE_FILE_NAMES
            or filename.startswith("credentials")
            or filename.endswith(tuple(self.SENSITIVE_SUFFIXES))
        )

    def _validate_write(self, target: Path, content: str | None) -> None:
        if not isinstance(content, str):
            raise ValueError("write 和 append 操作需要 content 文本")
        if len(content) > self.max_write_chars:
            raise ValueError(f"单次写入内容不能超过 {self.max_write_chars} 个字符")
        if target.suffix.lower() not in self.WRITABLE_SUFFIXES:
            raise ValueError("不支持写入该文件类型")
        if target.exists() and (target.is_symlink() or not target.is_file()):
            raise ValueError("目标必须是普通文件")
        if not target.parent.exists():
            raise ValueError("父目录不存在，请先创建目录")

    def _list(self, target: Path, recursive: bool) -> str:
        if not target.exists():
            raise FileNotFoundError
        if not target.is_dir():
            raise ValueError("list 操作需要目录路径")

        entries: list[str] = []
        pending = [target]
        truncated = False
        while pending and len(entries) < self.max_list_entries:
            directory = pending.pop(0)
            for child in sorted(directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
                relative = child.relative_to(self.root)
                if self._is_sensitive(relative) or child.is_symlink():
                    continue
                kind = "目录" if child.is_dir() else "文件"
                size = "" if child.is_dir() else f"，{child.stat().st_size} bytes"
                entries.append(f"- {relative.as_posix()}（{kind}{size}）")
                if child.is_dir() and recursive:
                    pending.append(child)
                if len(entries) >= self.max_list_entries:
                    truncated = True
                    break
        if not entries:
            return "目录为空或不包含可访问项"
        suffix = f"\n[结果已截断，最多显示 {self.max_list_entries} 项]" if truncated else ""
        return "目录内容:\n" + "\n".join(entries) + suffix

    def _read(self, target: Path, max_chars: int) -> str:
        if not target.exists():
            raise FileNotFoundError
        if not target.is_file():
            raise IsADirectoryError
        content = target.read_text(encoding="utf-8")
        if len(content) > max_chars:
            return content[:max_chars].rstrip() + f"\n\n[内容已截断，最多返回 {max_chars} 个字符]"
        return content

    @staticmethod
    def _mkdir(target: Path, recursive: bool) -> str:
        target.mkdir(parents=recursive, exist_ok=True)
        return "目录已创建"

    @staticmethod
    def _write(target: Path, content: str, append: bool) -> str:
        mode = "a" if append else "w"
        with target.open(mode, encoding="utf-8", newline="") as file:
            file.write(content)
        return "文件已追加" if append else "文件已写入"
