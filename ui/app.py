import streamlit as st
import httpx

API_URL = "http://localhost:8000"

st.set_page_config(page_title="MCPilot", page_icon="🤖")
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

    # 调用后端 API 获取回答
    with st.chat_message("assistant"):
        with st.spinner("MCPilot 正在思考..."):
            try:
                response = httpx.post(f"{API_URL}/chat", json={
                    "message": prompt,
                    "history": st.session_state.history
                }, timeout=180)
                response.raise_for_status()
                data = response.json()
                answer = data["answer"]
                st.session_state.history = data["history"]
            except httpx.HTTPStatusError as e:
                detail = e.response.text
                try:
                    detail = e.response.json().get("detail", detail)
                except Exception:
                    pass
                answer = f"API 错误 ({e.response.status_code}): {detail}"
            except Exception as e:
                answer = f"出错了: {e}"

        st.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})
    
    