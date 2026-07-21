"""端对端测试 /chat/stream SSE 接口"""
import asyncio
import json

import httpx
import pytest


BASE_URL = "http://localhost:8000"


async def collect_stream(message: str, history: list | None = None):
    """发起 SSE 请求，收集所有 token 和最终 done payload。"""
    payload = {"message": message, "history": history or []}
    tokens: list[str] = []
    done_payload: dict = {}

    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST", f"{BASE_URL}/chat/stream", json=payload) as resp:
            resp.raise_for_status()
            assert "text/event-stream" in resp.headers.get("content-type", "")

            buffer = ""
            async for chunk in resp.aiter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    event_str, buffer = buffer.split("\n\n", 1)
                    lines = event_str.strip().splitlines()
                    event_name = next(
                        (l[7:] for l in lines if l.startswith("event: ")), None
                    )
                    data_str = next(
                        (l[6:] for l in lines if l.startswith("data: ")), None
                    )
                    if not data_str:
                        continue
                    data = json.loads(data_str)
                    if event_name == "token":
                        tokens.append(data["token"])
                    elif event_name == "done":
                        done_payload = data

    return tokens, done_payload


@pytest.mark.asyncio
async def test_stream_produces_tokens():
    """流式接口应产生至少一个 token。"""
    tokens, _ = await collect_stream("你好，简单介绍一下你自己")
    assert len(tokens) > 0, "期望至少收到一个 token"
    full_answer = "".join(tokens)
    print(f"\n完整回答({len(tokens)} tokens): {full_answer[:100].encode('gbk', errors='replace').decode('gbk')}")


@pytest.mark.asyncio
async def test_stream_done_event_has_history():
    """done 事件应携带完整的 history 列表。"""
    _, done = await collect_stream("你好")
    assert "history" in done, "done payload 缺少 history 字段"
    history = done["history"]
    assert isinstance(history, list) and len(history) > 0
    roles = [m.get("role") for m in history]
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_stream_with_tool_call():
    """触发工具调用时，流式接口仍能正常返回 token 和 history。"""
    tokens, done = await collect_stream("现在几点？")
    full_answer = "".join(tokens)
    assert len(full_answer) > 0, "工具调用后模型应继续输出文本"

    history = done.get("history", [])
    roles = [m.get("role") for m in history]
    # 工具调用流程会产生 tool 消息
    assert "tool" in roles, "期望 history 中包含 tool 消息"
    safe = full_answer[:120].encode("gbk", errors="replace").decode("gbk")
    print(f"\n工具调用回答: {safe}")
    print(f"history 条数: {len(history)}, roles: {roles}")


@pytest.mark.asyncio
async def test_stream_history_continuity():
    """第一轮 done 返回的 history 可以直接传入第二轮，对话应保持连贯。"""
    _, done1 = await collect_stream("我叫小明")
    history = done1.get("history", [])

    tokens2, done2 = await collect_stream("我的名字是什么？", history=history)
    answer2 = "".join(tokens2)
    assert "小明" in answer2, f"模型应记住名字，实际回答: {answer2}"
    safe = answer2[:120].encode("gbk", errors="replace").decode("gbk")
    print(f"\n第二轮回答: {safe}")


if __name__ == "__main__":
    async def _main():
        print("=== test_stream_produces_tokens ===")
        tokens, _ = await collect_stream("你好，简单介绍一下你自己")
        print("".join(tokens))

        print("\n=== test_stream_with_tool_call ===")
        tokens, done = await collect_stream("现在几点？")
        print("".join(tokens))
        print(f"history 条数: {len(done.get('history', []))}")

    asyncio.run(_main())
