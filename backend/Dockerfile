FROM python:3.12-slim

WORKDIR /app

# 腾讯云 CVM 走腾讯云 PyPI 镜像更稳，也避免构建时拉 ghcr.io 的 uv 镜像。
RUN pip install --no-cache-dir -i https://mirrors.cloud.tencent.com/pypi/simple/ uv==0.12.13

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --index-url https://mirrors.cloud.tencent.com/pypi/simple/

COPY . .
# 字体下载失败就直接构建失败；直接调用 venv 避免 uv run 再同步 dev 依赖。
RUN /app/.venv/bin/python scripts/fetch_fonts.py

EXPOSE 39800
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "39800"]
