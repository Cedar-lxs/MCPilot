import asyncio
from fastapi import FastAPI
from pydantic import BaseModel
from src.agent.core import run
from src.rag.rag import query as rag_query
from src.rag.vector_store import VectorStore


app = FastAPI(title="MCPilot API", version="1.0")


class ChatRequest(BaseModel):
    message: str
    history: list | None = None

class ChatResponse(BaseModel):
    answer: str
    history: list


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """接收用户消息，返回 Agent 回答 + 更新后的历史"""
    answer, new_history = await run(req.message, req.history)
    return ChatResponse(answer=answer, history=new_history)

@app.get("/health")
async def health():
    return {"status": "ok"}




class RagSearchRequest(BaseModel):
    question: str
    top_k: int | None = None

class RagSearchResponse(BaseModel):
    results: list[dict]

@app.post("/rag/search", response_model=RagSearchResponse)
async def rag_search(req: RagSearchRequest):
    """只检索知识库， 返回原文"""
    store = VectorStore()
    results = await store.search(req.question, top_k=req.top_k)
    return RagSearchResponse(results = results)





class RagQueryRequest(BaseModel):
    question: str
    top_k: int | None = None

class RagQueryResponse(BaseModel):
    answer: str


@app.post("/rag/query", response_model=RagQueryResponse)
async def rag_query_route(req: RagQueryRequest):
    """检索 + LLM 回答"""
    answer = await rag_query(req.question, top_k=req.top_k)
    return RagQueryResponse(answer=answer)