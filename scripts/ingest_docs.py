"""导入 docs/ 目录下的文档到知识库"""
import asyncio
import sys
from pathlib import Path

# 把项目根目录加到 Python 路径
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.rag.vector_store import VectorStore


async def main():
    docs_dir = ROOT / "docs"
    store = VectorStore()

    md_files = sorted(docs_dir.glob("*.md"))
    if not md_files:
        print("docs/ 目录下没有 Markdown 文件")
        return

    for md_file in md_files:
        try:
            print(f"正在导入: {md_file.name}...")
            text = md_file.read_text(encoding="utf-8")
            ids = await store.add_texts([text], source=md_file.name)
            print(f"  → 已存入 {len(ids)} 个文本块")
        except Exception as e:
            print(f"  ❌ 导入失败: {e}")

    print(f"\n导入完成！共处理 {len(md_files)} 个文件")


asyncio.run(main())
