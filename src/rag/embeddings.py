"""
    文本向量化
"""
from typing import List

import httpx

from src.utils.config import EMBEDDING_API_KEY, EMBEDDING_BASE_URL, EMBEDDING_MODEL
from src.utils.logger_handler import logger


async def embed_texts(text: List[str]) -> List[List[float]]:
    """
        把一批文本转成向量
        - texts: 文本列表
        - 返回: 向量列表，每个向量是一堆 float

        调用 OpenAI 兼容的 Embedding API
        POST {base_url}/embeddings → 返回向量数组
    """
    # 检查 API Key 有没有配置
    if not EMBEDDING_API_KEY:
        logger.error("EMBEDDING_API_KEY 未配置")
        raise ValueError("EMBEDDING_API_KEY 未配置")
    if not EMBEDDING_BASE_URL:
        logger.error("EMBEDDING_BASE_URL 未配置")
        raise ValueError("EMBEDDING_BASE_URL 未配置")

    # 拼出完整的API URL
    url = f"{EMBEDDING_BASE_URL.rstrip('/')}/embeddings"


    # 一次全部发送所有向量化文本，导致超限
    # async with httpx.AsyncClient(timeout=30) as client:
    #     resp = await client.post(url, json={"input": text, ...})
    #     resp.raise_for_status()
    #     data = resp.json()
    #     return [item["embedding"] for item in data["data"]]


    # 分批发送，每批最多 5 个文本（避免超出 API 限制）
    batch_size = 5
    all_embeddings = []

    async with httpx.AsyncClient(timeout=30) as client:
        for i in range(0, len(text), batch_size):
            batch = text[i : i + batch_size]
            resp = await client.post(
                url,
                json={
                    "model": EMBEDDING_MODEL,
                    "input": batch,
                },
                headers={
                    "Authorization": f"Bearer {EMBEDDING_API_KEY}",
                    "Content-Type": "application/json",
                }
            )
            if resp.status_code != 200:
                logger.error(f"Embedding API 错误 ({resp.status_code}): {resp.text[:300]}")
                resp.raise_for_status()
            data = resp.json()
            all_embeddings.extend(item["embedding"] for item in data["data"])

    return all_embeddings