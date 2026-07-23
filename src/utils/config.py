"""
统一配置中心 — 所有环境变量从这里集中读取。
其他模块统一 `from src.utils.config import XXX`，不再各自调 os.getenv()。
"""
import os
from dotenv import load_dotenv

from src.utils.path_tool import get_project_root

load_dotenv(override=True)


def _int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))


# ─── LLM ─────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")
LLM_MAX_TOKENS = _int("LLM_MAX_TOKENS", 4096)
MAX_ITERATIONS = _int("MAX_ITERATIONS", 10)
AGENT_TEMPERATURE = _float("AGENT_TEMPERATURE", 0.3)

# ─── Embedding ───────────────────────────────────
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "")

# ─── RAG ─────────────────────────────────────────
CHUNK_SIZE = _int("CHUNK_SIZE", 500)
CHUNK_OVERLAP = _int("CHUNK_OVERLAP", 50)
TOP_K = _int("TOP_K", 5)

# ─── Vector Store ────────────────────────────────
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_data")

# ─── Session Store ───────────────────────────────
SESSION_DB_PATH = os.getenv("SESSION_DB_PATH", "./data/mcpilot.db")

# ─── Web Search ─────────────────────────────────
BOCHA_API_KEY = os.getenv("BOCHA_API_KEY", "")
SEARCH_TIMEOUT_SECONDS = _float("SEARCH_TIMEOUT_SECONDS", 10.0)
SEARCH_MAX_RESULTS = _int("SEARCH_MAX_RESULTS", 10)

# ─── File System Tool ────────────────────────────
FILE_SYSTEM_ROOT = os.getenv("FILE_SYSTEM_ROOT", get_project_root())
FILE_SYSTEM_MAX_READ_CHARS = _int("FILE_SYSTEM_MAX_READ_CHARS", 10000)
FILE_SYSTEM_MAX_WRITE_CHARS = _int("FILE_SYSTEM_MAX_WRITE_CHARS", 10000)
FILE_SYSTEM_MAX_LIST_ENTRIES = _int("FILE_SYSTEM_MAX_LIST_ENTRIES", 100)

# ─── API Auth ────────────────────────────────────
API_SECRET_KEY = os.getenv("API_SECRET_KEY", "")
