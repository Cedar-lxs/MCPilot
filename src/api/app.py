import asyncio
import json
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel

from src.agent.prompt import SYSTEM_PROMPT
from src.agent.react_graph import build_graph, get_tools
from src.mcp_client.client import MCPClient
from src.rag.rag import _store as vector_store
from src.rag.rag import query as rag_query
from src.session.store import SessionStore
from src.utils.config import API_SECRET_KEY
from src.utils.logger_handler import logger
from src.utils.path_tool import get_project_root

app = FastAPI(title="MCPilot API", version="1.0")

PROJECT_ROOT = Path(get_project_root()).resolve()

_session_store = SessionStore()

# ── API Key 认证中间件 ────────────────────────────────────

_EXEMPT_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if not API_SECRET_KEY:             # 未配置则关闭认证，本地开发不受影响
        return await call_next(request)

    if request.url.path in _EXEMPT_PATHS:    # /health /docs 不需要认证
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()

    # 防时序攻击，使用 secrets.compare_digest 做常量时间比较，防止时序侧信道攻击
    if not secrets.compare_digest(token, API_SECRET_KEY):
        return JSONResponse(status_code=401, content={"detail": "未授权：API Key 无效或缺失"})

    return await call_next(request)


# ── 全局生命周期 ──────────────────────────────────────────

@app.on_event("startup")
async def startup():
    await _session_store.initialize()

    mcp = MCPClient()
    try:
        await mcp.connect()
        app.state.mcp_client = mcp
        tools = await get_tools(mcp)
        app.state.graph = build_graph(tools)
        logger.info("MCP Client 已连接，LangGraph 已初始化")
    except Exception as e:
        logger.error(f"启动失败: {e}")
        app.state.mcp_client = None
        app.state.graph = None


@app.on_event("shutdown")
async def shutdown():
    mcp: MCPClient | None = getattr(app.state, "mcp_client", None)
    if mcp:
        await mcp.close()
        logger.info("MCP Client 已断开")


# ── 请求/响应模型 ─────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    history: list[dict] | None = None

class ChatResponse(BaseModel):
    answer: str
    history: list
    session_id: str | None = None

class SessionCreateRequest(BaseModel):
    title: str = "新对话"

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


# ── 工具函数 ──────────────────────────────────────────────

def _make_title(text: str, max_len: int = 30) -> str:
    text = text.strip()
    return text if len(text) <= max_len else text[:max_len] + "…"


def _build_messages_from_history(history: list[dict], new_message: str) -> list[BaseMessage]:
    """将历史记录列表转换为 LangChain 消息，确保包含系统提示。"""
    messages: list[BaseMessage] = []
    has_system = any(msg.get("role") == "system" for msg in history)
    if not has_system:
        messages.append(SystemMessage(content=SYSTEM_PROMPT))

    for msg in history:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "system":
            messages.append(SystemMessage(content=content))
        elif role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            ai_msg = AIMessage(content=content)
            if msg.get("tool_calls"):
                ai_msg.tool_calls = [
                    {
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "args": json.loads(tc["function"]["arguments"]),
                    }
                    for tc in msg["tool_calls"]
                ]
            messages.append(ai_msg)
        elif role == "tool":
            messages.append(ToolMessage(
                content=content,
                tool_call_id=msg.get("tool_call_id", ""),
            ))

    messages.append(HumanMessage(content=new_message))
    return messages


def _build_messages(req: ChatRequest) -> list[BaseMessage]:
    """从请求中构建消息列表（兼容旧接口 history 字段）。"""
    return _build_messages_from_history(req.history or [], req.message)


def _serialize_history(messages: list[BaseMessage]) -> list[dict]:
    """将 LangChain 消息序列化为 JSON 兼容的字典列表。"""
    history = []
    role_map = {"human": "user", "ai": "assistant", "system": "system", "tool": "tool"}

    for msg in messages:
        entry = {"role": role_map.get(msg.type, msg.type), "content": msg.content or ""}

        if hasattr(msg, "tool_calls") and msg.tool_calls:
            entry["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["args"], ensure_ascii=False),
                    },
                }
                for tc in msg.tool_calls
            ]

        if msg.type == "tool" and hasattr(msg, "tool_call_id"):
            entry["tool_call_id"] = msg.tool_call_id

        history.append(entry)

    return history


async def _load_history_for_request(req: ChatRequest) -> tuple[list[dict], bool]:
    """
    根据请求加载历史记录。
    返回 (history_dicts, from_db)：
    - from_db=True 表示从数据库加载，会话必须在对话完成后写回。
    - from_db=False 表示使用前端传来的 history（兼容旧接口）。
    """
    if req.session_id:
        session = await _session_store.get_session(req.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"会话不存在: {req.session_id}")
        msgs = await _session_store.get_messages(req.session_id)
        return msgs, True
    return req.history or [], False


async def _persist_history(
    session_id: str | None,
    from_db: bool,
    history_dicts: list[dict],
    first_user_message: str,
) -> None:
    """将对话结果写回数据库（仅当使用 session_id 时）。"""
    if not (session_id and from_db):
        return
    has_user = any(m.get("role") == "user" for m in history_dicts)
    title = _make_title(first_user_message) if has_user else None
    await _session_store.replace_messages(session_id, history_dicts, new_title=title)


# ── 会话管理接口 ──────────────────────────────────────────

@app.post("/sessions")
async def create_session(req: SessionCreateRequest):
    session = await _session_store.create_session(req.title)
    return session


@app.get("/sessions")
async def list_sessions():
    sessions = await _session_store.list_sessions()
    return {"sessions": sessions}


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    session = await _session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
    messages = await _session_store.get_messages(session_id)
    return {**session, "messages": messages}


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    deleted = await _session_store.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")
    return {"deleted": True, "session_id": session_id}


# ── 聊天接口 ──────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    mcp: MCPClient | None = getattr(app.state, "mcp_client", None)
    if not mcp:
        return ChatResponse(answer="MCP 未连接", history=req.history or [], session_id=req.session_id)

    graph = getattr(app.state, "graph", None)
    if graph is None:
        return ChatResponse(answer="服务器尚未就绪", history=req.history or [], session_id=req.session_id)

    history_dicts, from_db = await _load_history_for_request(req)
    langchain_messages = _build_messages_from_history(history_dicts, req.message)

    result = await graph.ainvoke({"messages": langchain_messages})

    answer = result["messages"][-1].content
    final_history = _serialize_history(result["messages"])

    await _persist_history(req.session_id, from_db, final_history, req.message)

    return ChatResponse(answer=answer, history=final_history, session_id=req.session_id)


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    mcp: MCPClient | None = getattr(app.state, "mcp_client", None)
    graph = getattr(app.state, "graph", None)
    if not mcp or graph is None:
        raise HTTPException(status_code=503, detail="服务器尚未就绪")

    history_dicts, from_db = await _load_history_for_request(req)
    langchain_messages = _build_messages_from_history(history_dicts, req.message)

    async def generate():
        final_messages: list[BaseMessage] | None = None
        async for event in graph.astream_events(
            {"messages": langchain_messages},
            version="v2",
        ):
            if event["event"] == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                content = chunk.content
                if isinstance(content, str) and content:
                    yield f"event: token\ndata: {json.dumps({'token': content}, ensure_ascii=False)}\n\n"
            elif event["event"] == "on_chain_end":
                output = event["data"].get("output")
                if isinstance(output, dict) and isinstance(output.get("messages"), list):
                    final_messages = output["messages"]

        if final_messages is not None:
            final_history = _serialize_history(final_messages)
            await _persist_history(req.session_id, from_db, final_history, req.message)
            done_data = {"history": final_history, "session_id": req.session_id}
            yield f"event: done\ndata: {json.dumps(done_data, ensure_ascii=False)}\n\n"
        else:
            yield f"event: done\ndata: {json.dumps({'session_id': req.session_id})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


# ── 健康检查 ──────────────────────────────────────────────

@app.get("/health")
async def health():
    mcp_ok = getattr(app.state, "mcp_client", None) is not None
    return {"status": "ok", "mcp_connected": mcp_ok}


# ── RAG 接口 ──────────────────────────────────────────────

@app.post("/rag/search", response_model=RagSearchResponse)
async def rag_search(req: RagSearchRequest):
    results = await vector_store.search(req.question, top_k=req.top_k)
    return RagSearchResponse(results=results)


@app.post("/rag/query", response_model=RagQueryResponse)
async def rag_query_route(req: RagQueryRequest):
    answer = await rag_query(req.question, top_k=req.top_k)
    return RagQueryResponse(answer=answer)


@app.get("/documents")
async def list_documents():
    all_data = await asyncio.to_thread(vector_store.collection.get)
    sources = set()
    for meta in all_data.get("metadatas", []):
        if meta and "source" in meta:
            sources.add(meta["source"])
    return {"documents": sorted(sources), "total": len(all_data["ids"])}


def _resolve_safe_path(filepath: str) -> Path:
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
    path = _resolve_safe_path(filepath)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {filepath}")
    if not path.is_file():
        raise HTTPException(status_code=400, detail=f"不是文件: {filepath}")
    text = await asyncio.to_thread(path.read_text, encoding="utf-8")
    ids = await vector_store.add_texts([text], source=path.name)
    return {"message": f"已导入 {len(ids)} 个文本块", "source": path.name}


@app.delete("/documents/{source}")
async def delete_document(source: str):
    all_data = await asyncio.to_thread(vector_store.collection.get)
    ids_to_delete = [
        all_data["ids"][i]
        for i, meta in enumerate(all_data.get("metadatas", []))
        if meta and meta.get("source") == source
    ]
    if not ids_to_delete:
        return {"error": f"未找到文档: {source}"}
    await asyncio.to_thread(vector_store.collection.delete, ids=ids_to_delete)
    return {"message": f"已删除 {len(ids_to_delete)} 个文本块", "source": source}
