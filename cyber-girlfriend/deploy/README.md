# Cyber Companion 生产部署

本目录只使用当前仓库构建的自定义镜像，不依赖上游 `server_latest` 或 `web_latest`。Persona Source/Version 以 MySQL 为唯一真源，`persona-artifacts` 保存导入 ZIP；Server 本地缓存不是数据真源。

## 首次部署

1. 复制 `.env.example` 为 `.env`，设置强 MySQL 密码和当前 Git commit。
2. 创建 `runtime/server`，把 `server.config.example.yaml` 复制为 `runtime/server/.config.yaml`。
3. 先执行 `docker compose --env-file .env -f docker-compose.production.yml up -d mysql redis manager`。
4. 登录智控台设置 `server.secret`，再把同一值写入 `runtime/server/.config.yaml` 的 `manager-api.secret`。
5. 执行 `docker compose --env-file .env -f docker-compose.production.yml up -d --build`。
6. 在人物库导入、测试并发布 Persona；不要把 Persona 原始制品或 Secret 提交到 Git。

## 健康与告警

- `GET /xiaozhi/persona/health`：数据库、Compiler 与 Companion 指标快照（需登录）。
- 告警建议：Compiler 或 Resolve 五分钟错误率超过 5%；Import Job 15 分钟无进展；CAS 冲突率超过 2%；连续三次画廊同步失败。
- 日志中只记录 job/agent/persona/version/hash 前缀和错误码，不记录原始对话、记忆、ZIP 或 Secret。

## 升级和回滚

1. 升级前备份 MySQL 与 `persona-artifacts` 卷，并记录当前镜像 commit。
2. 使用新 commit 构建并启动；Liquibase 迁移仅新增兼容字段和表。
3. 完成人物 Resolve、普通对话、记忆和导入冒烟测试。
4. 若新版本异常，把 `.env` 的 `GIT_COMMIT` 改回旧值并重新 `up -d`。不得回滚 MySQL 数据卷；State/Memory 与 Persona 数据会保留。
5. 紧急情况下可把 `companion.persona_registry_backend` 改为 `filesystem`，State/Memory 仍保留在 manager-api；若需完全停用则把 `companion.enabled` 设为 `false`，基础语音聊天仍可工作。

## 本地 Registry 迁移

```bash
cd main/xiaozhi-server
python -m core.companion.importers.dot_skill \
  --registry data/companion/personas \
  migrate-filesystem-to-manager-api \
  --manager-url http://127.0.0.1:8002/xiaozhi \
  --token '<智控台 Bearer Token>' \
  --dry-run
```

确认报告后移除 `--dry-run`。迁移不会删除本地文件，重复执行相同 Hash 的版本是幂等操作。
