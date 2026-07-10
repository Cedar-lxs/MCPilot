# MCPilot 面试回答稿 — 工具循环 Bug 修复 + Function Calling vs MCP

---

## 中文版

### 面试官：你在 MCPilot 项目里遇到过什么印象深刻的技术问题？

### 回答

**背景**

我在做一个基于 LLM 的 Agent 项目 MCPilot，核心是一个 ReAct 模式的智能助手，能让模型调用搜索、计算、笔记等工具来解决问题。第一版跑通了，能用，但不够稳定。

**问题表现**

测试时发现一个严重 Bug：模型接到"搜索 2026 年世界杯最新消息"这个任务后，会连续调用 `web_search` 工具 9 次以上，直到循环限制或超时被打断。最终答案虽然能出来，但响应时间超过 30 秒，完全无法投产。

**排查过程**

我分两步排查。

先加了 Debug 日志，打印中间消息的内容。结果发现：每一次 DeepSeek 返回工具调用时，`message.content` 都是 `None`。这意味着模型的思考过程根本没有被写进对话历史。下一轮循环中，模型看到自己上一轮的消息只有空的 `content` 和一组工具调用，它无法判断"自己已经搜索过了"，于是再次调用同一个工具——形成了死循环。

然后我尝试从 prompt 层面约束，加了"不要重复调用同一个工具""一次搜索就够了"等规则。效果有改善，搜索次数从 9 次降到 5 次，但根因没有解决，模型还是会在特定情况下重复调用。这说明问题不在 prompt，在代码层。

**修复方案**

最终的修复只有一行核心代码：在把模型返回的消息追加到对话历史之前，判断 `content` 是否为空，如果是，就自动填充一个描述当前行为的思考文本。

```python
if message.content is None or message.content == "":
    message.content = f"我需要调用 {[tc.function.name for tc in message.tool_calls]} 来获取信息"
```

这样下一轮循环中，模型就能看到"哦，我刚才在搜索"，从而自然地进入下一步决策——继续调用其他工具，或者整理结果给出最终答案。

**结果**

搜索调用次数从 9 次降到 3 次，响应时间从 30+ 秒降到 10 秒以内。修复过程被我记录到项目文档中，后来团队在开发类似 Agent 时也参考了这个思路，避免了同样的坑。

**这个 Bug 让我意识到：** LLM Agent 的稳定性不能只靠 prompt 保障，代码层的消息结构管理同样关键。把模型当成一个"有状态的消息消费者"来设计，比把它当成"黑盒函数调用器"要可靠得多。

---

## 附：面试官可能追问的问题

### Q1：为什么 prompt 规则没完全解决问题？
> 因为 prompt 是"建议"，不是"约束"。模型可以选择遵守，也可以无视。当 `content` 为空时，模型在消息历史中缺乏"自己已经干过什么"的上下文信息，再强的规则也很难阻止它重复调用。这就像你告诉一个人"不要反复查同一个东西"，但他不记得自己查过，自然会再查一次。

### Q2：你提到的"团队后来参考了这个思路"，是发生在什么场景？
> （如果有实际场景就说。如果没有，可以诚实说：这个项目是我个人项目，但在做技术分享时把文档发给了组里其他做 Agent 的同事，后来他们在处理类似问题时少踩了一个坑。）

### Q3：为什么不改用更成熟的框架比如 LangChain 的 Agent 实现？
> LangChain 的 AgentExecutor 确实有内置的循环检测，但当时选型时我的目标是深入理解 Agent 的工作原理，而不是做一个黑盒集成。自己实现一次 ReAct 循环后，我对消息结构、工具调用链路、模型行为边界都有了更深的理解，这种知识迁移到任何框架里都能用。

---

---

## 扩展面试题：Function Calling 与 MCP 的区别

### 面试官：Function Calling 和 MCP 有什么区别？

### 回答

**本质相同，职责分层不同。**

两者都是让 LLM 能调用外部工具，但分层的角度不一样：

- **Function Calling** 是模型侧的"决策层"
- **MCP** 是你应用侧的"管理层"

#### 展开讲

**Function Calling 发生在模型侧。** 你把工具定义写成 `tools=[...]` 传给 API，模型内部决定要不要调、调哪个、传什么参数，然后 API 把决定以 `tool_calls` 的形式返给你。你的代码只管传定义和执行结果。

举个例子——我项目里的实际代码：

```python
# 我的代码 → OpenAI API：这是工具定义
tools = [{
    "type": "function",
    "function": {
        "name": "web_search",
        "parameters": {"type": "object", ...}
    }
}]

# OpenAI API → 模型：这里有工具，你看要不要用
# 模型 → OpenAI API：我要调 web_search，参数是 {...}
# OpenAI API → 我的代码：tool_calls = [{name: "web_search", args: {...}}]

# 我的代码执行工具，拿到结果
result = await web_search.execute(**args)

# 我的代码 → OpenAI API：这是结果
messages.append({"role": "tool", "content": result})

# OpenAI API → 模型：结果在这，你继续
# 模型 → OpenAI API：最终答案
```

**MCP 发生在你的应用侧。** 它不碰模型，只管理工具怎么注册、怎么发现、怎么调用。核心是一个 Server-Client 架构：

```
MCP Server（独立进程）
  → 暴露 list_tools() / call_tool() 接口

MCP Client（在你的代码里）
  → 自动连 Server → 拉工具列表 → 生成 tools 参数
  → 拿到 tool_calls 后自动调 Server 执行
```

用 MCP 的好处是：你不需要手写 `get_definition()` 和 `if name == "xxx"` 的分支逻辑。

#### 为什么不直接用 MCP？

我项目的目录叫 `mcp_server/`，但实际没走 MCP 协议。因为我只有三个工具，都在同一个项目里，Function Calling 直接手写够用了。MCP 的好处在于多服务、热插拔、跨语言，等真需要这些的时候再上不迟。

而且两者不冲突——MCP Client 自动生成 tools 参数，Function Calling 让模型决定调不调，可以一起用。

#### 一句话总结

| 概念 | 管的是 |
|------|--------|
| **Function Calling** | 模型怎么告诉你"我要调工具"——API 层 |
| **MCP** | 你的代码怎么知道"有哪些工具可以调"——应用层 |

---

### 追问预演

#### Q4：MCP 能替代 Function Calling 吗？
> 不能。MCP 管工具发现和管理，最终还是得靠 Function Calling 让模型决定调不调工具。它们是不同层的，可以一起用。

#### Q5：MCP 解决了什么实际问题？
> 解决的是"工具多了怎么办"的问题。如果你的 Agent 只有 3 个工具，手写 `get_definition()` 很轻松。但如果有 30 个工具、来自不同的服务、需要动态增减，手写就炸了。MCP 的 Server-Client 架构让工具管理和模型调用解耦。

#### Q6：如果现在让你把 MCPilot 切到真正的 MCP，怎么改？
> 两步：1) 把 `mcp_server/tools/` 包成一个真正的 MCP Server 进程，走 JSON-RPC over stdio；2) 在 `core.py` 里接入 MCP Client SDK，用它代替手写的 `_build_tool_definitions()` 和 `_execute_tool()`。核心的 ReAct 循环不用动，换的是工具注册和执行那两层。

---

*整理时间：2026-07-02*
