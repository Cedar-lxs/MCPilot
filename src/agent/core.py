import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

from openai import OpenAI
from src.mcp_client.client import MCPClient
from src.agent.prompt import SYSTEM_PROMPT
from src.utils.logger_handler import logger

# LLM 客户端
_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
)

MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))
MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "10"))
TEMPERATURE = float(os.getenv("AGENT_TEMPERATURE", "0.3"))


async def run(
    user_input: str,
    history: list | None = None,
    mcp_client: MCPClient | None = None,
) -> tuple[str, list]:
    """
    执行一次对话，返回 (最终答案, 更新后的消息历史)

    参数:
        user_input: 用户输入
        history: 上轮的消息历史，None 表示新对话
        mcp_client: 外部传入的 MCPClient（复用连接），None 则自动创建
    返回:
        (answer, messages) 元组，messages 可传给下一轮
    """
    # 构建消息历史
    if history is None:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    else:
        messages = list(history)
    messages.append({"role": "user", "content": user_input})

    # 获取或创建 MCP 客户端
    own_mcp = mcp_client is None
    mcp = mcp_client if not own_mcp else MCPClient()

    try:
        if own_mcp:
            await mcp.connect()

        mcptools = await mcp.list_tools()
        tools = mcp.to_openai_tools(mcptools)

        for iteration in range(MAX_ITERATIONS):
            try:
                response = _client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    max_tokens=MAX_TOKENS,
                    temperature=TEMPERATURE,
                )
            except Exception as e:
                logger.error(f"LLM API 调用失败: {e}")
                return f"LLM API 调用失败: {e}", messages

            message = response.choices[0].message

            # 情况1: LLM 需要调工具
            if message.tool_calls:
                # DeepSeek 调工具时 content 可能为空，给个占位文本
                if not message.content:
                    message.content = (
                        f"我需要调用 "
                        f"{[tc.function.name for tc in message.tool_calls]}"
                        f" 来获取信息"
                    )

                messages.append(message)

                for tc in message.tool_calls:
                    tool_name = tc.function.name
                    tool_args = json.loads(tc.function.arguments)
                    try:
                        result = await mcp.call_tool(tool_name, tool_args)
                    except Exception as e:
                        logger.error(f"工具 [{tool_name}] 调用失败: {e}")
                        result = f"工具 [{tool_name}] 调用失败: {e}"

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })

            # 情况2: LLM 直接给出 Final Answer
            else:
                messages.append({"role": "assistant", "content": message.content})
                return message.content, messages

        logger.error(f"超过最大循环次数 ({MAX_ITERATIONS})，未能得到最终答案")
        return f"超过最大循环次数 ({MAX_ITERATIONS})，未能得到最终答案", messages

    finally:
        if own_mcp:
            await mcp.close()
