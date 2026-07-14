"""测试文本分块"""
from src.rag.chunk import chunk_text


def test_short_text_no_chunking():
    result = chunk_text("hello", chunk_size=500, chunk_overlap=50)
    assert result == ["hello"]


def test_chunk_splitting():
    text = "A" * 100 + "B" * 100 + "C" * 100
    result = chunk_text(text, chunk_size=110, chunk_overlap=10)
    assert len(result) == 3


def test_overlap_content():
    """相邻块之间有重叠内容"""
    text = "abcdefghij" * 20  # 200 chars
    result = chunk_text(text, chunk_size=50, chunk_overlap=10)
    # 第一块的尾部应出现在第二块的头部
    assert result[0][-10:] == result[1][:10]


def test_overlap_clamped():
    """overlap >= size 时自动降为 size // 10"""
    result = chunk_text("abc" * 100, chunk_size=100, chunk_overlap=200)
    # 不应该死循环
    assert len(result) > 0


def test_default_config():
    """使用默认的 CHUNK_SIZE / CHUNK_OVERLAP 也能正常分块"""
    text = "X" * 1200
    result = chunk_text(text)  # 不传参数，走 .env 默认值 500/50
    assert len(result) == 3
