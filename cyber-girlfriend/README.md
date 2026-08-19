# Companion Core 使用说明

本目录用于保存“赛博女友 / Companion Core”改造文档和运行说明，不放入项目原有 `docs/`。

文档入口：

- [CyberGirlfriend 最终成品实施方案](./cyber-girlfriend-final-product-plan.md)：已实现的最终产品基线、验证记录与现场部署验收清单；
- [Companion Core 改造方案](./companion-core-implementation-plan.md)：已实现的底层技术基线。

P0-P4 已完成代码实现。生产部署、升级和回滚见 [部署手册](./deploy/README.md)。

## 1. 导入 dot-skill Persona

在 `main/xiaozhi-server` 目录运行：

```bash
python -m core.companion.importers.dot_skill inspect \
  --source /path/to/dot-skill/skills/colleague/example_zhangsan

python -m core.companion.importers.dot_skill import \
  --source /path/to/dot-skill/skills/colleague/example_zhangsan \
  --registry data/companion/personas \
  --version v1

python -m core.companion.importers.dot_skill publish \
  --registry data/companion/personas \
  --persona-id persona.colleague.example_zhangsan \
  --version v1
```

导入器兼容 dot-skill schema 1/2/3，以及旧版只有 `meta.json + persona.md + work.md` 的目录。它只读取人物元数据和 Markdown，不执行来源中的脚本、工具或安装指令。

公众人物会自动归类为 `celebrity`，关系阶段固定不超过 `friend`。

## 2. 智控台导入并绑定智能体

运行 Liquibase 更新后，普通用户不需要使用上述 CLI：

1. 从顶部菜单进入“Persona 人物库”；
2. 从在线画廊导入，或使用 GitHub URL/ZIP；
3. 系统自动检查来源并编译测试；
4. 查看 PersonaSpec、Runtime Prompt、warning 和测试报告后发布；
5. 点击“发布并绑定”，或在“角色配置 → 陪伴核心”使用 Persona/版本下拉选择；
6. Overlay 使用表单编辑，高级用户才需要查看 JSON 预览。

Overlay 示例：

```json
{
  "ai_identity_notice": "这是 AI 陪伴角色，不代表相关真人本人。",
  "user_address": "阿明",
  "initial_stage": "familiar",
  "allowed_stages": ["familiar", "friend", "ambiguous", "lover"],
  "intimacy_boundaries": ["不以冷暴力逼迫用户", "不声称现实中的真人承诺"],
  "memory_rules": ["只引用真实保存的共同经历"],
  "proactive_enabled": true,
  "proactive_interval_minutes": 180,
  "proactive_behavior_rules": ["只在设备在线且用户空闲时简短问候"],
  "voice_reply_style": "适合语音播放，通常 2 到 4 句",
  "tool_rephrase_style": "保留事实和数值，用角色自己的短句表达",
  "tool_ack_prefix": "行吧"
}
```

Overlay 采用白名单解析，不能设置 `trust`、`affection`、关系分数或其他运行状态。

## 3. 单体模式配置

不使用 manager-api 时，在 `main/xiaozhi-server/config.yaml` 中配置：

```yaml
companion:
  enabled: true
  persona_id: persona.colleague.example_zhangsan
  persona_version: v1
  user_id: local-user
  agent_id: local-agent
  persona_registry: data/companion/personas
  database_path: data/companion/companion.db
  context_timeout_ms: 500
```

默认开关为关闭。Persona 加载、上下文构建或状态提交失败时会 fail-open，基础语音聊天仍继续工作。

`repository: auto` 在 manager-api 部署下通过受 `server.secret` 保护的接口把状态、事件和记忆写入 MySQL；单体部署使用 SQLite。两种模式都以 `owner_user_id + agent_id + persona_id` 为关系主键，因此同一用户绑定到同一智能体的多个设备会共享同一人物的状态，而不同人物不会串关系或记忆。

管理端只显示关系阶段、有效轮次和记忆数量，不显示内部信任/好感分数。重置操作需要确认，并会写入 `ai_companion_audit` 审计表。

## 4. 版本管理

```bash
python -m core.companion.importers.dot_skill list --registry data/companion/personas
python -m core.companion.importers.dot_skill diff --registry data/companion/personas \
  --persona-id PERSONA_ID --from v1 --to v2
python -m core.companion.importers.dot_skill rollback --registry data/companion/personas \
  --persona-id PERSONA_ID --version v1
python -m core.companion.importers.dot_skill archive --registry data/companion/personas \
  --persona-id PERSONA_ID --version v2
```

更新或回滚同一 Persona 的版本不会清空 `user_id + agent_id + persona_id` 对应的关系状态和记忆；切换到另一个 Persona 时使用独立状态，切回后恢复原人物状态。

## 5. 验证

```bash
cd main/xiaozhi-server
python -m unittest discover -s tests -p 'test_*.py' -v

cd ../manager-web
npm run check:i18n
npm run test:unit
npm run build
```

运行数据默认位于 `main/xiaozhi-server/data/companion/`，不应提交到源码仓库。

## 6. 声音克隆

声音克隆沿用项目原有流程：在“声音克隆”上传样本并完成训练，然后在角色配置中选择训练成功的音色。
Persona 只负责人物性格、关系和记忆，不额外维护声音绑定表。
