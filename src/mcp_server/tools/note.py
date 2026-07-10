"""MCP Ttool: 临时笔记"""
from src.utils.logger_handler import logger

class NoteTool:
    """临时笔记工具--Agent用来记录中间信息"""

    def __init__(self):
        self._store: dict[str, str] = {}

    def get_definition(self) -> dict:
        return {
            "name": "note_take",
            "description": "记录或读取临时笔记,辅助多步推理中记忆信息",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["write", "read", "list", "delete"],
                        "description": "操作类型:写入/读取/列出/删除"
                    },
                    "key": {
                        "type": "string",
                        "description": "笔记键名(write时候需要)"
                    },
                    "content": {
                        "type": "string",
                        "description": "笔记内容(write时候需要)"
                    }
                },
                "required":["action"]
            },
        }
    
    async def execute(self, action: str, key: str = None, content: str = None) -> str:
        """执行笔记操作"""
        logger.info(f"笔记操作:{action},key = {key}")

        if action == "write":
            if not key or content is None:
                return "write操作需要 key 和 content"
            self._store[key] = content
            logger.info(f"已经记录笔记: [{key}]")
            return f"已经记录笔记:[{key}]"
        
        elif action == "read":
            if not key:
                return f"read操作需要 key"
            val = self._store.get(key)
            if val is None:
                return f"笔记 [{key}] 不存在"
            return f"笔记: {key}: {val}"
        
        elif action == "list":
            if not self._store:
                return "暂无笔记"
            lines = [f"-{k}" for k in self._store.keys()]
            return "笔记列表:\n" + "\n".join(lines)
        
        elif action == "delete":
            if not key:
                return "delete操作需要key"
            self._store.pop(key, None)
            logger.info(f"已经删除笔记[{key}]")
            return f"已经删除笔记[{key}]"
        
        else:
            return f"未知操作:{action}, 可选:write, read, list, delete"
