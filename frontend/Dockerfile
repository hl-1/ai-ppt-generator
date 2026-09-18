# 构建上下文必须是仓库根目录（见 docker-compose.prod.yml 的 context: .）
FROM node:22-alpine AS build

WORKDIR /src

# 先装依赖，利用缓存
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci

# shared/ 必须与 frontend/ 保持同级：design.ts 里 import.meta.glob('../../../shared/...')
COPY shared ./shared
COPY frontend ./frontend

RUN cd frontend && npm run build

FROM nginx:alpine

COPY --from=build /src/frontend/dist /usr/share/nginx/html
COPY nginx.prod.conf /etc/nginx/conf.d/default.conf