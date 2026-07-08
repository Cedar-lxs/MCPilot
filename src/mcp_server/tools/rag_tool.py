"""MCP Tool: RAG 知识库查询"""
from src.utils.logger_handler import logger


class RagTool:
    """RAG 知识库查询"""

    def get_definition(self) -> dict:
        return {
            "name": "rag_query",
            "description": "从本地知识库检索信息，支持 RAG 增强问答。当用户问到可能存在于知识库中的内容时使用",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "用户的问题",
                    },
                },
                "required": ["question"],
            },
        }
    
    async def execute(self, question: str) -> str:
        """执行RAG 查询"""
        from src.rag.rag import query

        try:
            result = await query(question)
            return f"知识库回答: {result}"
        except Exception as e:
            logger.error(f"Rag查询失败:{e}")
            return f"Rag查询失败:{e}"