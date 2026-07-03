import asyncio
from fastapi import FastAPI
from pydantic import BaseModel
from src.agent.core import run


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