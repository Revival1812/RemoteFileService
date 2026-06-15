FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 🌟 修改点 1：替换系统软件源为阿里云，加速 apt-get，并补全截断的清理命令
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources || \
    sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list && \
    apt-get update && apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./

# 🌟 修改点 2：为 pip 增加国内镜像源，加速 Python 依赖包下载
RUN pip install --upgrade pip -i https://mirrors.aliyun.com/pypi/simple/ && \
    pip wheel --wheel-dir /wheels ".[dev]" -i https://mirrors.aliyun.com/pypi/simple/

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/appuser/.local/bin:${PATH}"

WORKDIR /app
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

COPY --from=builder /wheels /wheels

# 🌟 修改点 3：同样为 runtime 阶段的 pip 安装加上国内镜像源
RUN pip install --no-cache-dir /wheels/* -i https://mirrors.aliyun.com/pypi/simple/ && \
    rm -rf /wheels

COPY . .
RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

# 🌟 补全点 1：修复被截断的健康检查命令
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()"

# 🌟 补全点 2：修复被截断的 Uvicorn 启动命令
CMD ["sh", "-c", "python -m app.cli.wait_for_db && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
