import json
import os

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_URL = "http://localhost:8000"
_API_KEY = os.getenv("API_SECRET_KEY", "")

st.set_page_config(page_title="MCPilot", page_icon="", layout="wide")


# ── 工具函数 ──────────────────────────────────────────────

def _headers() -> dict:
    if _API_KEY:
        return {"Authorization": f"Bearer {_API_KEY}"}
    return {}


def api_get(path: str) -> dict | None:
    try:
        r = httpx.get(f"{API_URL}{path}", headers=_headers(), timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"请求失败: {e}")
        return None


def api_post(path: str, data: dict) -> dict | None:
    try:
        r = httpx.post(f"{API_URL}{path}", json=data, headers=_headers(), timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"请求失败: {e}")
        return None


def api_delete(path: str) -> dict | None:
    try:
        r = httpx.delete(f"{API_URL}{path}", headers=_headers(), timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"请求失败: {e}")
        return None


def load_session(session_id: str) -> None:
    """从后端加载会话内容并写入 session_state。"""
    data = api_get(f"/sessions/{session_id}")
    if data is None:
        return
    st.session_state.session_id = session_id
    st.session_state.messages = [
        {"role": m["role"], "content": m["content"]}
        for m in data.get("messages", [])
        if m["role"] in ("user", "assistant")
    ]


def create_new_session() -> None:
    data = api_post("/sessions", {"title": "新对话"})
    if data:
        st.session_state.session_id = data["id"]
        st.session_state.messages = []


# ── 初始化 session_state ──────────────────────────────────

if "session_id" not in st.session_state:
    st.session_state.session_id = None

if "messages" not in st.session_state:
    st.session_state.messages = []

if "sessions_list" not in st.session_state:
    st.session_state.sessions_list = []

# 首次加载：获取会话列表，自动恢复或新建
if st.session_state.session_id is None:
    data = api_get("/sessions")
    if data and data.get("sessions"):
        sessions = data["sessions"]
        st.session_state.sessions_list = sessions
        load_session(sessions[0]["id"])
    else:
        create_new_session()


# ── 侧边栏：会话管理 ──────────────────────────────────────

with st.sidebar:
    st.title("MCPilot")

    if st.button("+ 新建会话", use_container_width=True):
        create_new_session()
        st.rerun()

    st.divider()
    st.caption("最近会话")

    data = api_get("/sessions")
    sessions = data.get("sessions", []) if data else []
    st.session_state.sessions_list = sessions

    for s in sessions:
        is_current = s["id"] == st.session_state.session_id
        label = ("▶ " if is_current else "") + s["title"]
        if st.button(label, key=f"sess_{s['id']}", use_container_width=True):
            if not is_current:
                load_session(s["id"])
                st.rerun()

    st.divider()

    if st.session_state.session_id and st.button(
        "删除当前会话", use_container_width=True, type="secondary"
    ):
        api_delete(f"/sessions/{st.session_state.session_id}")
        data = api_get("/sessions")
        remaining = data.get("sessions", []) if data else []
        if remaining:
            load_session(remaining[0]["id"])
        else:
            create_new_session()
        st.rerun()


# ── 主区域：对话 ──────────────────────────────────────────

st.title("MCPilot - 智能助手")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("说点什么..."):
    if st.session_state.session_id is None:
        create_new_session()

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        answer = ""
        error_msg = ""

        try:
            with httpx.stream(
                "POST",
                f"{API_URL}/chat/stream",
                json={
                    "message": prompt,
                    "session_id": st.session_state.session_id,
                },
                headers=_headers(),
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
                                returned_sid = data.get("session_id")
                                if returned_sid:
                                    st.session_state.session_id = returned_sid

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
