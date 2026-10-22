# 生产配置

本目录集中存放生产 Compose、Nginx、镜像构建文件和环境变量模板。
配置含义与完整操作见 [部署说明](../docs/deployment.md)。

在仓库根执行：

```bash
make prod-config
docker compose --env-file deploy/.env.production -f deploy/docker-compose.prod.yml up -d --build
```

首次部署从 `.env.production.example` 复制出 `.env.production` 并填写配置，证书放入
`certs/`。实际环境文件、证书和私钥均由 Git 忽略。
