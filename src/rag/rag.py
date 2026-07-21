"""
    RAG 查询链路 — 检索 + LLM 回答
"""
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from src.rag.vector_store import VectorStore
from src.utils.config import (
    AGENT_TEMPERATURE, LLM_MAX_TOKENS, LLM_MODEL,
    OPENAI_API_KEY, OPENAI_BASE_URL,
)
from src.utils.logger_handler import logger

_llm = ChatOpenAI(
    model=LLM_MODEL,
    api_key=OPENAI_API_KEY,
    base_url=OPENAI_BASE_URL,
    temperature=AGENT_TEMPERATURE,
    max_tokens=LLM_MAX_TOKENS,
)

_store = VectorStore()

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
    """RAG 查询全流程：检索知识库 → 拼装 Prompt → LLM 回答"""
    results = await _store.search(question, top_k=top_k)

    if not results:
        logger.info("知识库中没有找到相关内容")
        return "知识库中没有找到相关内容"

    context = "\n\n---\n\n".join([r["document"] for r in results])
    prompt = RAG_PROMPT_TEMPLATE.format(context=context, question=question)

    response = await _llm.ainvoke([HumanMessage(content=prompt)])
    return response.content
