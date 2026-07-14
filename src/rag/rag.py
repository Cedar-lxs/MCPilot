"""
    RAG 查询链路 — 检索 + LLM 回答
"""
from openai import OpenAI

from src.rag.vector_store import VectorStore
from src.utils.config import LLM_MODEL, OPENAI_API_KEY, OPENAI_BASE_URL
from src.utils.logger_handler import logger

# 共享 LLM 客户端（与 agent 复用同一份配置）
_rag_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _rag_client
    if _rag_client is None:
        _rag_client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
        )
    return _rag_client



# RAG提示词模板
RAG_PROMPT_TEMPLATE = """你是一个知识库问答助手。请根据以下检索到的资料回答用户的问题。

检索到的资料：
{context}

用户问题：{question}

要求：
1. 只基于检索到的资料回答，不要编造信息
2. 如果资料不足以回答问题，直接说"资料中没有相关信息"
3. 回答简洁准确
"""



async def query(question: str, top_k: int = None) -> str:
    """
        RAG 查询全流程
        - question: 用户问题
        - top_k: 检索返回的相似文档数量
        - 返回: LLM 基于检索结果生成的答案
    """
    # 1. 调用VectorStore检索
    store = VectorStore()
    results = await store.search(question, top_k = top_k)

    if not results:
        logger.info("知识库中没有找到相关内容")
        return "知识库中没有找到相关内容"

    # 2. 把检索到的文档拼装成上下文
    context = "\n\n---\n\n".join([r["document"] for r in results])

    # 3. 拼装Prompt
    prompt = RAG_PROMPT_TEMPLATE.format(context = context, question = question)

    # 4.调用LLM回答
    response = _get_client().chat.completions.create(
        model = LLM_MODEL,
        messages = [{
            "role": "user",
            "content": prompt
        }],
        temperature=0.3
    )

    return response.choices[0].message.content

