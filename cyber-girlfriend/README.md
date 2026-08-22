# Companion Core 使用说明

本目录用于保存“赛博女友 / Companion Core”改造文档和运行说明，不放入项目原有 `docs/`。

文档入口：

- [CyberGirlfriend 最终成品实施方案](./cyber-girlfriend-final-product-plan.md)：已实现的最终产品基线、验证记录与现场部署验收清单；
- [Companion Core 活人感下一阶段开发方案](./living-presence-next-development-plan.md)：P7-P13 的输入感知、统一表达、关系、主动关心、TTS 校准与评测路线；
- [Companion Core 改造方案](./companion-core-implementation-plan.md)：已实现的底层技术基线。

P0-P6 已完成代码实现。生产部署、升级和回滚见 [部署手册](./deploy/README.md)。

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

公众人物会自动归类为 `celebrity`，并强制保留“AI 角色、不代表真人”的身份提示；导入器默认推荐朋友型，但实际关系范围在角色配置中独立选择。

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
  "relationship_mode": "romance",
  "initial_stage": "familiar",
  "allowed_stages": ["familiar", "friend", "ambiguous", "lover"],
  "intimacy_boundaries": ["不以冷暴力逼迫用户", "不声称现实中的真人承诺"],
  "memory_rules": ["只引用真实保存的共同经历"],
  "proactive_enabled": true,
  "proactive_interval_minutes": 180,
  "proactive_daily_limit": 3,
  "proactive_quiet_start": "23:00",
  "proactive_quiet_end": "08:00",
  "proactive_timezone": "Asia/Shanghai",
  "proactive_max_unanswered": 3,
  "proactive_rejection_cooldown_minutes": 1440,
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
  outbox_path: data/companion/commit_outbox.db
  context_timeout_ms: 500
```

默认开关为关闭。Persona 加载、上下文构建或状态提交失败时会 fail-open，基础语音聊天仍继续工作。

`repository: auto` 在 manager-api 部署下通过受 `server.secret` 保护的接口把状态、事件和记忆写入 MySQL；单体部署使用 SQLite。两种模式都以 `owner_user_id + agent_id + persona_id` 为关系主键，因此同一用户绑定到同一智能体的多个设备会共享同一人物的状态，而不同人物不会串关系或记忆。

manager-api 短暂不可用时，结构化状态提交会写入本地 `outbox_path` 并在后台重放；该文件可能包含记忆候选，
应放在持久卷中并保持仅服务账号可读。`/internal/companion/health` 可查看积压数量和最老积压时长。

管理端只显示关系阶段、有效轮次和记忆数量，不显示内部信任/好感分数。重置操作需要确认，并会写入 `ai_companion_audit` 审计表。
“仅重置关系”会保留当前 Persona 的人物记忆；“完整重置”才会清除关系、事件和记忆。最近一轮诊断只保存回应计划、事件、记忆 ID、状态和耗时，不保存原始对话。

可选混合向量召回默认关闭。需要时在 `companion.memory_embedding` 配置 OpenAI-compatible `/embeddings` 服务；服务失败会自动回退词法/概念召回。

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
