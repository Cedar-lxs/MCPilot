"""
    向量存储 — ChromaDB 持久化向量库
"""
import asyncio
from uuid import uuid4

import chromadb

from src.rag.chunk import chunk_text
from src.rag.embeddings import embed_texts
from src.utils.config import CHROMA_DB_PATH, TOP_K
from src.utils.logger_handler import logger


class VectorStore:
    def __init__(self, collection_name: str = "mcpilot"):
        self.client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        self.collection = self.client.get_or_create_collection(name=collection_name)

    async def add_texts(self, texts: list[str], source: str = "") -> list[str]:
        """添加文本到向量库（自动分块 + 向量化 + 存储）"""
        all_chunks: list[str] = []
        for text in texts:
            all_chunks.extend(chunk_text(text))

        if not all_chunks:
            logger.warning("没有需要添加的文本")
            return []

        logger.info(f"正在向量化 {len(all_chunks)} 个文本块...")
        embeddings = await embed_texts(all_chunks)

        ids = [str(uuid4()) for _ in all_chunks]

        await asyncio.to_thread(
            self.collection.add,
            ids=ids,
            embeddings=embeddings,
            documents=all_chunks,
            metadatas=[{"source": source}] * len(ids),
        )

        logger.info(f"已存入 {len(ids)} 个文本块")
        return ids

    async def search(self, query: str, top_k: int = None) -> list[dict]:
        """相似度搜索，返回 [{id, document, distance}, ...]"""
        if top_k is None:
            top_k = TOP_K

        query_embeddings = await embed_texts([query])
        query_vector = query_embeddings[0]

        results = await asyncio.to_thread(
            self.collection.query,
            query_embeddings=[query_vector],
            n_results=top_k,
        )

        output = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                output.append({
                    "id": results["ids"][0][i],
                    "document": results["documents"][0][i],
                    "distance": results["distances"][0][i] if results.get("distances") else None,
                })

        return output
