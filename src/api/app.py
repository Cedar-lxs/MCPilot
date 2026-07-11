import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.agent.core import run
from src.mcp_client.client import MCPClient
from src.rag.rag import query as rag_query
from src.rag.vector_store import VectorStore
from src.utils.logger_handler import logger
from src.utils.path_tool import get_project_root

app = FastAPI(title="MCPilot API", version="1.0")

PROJECT_ROOT = Path(get_project_root()).resolve()


# ── 全局 MCP Client 生命周期 ──────────────────────────────

@app.on_event("startup")
async def startup():
    """服务启动时建立 MCP Client 连接（复用，避免每次对话起子进程）"""
    mcp = MCPClient()
    try:
        await mcp.connect()
        app.state.mcp_client = mcp
        logger.info("MCP Client 已连接")
    except Exception as e:
        logger.error(f"MCP Client 启动失败: {e}")
        app.state.mcp_client = None


@app.on_event("shutdown")
async def shutdown():
    """服务关闭时断开 MCP Client"""
    mcp: MCPClient | None = getattr(app.state, "mcp_client", None)
    if mcp:
        await mcp.close()
        logger.info("MCP Client 已断开")


# ── 请求/响应模型 ─────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    history: list | None = None

class ChatResponse(BaseModel):
    answer: str
    history: list

class RagSearchRequest(BaseModel):
    question: str
    top_k: int | None = None

class RagSearchResponse(BaseModel):
    results: list[dict]

class RagQueryRequest(BaseModel):
    question: str
    top_k: int | None = None

class RagQueryResponse(BaseModel):
    answer: str


# ── 路由 ──────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """接收用户消息，返回 Agent 回答 + 更新后的历史"""
    mcp: MCPClient | None = getattr(app.state, "mcp_client", None)
    if mcp is None:
        raise HTTPException(
            status_code=503,
            detail="MCP Client 未连接，请检查服务启动日志后重启",
        )
    answer, new_history = await run(req.message, req.history, mcp_client=mcp)
    return ChatResponse(answer=answer, history=new_history)


@app.get("/health")
async def health():
    mcp_ok = getattr(app.state, "mcp_client", None) is not None
    return {"status": "ok", "mcp_connected": mcp_ok}


@app.post("/rag/search", response_model=RagSearchResponse)
async def rag_search(req: RagSearchRequest):
    """只检索知识库，返回原文"""
    store = VectorStore()
    results = await store.search(req.question, top_k=req.top_k)
    return RagSearchResponse(results=results)


@app.post("/rag/query", response_model=RagQueryResponse)
async def rag_query_route(req: RagQueryRequest):
    """检索 + LLM 回答"""
    answer = await rag_query(req.question, top_k=req.top_k)
    return RagQueryResponse(answer=answer)


@app.get("/documents")
async def list_documents():
    """查看知识库中所有文档（同步 ChromaDB 调用，放到线程池避免阻塞）"""
    store = VectorStore()
    all_data = await asyncio.to_thread(store.collection.get)
    sources = set()
    for meta in all_data.get("metadatas", []):
        if meta and "source" in meta:
            sources.add(meta["source"])
    return {"documents": sorted(sources), "total": len(all_data["ids"])}


def _resolve_safe_path(filepath: str) -> Path:
    """将路径解析到项目根目录内，防止任意文件读取"""
    path = Path(filepath)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()
    try:
        path.relative_to(PROJECT_ROOT)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"路径必须在项目目录内: {PROJECT_ROOT}",
        )
    return path


@app.post("/documents/upload")
async def upload_document(filepath: str):
    """上传文件，导入知识库（仅允许项目目录内的文件）"""
    path = _resolve_safe_path(filepath)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {filepath}")
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"不是文件: {filepath}")

    text = await asyncio.to_thread(path.read_text, encoding="utf-8")
    store = VectorStore()
    ids = await store.add_texts([text], source=path.name)
    return {"message": f"已导入 {len(ids)} 个文本块", "source": path.name}


@app.delete("/documents/{source}")
async def delete_document(source: str):
    """删除知识库中的指定文档"""
    store = VectorStore()

    # 读取元数据（同步 ChromaDB 调用，放到线程池）
    all_data = await asyncio.to_thread(store.collection.get)

    ids_to_delete = []
    for i, meta in enumerate(all_data.get("metadatas", [])):
        if meta and meta.get("source") == source:
            ids_to_delete.append(all_data["ids"][i])

    if not ids_to_delete:
        return {"error": f"未找到文档: {source}"}

    await asyncio.to_thread(store.collection.delete, ids=ids_to_delete)
    return {"message": f"已删除 {len(ids_to_delete)} 个文本块", "source": source}
