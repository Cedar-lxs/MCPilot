import json

import httpx
import streamlit as st

API_URL = "http://localhost:8000"

st.set_page_config(page_title="MCPilot", page_icon="")
st.title("MCPilot - 智能助手")


# 初始化历史聊天记录
if "history" not in st.session_state:
    st.session_state.history = None

if "messages" not in st.session_state:
    st.session_state.messages = []

# 显示已有聊天记录
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 显示聊条记录
if prompt := st.chat_input("说点什么..."):
    # 显示用户消息
    st.session_state.messages.append({"role": "user", "content": prompt})   
    with st.chat_message("user"):
        st.markdown(prompt)

    # 调用后端流式接口获取回答
    with st.chat_message("assistant"):
        answer = ""
        error_msg = ""

        try:
            with httpx.stream(
                "POST",
                f"{API_URL}/chat/stream",
                json={"message": prompt, "history": st.session_state.history},
                timeout=180,
            ) as resp:
                resp.raise_for_status()

                buf = [""]
                spinner = st.empty()
                spinner.markdown("⏳ MCPilot 正在思考...")

                def token_generator():
                    first = True
                    for chunk in resp.iter_text():
                        buf[0] += chunk
                        while "\n\n" in buf[0]:
                            event_str, buf[0] = buf[0].split("\n\n", 1)
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
                                token = data.get("token", "")
                                if token and first:
                                    spinner.empty()
                                    first = False
                                yield token
                            elif event_name == "done":
                                if data.get("history"):
                                    st.session_state.history = data["history"]

                answer = st.write_stream(token_generator())

        except httpx.HTTPStatusError as e:
            detail = e.response.text
            try:
                detail = e.response.json().get("detail", detail)
            except Exception:
                pass
            error_msg = f"API 错误 ({e.response.status_code}): {detail}"
        except Exception as e:
            error_msg = f"出错了: {e}"

        if error_msg:
            st.error(error_msg)
            answer = error_msg

        st.session_state.messages.append({"role": "assistant", "content": answer})
    
    