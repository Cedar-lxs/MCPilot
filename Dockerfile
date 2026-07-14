# MCPilot — 多阶段构建
#   docker build -t mcpilot .
#   docker run -p 8000:8000 --env-file .env mcpilot

# ── 构建阶段 ──────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ── 运行阶段 ──────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# 从构建阶段复制已安装的依赖
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# 复制项目文件
COPY src/ ./src/
COPY ui/ ./ui/
COPY scripts/ ./scripts/
COPY docs/ ./docs/
COPY .env.example ./

# 确保日志和向量库目录存在（运行时挂载卷覆盖）
RUN mkdir -p logs chroma_data

EXPOSE 8000 8501

# 默认启动 API 服务
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
