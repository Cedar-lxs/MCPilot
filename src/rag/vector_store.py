"""
    向量存储 — ChromaDB 持久化向量库
"""
from uuid import uuid4

import chromadb

from src.rag.chunk import chunk_text
from src.rag.embeddings import embed_texts
from src.utils.config import CHROMA_DB_PATH, TOP_K
from src.utils.logger_handler import logger


class VectorStore:
    def __init__(self, collection_name: str = "mcpilot"):
        # 创建持久化客户端，数据存到 CHROMA_DB_PATH 目录
        self.client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        # 获取或创建集合（Collection ≈ 一张表）
        self.collection = self.client.get_or_create_collection(name=collection_name)

    async def add_texts(self, texts: list[str], source: str = "") -> list[str]:
        """添加文本到向量库（自动分块 + 向量化 + 存储）"""
        # 1. 每条文本先切块
        all_chunks : list[str] = []
        for text in texts:
            chunks= chunk_text(text)
            all_chunks.extend(chunks)

        if not all_chunks:
            logger.warning("没有需要添加的文本")
            return []
        
        # 2. 批量向量化所有文本块
        logger.info(f"正在向量化{len(all_chunks)}个文本块...")
        embeddings = await embed_texts(all_chunks)

        # 3. 生成唯一 id
        ids = [str(uuid4()) for _ in all_chunks]

        # 4. 存入ChromaDB（ids, documents, embeddings 三个列表长度一致）
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=all_chunks,
            metadatas=[{"source": source}] * len(ids)
        )

        logger.info(f"已存入 {len(ids)} 个文本块")

        return ids
    

    async def search(self, query: str, top_k: int = None) -> list[dict]:
        """相似度搜索，返回 [{id, document, distance}, ...]"""
        if top_k is None:
            top_k = TOP_K

        # 1. 把用户的查询也转换成向量
        query_embeddings = await embed_texts([query])
        query_vector = query_embeddings[0]  # embed_texts 返回 list[list[float]]，取第一个

        # 2.Chroma 相似度查询
        results = self.collection.query(
            query_embeddings= [query_vector],
            n_results= top_k,
        )

        # 3. 整理成[{id, document, distance},...]
        output = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                output.append({
                    "id": results["ids"][0][i],
                    "document": results["documents"][0][i],
                    "distance": results["distances"][0][i] if results.get("distances") else None,
                })

        return output