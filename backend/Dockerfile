FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /usr/local/bin/uv   # 固定版本，别用 latest
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .
# 去掉 || true：字体下载失败就直接构建失败，而不是悄悄产出一个度量退化的镜像
RUN uv run python scripts/fetch_fonts.py

EXPOSE 39800
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "39800"]