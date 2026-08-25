# Companion Core 使用说明

本目录用于保存“赛博女友 / Companion Core”改造文档和运行说明，不放入项目原有 `docs/`。

文档入口：

- [CyberGirlfriend 最终成品实施方案](./cyber-girlfriend-final-product-plan.md)：已实现的最终产品基线、验证记录与现场部署验收清单；
- [Companion Core 活人感下一阶段开发方案](./living-presence-next-development-plan.md)：P7-P13 的输入感知、统一表达、关系、主动关心、TTS 校准与评测路线；
- [Companion Core 改造方案](./companion-core-implementation-plan.md)：已实现的底层技术基线。

P0-P8 已完成代码实现，其中 P7-P8 待集成/实机验收。生产部署、升级和回滚见 [部署手册](./deploy/README.md)。

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

人物库卡片和“管理版本”窗口均可使用“导入新版”。GitHub 来源可以直接重新拉取，ZIP 来源可上传新版制品；升级任务会在写库前校验目标 Persona ID，生成草稿并重新经过编译、校验和测试，不会直接覆盖当前发布版。发布新版后，未固定版本的智能体自动跟随，固定版本的智能体保持原版本。

历史版本由旧编译器生成、但源码内容没有变化时，在“管理版本”点击“重新解析”。系统优先使用该版本保存的源码 ZIP；缺少快照时使用当时的 GitHub commit，仍不可用时可上传与旧版本源码哈希一致的 ZIP。重新解析不会覆盖旧版本：结果变化时创建 `-r2`、`-r3` 等修订草稿，结果一致时不创建重复版本。只有表达 ID 和输出原文都不变的招牌录音可以选择性继承，手工规则覆盖不会继承。

“招牌表达/招牌语音”是完全可选能力，不是 Persona 发布门槛。只有原 Skill 明确给出招牌或标志性表达证据时才自动解析；没有招牌表达的人物可直接导入、测试和发布。Skill 解析出的规则默认只读，可按版本单条禁用；只有明确点击“自定义覆盖规则”才创建手工覆盖。固定录音也可不上传，缺失时回退人物当前 TTS；若上传，主录音建议只录模型输出的招牌原文，例如 `Ciallo～(∠・ω< )⌒★`，对话前摇由模型按语境动态生成，活泼和轻柔录音为可选变体。

开发期编译算法升级后，重复导入同一份源码会比较当前编译结果：输出变化时自动生成 `-r2`、`-r3` 修订草稿，输出不变时复用已有结果。`inspect` 与 `compile` 使用同一份规范化源码哈希，因此不会再把 ZIP 时间戳差异误判为源码变化。开发模式人物详情还提供“彻底清除人物”，会永久删除人物版本、导入/审计记录、招牌资产、关系与记忆并解除绑定；该功能默认仅在 `application-dev.yml` 开启，非开发环境需显式设置 `COMPANION_PERSONA_DEV_TOOLS_ENABLED=true`。

公开 GitHub 仓库升级会优先通过 REST API 解析精确 commit；API 限流时自动回退到 Git smart-HTTP refs，不需要人工等待额度恢复。生产环境仍建议给 `manager-api` 配置可选环境变量 `PERSONA_GITHUB_TOKEN`，以获得更高额度；令牌只放环境变量，不写入数据库或前端。

“删除人物”是可恢复移除：仍有智能体绑定时会拒绝删除并提示占用；解除全部绑定后，人物从人物库和可绑定列表隐藏，但版本、审计、关系和记忆保留。重新导入同一 Persona 可恢复人物。当前不提供会级联清理历史数据的永久物理删除。

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
