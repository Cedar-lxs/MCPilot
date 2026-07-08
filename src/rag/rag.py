"""
    RAG 查询链路 — 检索 + LLM 回答
"""
import os 
from dotenv import load_dotenv
from openai import OpenAI
from src.rag.vector_store import VectorStore
from src.utils.logger_handler import logger

load_dotenv(override=True)

# 获取API_KEY以及BASE_URL

API_KEY = os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("OPENAI_BASE_URL")


# 创建LLM客户端
client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)

LLM_MODEL = os.getenv("LLM_MODEL")



# RAG提示词模板
RAG_PROMPT_TEMPLATE = """你是一个知识库问答助手。请根据以下检索到的资料回答用户的问题。

检索到的资料：
{context}

用户问题：{question}

要求：
1. 只基于检索到的资料回答，不要编造信息
2. 如果资料不足以回答问题，直接说"资料中没有相关信息"
3. 回答简洁准确
4. **rag_query** — 从本地知识库检索信息，当问题涉及项目内部文档、知识库内容时使用
   使用方法：rag_query(question="用户的问题")

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
    response = client.chat.completions.create(
        model = LLM_MODEL,
        messages = [{
            "role": "user",
            "content": prompt
        }],
        temperature=0.3
    )

    return response.choices[0].message.content

