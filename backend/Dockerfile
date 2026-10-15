FROM node:22-bookworm-slim AS diagrams
WORKDIR /diagrams
COPY diagram_engine/package*.json ./
RUN npm ci --omit=dev --no-audit --no-fund

FROM python:3.12-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

# 腾讯云 CVM 走腾讯云 PyPI 镜像更稳，也避免构建时拉 ghcr.io 的 uv 镜像。
RUN pip install --no-cache-dir -i https://mirrors.cloud.tencent.com/pypi/simple/ uv==0.12.13

COPY pyproject.toml uv.lock ./
# Keep locked versions and hashes, but resolve package files through the mirror.
RUN uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file /tmp/requirements.lock \
    && uv venv /app/.venv \
    && uv pip sync --python /app/.venv/bin/python --require-hashes \
        --default-index https://mirrors.cloud.tencent.com/pypi/simple/ /tmp/requirements.lock

COPY . .
COPY --from=diagrams /usr/local/bin/node /usr/local/bin/node
COPY --from=diagrams /diagrams/node_modules /app/diagram_engine/node_modules
RUN uv pip install --python /app/.venv/bin/python --no-deps --editable . \
    --default-index https://mirrors.cloud.tencent.com/pypi/simple/
# 字体下载失败就直接构建失败；直接调用 venv 避免 uv run 再同步 dev 依赖。
RUN /app/.venv/bin/python scripts/fetch_fonts.py

EXPOSE 39800
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "39800"]
