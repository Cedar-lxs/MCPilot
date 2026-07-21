import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel

from src.agent.prompt import SYSTEM_PROMPT
from src.agent.react_graph import build_graph, get_tools
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

        # 启动时一次建好LangGraph，复用
        # 1. 从 MCP 获取工具列表
        tools = await get_tools(mcp)
        # 2. 构建 LangGraph 并编译
        app.state.graph = build_graph(tools)
        
        logger.info("MCP Client 已连接，LangGraph 已初始化")
    except Exception as e:
        logger.error(f"启动失败: {e}")
        app.state.mcp_client = None
        app.state.graph = None


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
    history: list[dict] | None = None

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


def _build_messages(req: ChatRequest) -> list[BaseMessage]:
    """将 API 历史转换为 LangChain 消息，并确保包含系统提示。"""
    messages: list[BaseMessage] = []
    # any(...)检查历史里有没有system消息
    has_system = any(msg.get("role") == "system" for msg in req.history or [])
    if not has_system:
        messages.append(SystemMessage(content=SYSTEM_PROMPT))

    for msg in req.history or []:
        role = msg.get("role")
        content = msg.get("content", "")
        if role == "system":
            messages.append(SystemMessage(content=content))
        elif role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
        elif role == "tool":
            messages.append(ToolMessage(
                content=content,
                tool_call_id=msg.get("tool_call_id", ""),
            ))

    messages.append(HumanMessage(content=req.message))
    return messages


def _serialize_history(messages: list[BaseMessage]) -> list[dict]:
    """将 LangChain 消息转换为前端可复用的历史记录。"""
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


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """接收用户消息，返回 Agent 回答 + 更新后的历史"""
    mcp: MCPClient | None = getattr(app.state, "mcp_client", None)
    if not mcp:
        return ChatResponse(answer="MCP 未连接", history=req.history)
    
    # 取启动时建好的Graph
    graph = getattr(app.state, "graph", None)
    if graph is None:
        return ChatResponse(answer="服务器尚未就绪", history=req.history)
    
    langchain_messages = _build_messages(req)

    # 4. 跑图
    result = await graph.ainvoke({"messages": langchain_messages})

    # 5. 提取答案
    answer = result["messages"][-1].content
    history_dicts = _serialize_history(result["messages"])

    return ChatResponse(answer=answer, history=history_dicts)


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """以 SSE 持续推送模型 token，并在结束时返回完整历史。"""
    mcp: MCPClient | None = getattr(app.state, "mcp_client", None)
    graph = getattr(app.state, "graph", None)
    if not mcp or graph is None:
        raise HTTPException(status_code=503, detail="服务器尚未就绪")

    langchain_messages = _build_messages(req)

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
            yield f"event: done\ndata: {json.dumps({'history': _serialize_history(final_messages)}, ensure_ascii=False)}\n\n"
        else:
            yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


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
