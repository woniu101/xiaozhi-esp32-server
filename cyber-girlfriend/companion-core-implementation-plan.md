# CyberGirlfriend Companion Core 技术基线

> 状态：Implemented Baseline v3.1
> 更新日期：2026-08-19
> 用途：指导 Companion Core 后续调试、重构和扩展。产品范围以 `cyber-girlfriend-final-product-plan.md` 为准。

## 1. 设计目标

Companion Core 负责把“通用语音助手”变成具有稳定人物性格、动态情绪、关系发展和长期记忆的陪伴角色。
它必须保持对现有 xiaozhi-server 的低侵入和 fail-open：任何 Companion 子模块故障都不能阻断基础对话。

核心原则：

1. dot-skill 是导入格式，不是运行时插件；
2. 所有来源统一编译为 Canonical PersonaSpec；
3. Persona、Agent Overlay、User-Agent-Persona Runtime State 分层；
4. 每轮上下文临时注入，不污染原始提示词；
5. 状态提交幂等并使用 revision 处理并发；
6. 真实用户数据按 `user_id + agent_id + persona_id` 隔离，Persona 的不同版本共享状态；
7. 内部状态数值不直接展示给终端用户。

## 2. 代码布局

```text
main/xiaozhi-server/core/companion/
├── importers/
│   ├── base.py
│   ├── safe_source.py
│   ├── dot_skill.py
│   ├── manual_yaml.py
│   ├── validator.py
│   └── compiler.py
├── persona/
│   ├── registry.py
│   ├── manager_api_registry.py
│   ├── evaluator.py
│   └── judge.py
├── emotion/engine.py
├── relationship/engine.py
├── repositories/
│   ├── base.py
│   ├── local_sqlite.py
│   ├── manager_api.py
│   └── memory_ranking.py
├── context_builder.py
├── event_extractor.py
├── example_selector.py
├── manager.py
├── models.py
├── overlay.py
├── presentation.py
├── privacy.py
├── response_planner.py
├── runtime.py
├── semantic_text.py
├── session.py
├── state_models.py
├── state_reducer.py
└── turn_recorder.py
```

manager-api 对应模块：

```text
main/manager-api/src/main/java/xiaozhi/modules/persona/
├── client/PersonaCompilerClient.java
├── controller/
├── dao/
├── dto/
├── metrics/
├── service/
└── source/GitHubSourceDownloader.java
```

## 3. Persona 导入

### 3.1 Adapter 输入

`DotSkillAdapter` 支持：

- dot-skill schema 1/2/3；
- `manifest.json + meta.json + persona.md`；
- legacy `meta.json + persona.md + work.md`；
- 本地目录和 ZIP；
- colleague、relationship、celebrity 三种 family。

`ManualYamlAdapter` 用于本地开发和回归夹具。

### 3.2 安全读取

来源处理必须满足：

- 不执行 Skill 内任何代码；
- 拒绝路径穿越、绝对路径和符号链接；
- 限制 ZIP 总大小、文件数量、单文件大小和压缩比；
- GitHub 仅接受 HTTPS 仓库 URL；
- 下载固定 commit 快照；
- 对最终制品计算 SHA-256。

### 3.3 标准化

Adapter 提取：

- identity / public role；
- core relational rules；
- expression DNA；
- emotional logic；
- conflict and repair；
- mental models / decision heuristics；
- examples / limitations；
- relationship policy；
- upstream ID、版本、URL、commit 和 artifact hash。

公众人物 family 自动归一化为 `celebrity`，允许关系阶段固定为 familiar/friend。

### 3.4 编译和测试

`PersonaCompiler` 将 PersonaSpec 编译为带结构标签的 Runtime Prompt。编译顺序保持确定性，方便 hash、Diff 和测试。

发布前执行：

- JSON Schema；
- 字段长度和数量限制；
- Prompt Injection 扫描；
- 核心规则/表达 DNA 完整性 warning；
- Persona Evaluator 场景测试；
- 可选 Judge LLM。

Judge 不可用时记录 `unavailable/skipped`，不破坏确定性规则测试。

## 4. Runtime 数据分层

### 4.1 Persona

发布版本中的静态内容，只能通过版本生命周期修改。运行时按 `persona_id + version/hash` 缓存。

### 4.2 Overlay

Agent 级产品配置，只允许以下类型字段：

- 用户称呼；
- initial/allowed relationship stages；
- intimacy boundaries；
- memory rules；
- proactive behavior rules；
- voice/tool reply style；
- tool acknowledgement prefix；
- additional rules；
- AI identity notice。

`normalize_overlay()` 丢弃未知字段；`effective_overlay()` 取 Persona 策略、公众人物上限和 Agent 配置的交集。

### 4.3 State

User-Agent-Persona 级动态状态：

```text
EmotionState:
  valence, arousal, warmth, irritation, fatigue, updated_at

RelationshipState:
  stage, trust, affection, intimacy, conflict,
  meaningful_turns, shared_event_count, updated_at
```

所有浮点值进入存储前都限制在 `[0, 1]`。关系阶段只能通过阈值和有效事件迁移，不允许 Overlay 直接写分数。

## 5. 每轮调用协议

### 5.1 before_turn

```text
CompanionManager.before_turn(connection, user_text)
  -> resolve active Persona
  -> decay committed user-agent state
  -> extract current-turn signals
  -> preview emotion/relationship without incrementing revision
  -> retrieve ranked memories with recent-item exclusion
  -> build ResponsePlan and select situational examples
  -> build CompanionTurnContext
  -> return ephemeral system context
```

上下文预算按 Persona、状态、记忆和当前轮分配。记忆不足时不伪造；超预算时优先保留核心规则和高相关记忆。
预览状态只供当前回复和 TTS 表现使用，不直接写入 Repository。主动消息使用 `track_turn=false`，
不会留下待提交事件、记忆或预览状态。

### 5.2 LLM 注入

`Dialogue.get_llm_dialogue_with_memory()` 接受可选 CompanionTurnContext，仅构造本次请求副本。原始 dialogue 和角色系统提示不写入动态状态。

### 5.3 after_turn

```text
CompanionManager.after_turn(connection, user_text, assistant_text)
  -> rule/structured Memory Extractor
  -> merge and deduplicate pre-turn/post-turn events
  -> EmotionEngine + RelationshipEngine exactly once
  -> memory and commitment candidates
  -> TurnRecorder.commit(turn_id, expected_revision)
```

同一 `turn_id` 重复提交必须幂等。revision 不匹配时重新读取状态并按仓储策略重试，不能静默覆盖其他设备提交。

## 6. 情绪和关系

### 6.1 Emotion Engine

情绪由结构化事件驱动，并按时间衰减：

- 用户关心/认真回应：warmth、valence 上升；
- 敷衍/攻击：irritation、conflict 上升；
- 长时间无交互：arousal、irritation 向基线回落；
- 高频长对话：fatigue 可上升。

情绪只影响表达，不改变事实、安全规则或工具结果。

### 6.2 Relationship Engine

阶段建议：

```text
stranger -> familiar -> friend -> ambiguous -> lover -> intimate
```

每次迁移需要同时满足分数阈值、有效轮次和共同事件数量。负面事件可以增加 conflict 或降低 warmth；
长时间无交互会让亲密度缓慢冷却，达到降级条件时逐级降级，道歉与后续正向互动可降低 conflict 并修复关系。

公众人物 Persona 的有效阶段集合始终不超过 familiar/friend。

## 7. 记忆

记忆类型：

- semantic：用户事实与稳定偏好；
- episodic：有时间和上下文的事件；
- shared：双方共同完成的事情；
- relationship：影响关系的事件。
- commitment：用户计划、提醒请求和角色明确承诺，可由后续完成/取消结果替换。

写入前执行：

- 文本长度限制；
- 敏感信息过滤；
- Prompt Injection 检测；
- normalized hash 去重；
- importance/confidence 阈值；
- source turn 追踪。

生命周期规则：

- `memory_rules` 在提取阶段生效，可限制主题或只保留指定类型；
- 规则提取为低延迟基线；默认 `hybrid` 模式使用主模型严格 JSON 补充结构化候选，失败时自动保留规则结果；
- semantic 记忆使用 `subject_key` 合并，同一主题的新事实把旧事实标记为 `superseded`；
- episodic 默认带过期时间，过期或 superseded 记忆不进入运行时上下文；
- 管理端支持按当前 Persona 查看、编辑和删除记忆。

召回排序综合中文词法、概念主题、`subject_key`、importance、confidence 和时间衰减；同一主题在单轮结果中保持多样性，普通对话短期排除刚使用过的记忆，明确询问“还记得吗”时可绕过排除。第一版不依赖向量数据库，后续可在 Repository 后增加 embedding 实现而不修改 Runtime 接口。

### 7.1 Response Planner 与动态示例

每轮在调用 LLM 前生成结构化 ResponsePlan，包括 dialogue act、情绪语气、回复长度、提问策略、主动程度和记忆策略。Planner 当前覆盖安慰、边界、修复、接纳、共同计划、建议、直接回答、行动、轻松互动、回忆、倾听和一般接话。

编译后的完整 Persona 示例会从常驻 Runtime Prompt 中移除，再由 `example_selector.py` 按用户消息、场景标签和 ResponsePlan 选择最多 3 条。最近使用过的示例短期排除；没有正相关示例时不注入示例，避免错场景模仿。

## 8. 工具调用与表现层

工具分两类：

- 即时动作：执行成功后可用 `tool_ack_prefix` 给出短确认；失败和未找到结果不添加成功确认语；
- 信息结果：保持数值和事实不变，只按 `tool_rephrase_style` 重写表达。

`presentation.py` 根据情绪和人物配置产生 TTS style / 表现提示。TTS Provider 声明支持时接收 emotion style；不支持时忽略该参数并继续合成。

## 9. Repository

### 9.1 manager-api

完整部署使用：

- `POST /config/companion/persona/resolve`；
- `POST /config/companion/state`；
- `POST /config/companion/memories/search`；
- `POST /config/companion/commit`。

请求沿用 server secret，并由 manager-api 校验智能体、Persona 和用户数据范围。

### 9.2 SQLite

单体部署使用 `local_sqlite.py`，表结构和幂等语义与 manager-api 保持一致。它是开发/离线后端，不作为完整部署的数据真源。

## 10. 缓存和降级

建议缓存：

- Persona：key=`persona_id:version:artifact_hash`；
- Runtime Resolve：短 TTL，允许 stale-if-error；
- State：仅 Session 内短缓存，提交后必须更新 revision；
- Memory query：仅单轮复用，不跨用户共享。

降级规则：

- Persona 不可用：跳过 Companion Context；
- State 不可用：使用初始状态但不伪造旧记忆；
- Commit 失败：记录指标，不重放整次 LLM 回复；
- Context 超时：直接进入原始对话链；
- 任一异常不得关闭 WebSocket 会话。

## 11. manager-api 管理闭环

Import Worker 自动执行：

```text
resolve -> download -> inspect -> compile -> validate -> persist draft
```

管理生命周期：

- draft：可预览、测试、导出；
- published：可被 Agent Resolve；
- archived：保留审计和 Diff，但不可重新发布；
- rollback：把当前 published pointer 切换到目标已发布版本。

所有 private Persona 操作检查 `owner_user_id`；shared/public 只开放读取和绑定，不开放修改。

## 12. 前端契约

PersonaLibrary 页面只承担：

- 展示 Gallery 和用户人物；
- 创建 URL/ZIP 导入任务；
- 轮询三步进度；
- 展示 Spec/Prompt/Validation/Test/Judge；
- 发布、回滚、归档和 Diff；
- 跳转 Agent 绑定。

角色配置页只提交 Persona ID、可选版本、enabled 和白名单 Overlay。声音音色继续使用原有 TTS/Voice Clone 配置字段。

## 13. 关键数据库约束

- `ai_persona_version(persona_source_id, version)` 唯一；
- artifact hash 用于幂等和追踪；
- `ai_companion_state(user_id, agent_id, persona_id)` 为主键；
- event 对 `turn_id + event_type + payload_hash` 去重；
- memory 对 owner/type/normalized hash 去重；
- turn_id 全局记录防重复提交；
- 发布指针和 Agent 绑定只允许指向可解析的 published 版本。

## 14. 测试门槛

每次修改 Companion Core 至少运行：

```bash
cd main/xiaozhi-server
python -m unittest discover -s tests -p 'test_*.py' -v

cd ../manager-web
npm run check:i18n
npm run test:unit
npm run build
```

manager-api 需执行 Maven 测试；迁移需在空 MySQL 库应用完整 changelog，并对已有 Companion 数据做升级回归。

必须覆盖的故障注入：

- manager-api 超时；
- Compiler 返回无效 JSON；
- ZIP bomb / Zip Slip；
- 同一 turn 重放；
- 多设备 revision 冲突；
- published 版本不存在；
- TTS Provider 不支持 emotion style；
- Companion 总开关关闭。

## 15. 后续扩展顺序

1. 真实对话数据驱动的阈值和 Prompt 调优；
2. Embedding Memory Repository；
3. 头像/Live2D/表情映射；
4. Persona 版本评测集和自动回归看板；
5. 主动消息跨离线设备的消息队列与推送；
6. 多用户共享人物模板但完全隔离 Runtime State。

在线设备的主动消息调度已实现独立开关、最短频率限制和人物规则约束；离线推送仍属于后续扩展。

不应优先做的内容：训练自有大模型、让 dot-skill 在运行时执行、让 Overlay 修改内部状态、把所有历史对话直接塞入 Prompt。

## 16. 验收标准

- 导入同一制品两次结果稳定且可追踪；
- Runtime 只能加载 published 版本；
- Persona v1/v2 切换后用户关系和记忆不丢失；
- 同一 turn 重放不会重复累计状态；
- 多设备并发不会静默覆盖；
- Prompt Injection 内容不能进入 published Runtime Prompt；
- 公众人物 Overlay 无法扩大关系阶段；
- manager-api/Repository/Compiler 超时均能回退基础聊天；
- Voice Clone 训练成功后可由角色配置直接选择并在设备生效。
