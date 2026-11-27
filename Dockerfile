# 个人记账与消费分析 AI 助手 · 运行镜像（含前端构建产物）
# 构建：docker build -t gduf-ai-assistant .
# 运行：docker run -p 8000:8000 --env-file .env -v ./data:/app/data gduf-ai-assistant
#
# 阶段 1：构建前端（产物 /web/dist，最终复制到 /app/frontend/dist 由 FastAPI 托管）
FROM node:20-alpine AS frontend-build
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 阶段 2：运行镜像
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# tzdata 让容器内的 Asia/Shanghai 生效（Agent 的"今天/昨天"依赖它）
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

# 先装依赖，利用层缓存：只改代码时不会重新装包
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY scripts /app/scripts

# 前端静态产物：backend/app/main.py 会在该目录存在时挂载到 /
COPY --from=frontend-build /web/dist /app/frontend/dist

# 工作目录设为 backend，使 `uvicorn app.main:app` 能找到包；
# 仓库根目录是 /app，因此 DB_PATH=data/app.db 会落在 /app/data（由 compose 挂载持久化）
WORKDIR /app/backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
