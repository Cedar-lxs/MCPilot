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
        """执行RAG 查询
        from src.rag.rag import query

        try:
            result = await query(question)
            return f"知识库回答: {result}"
        except Exception as e:
            logger.error(f"Rag查询失败:{e}")
            return f"Rag查询失败:{e}"
        """

        """执行RAG查询  只检索原文  不调LLM"""
        from src.rag.vector_store import VectorStore

        try:
            store = VectorStore()
            results = await store.search(question)
            store.close()   # 用完释放锁
            if not results:
                logger.warning("知识库中没有找到相关内容")
                return "知识库中没有找到相关内容"
            
            lines = []
            for i, r in enumerate(results, 1):
                doc = r["document"].encode("gbk", errors="replace").decode("gbk")
                lines.append(f"{i}. {doc}")

            return "知识库检索结果：\n\n" + "\n\n".join(lines)
        except Exception as e:
            logger.error(f"知识库检索失败{e}")
            return f"知识库检索失败{e}"