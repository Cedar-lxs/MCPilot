"""
    文本分块 — 把长文本切成有重叠的小段
"""
import os 
from dotenv import load_dotenv

load_dotenv(override=True)

# 从 .env 读取配置
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP"))


def chunk_text(text: str, chunk_size: int = None, chunk_overlap: int = None) -> list[str]:
    """
        把长文本切成有重叠的小段
        - text: 原始文本
        - chunk_size: 每段字符数（默认 .env 里的值）
        - chunk_overlap: 相邻段落重叠字符数（默认 .env 里的值）
        - 返回: 字符串列表
    """
    if chunk_size is None:
        chunk_size = CHUNK_SIZE
    if chunk_overlap is None:
        chunk_overlap = CHUNK_OVERLAP

    # 计算步长（每次往前走多少字符）
    step = chunk_size - chunk_overlap
    # 如果文本本身 <= chunk_size，直接返回
    if len(text) <= chunk_size:
        return [text]
    # 循环切片，直到覆盖全文本
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += step

    return chunks