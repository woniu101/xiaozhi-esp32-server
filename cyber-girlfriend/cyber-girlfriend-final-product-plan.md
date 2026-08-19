# CyberGirlfriend 最终成品实施方案

> 状态：Development Baseline v4.0
> 更新日期：2026-08-19
> 适用仓库：`xiaozhi-esp32-server`
> 目标：在现有小智服务端上形成可导入人物、持续建立关系、保存长期记忆、使用克隆音色的赛博女友产品闭环。

## 1. 最终目标

最终成品不是“换一段系统提示词”，而是一个稳定的人物运行系统：

1. 可以直接复用 colleague-skill / dot-skill 画廊中的人物；
2. 不要求用户执行命令行转换；
3. 人物语言风格、决策习惯、情绪反应和边界在多轮对话中保持一致；
4. 同一用户、同一智能体、同一 Persona 的关系、事件和记忆能够跨会话延续，切换 Persona 不串状态；
5. 人物版本可测试、发布、回滚、归档和绑定；
6. Companion Core 故障时不影响原有基础语音聊天；
7. 第二阶段可直接复用项目原有 Voice Clone 流程完成音色训练和选择。

开发版不增加额外的业务确认表单、状态字段或发布门禁。项目原有账号登录、用户资源隔离、
内部接口 HMAC、SSRF 防护、ZIP 安全检查和 Prompt Injection 检查继续保留。

## 2. 当前结论

本仓库已经完成 P0-P4 主体代码及角色配置四批优化，当前阶段是“集成验证和真实环境验收”：

- `dot-skill -> PersonaSpec -> Runtime Prompt` 转换链已经存在；
- Companion Runtime、情绪、关系、记忆和工具表达链已经接入 `xiaozhi-server`；
- manager-api 已具备人物库、导入任务、版本生命周期、Runtime Resolve 和状态仓储；
- manager-web 已具备人物库、在线画廊、一键导入、版本管理和角色绑定；
- Voice Clone 沿用原模块，训练成功的音色可直接在角色配置中选择；
- 部署文件已固定使用当前仓库构建的自定义镜像。

四批优化已纳入实现基线：

- 三套记忆明确命名为“人物关系与记忆 / 旧版对话记忆 / 本地短记忆摘要”，切换旧版提供器不再删除数据；
- Runtime 隔离键升级为 `user_id + agent_id + persona_id`，Persona 版本升级仍沿用同一状态；
- 模板采用预览和应用范围，默认保留 Persona、Overlay、Runtime State 与声音；
- Companion 使用中性基础系统规则，旧版 intent-llm 在配置页标记为不兼容；
- 角色配置按人物、关系记忆、能力、声音、高级兼容五区展示，并显示保存/重启状态；
- 人物记忆支持查看、编辑、删除、过期、去重和同主题新事实替换旧事实；
- 关系支持冷却、降级和道歉修复，主动关心具备独立开关与频率调度。

仍需在目标环境完成 MySQL 迁移、真实画廊导入、真实模型评审、TTS 供应商和 ESP32 设备验收。

## 3. 产品体验

### 3.1 人物库

顶部导航新增“Persona 人物库”，包含：

- 我的角色：查看草稿/发布状态、关系上限和版本；
- 在线画廊：搜索 colleague-skill Gallery；
- GitHub 导入：输入仓库地址和可选 ref；
- ZIP 导入：上传本地 dot-skill 制品；
- 版本操作：预览、对比、重跑测试、发布、回滚、归档；
- 智能体绑定：选择智能体后跳转角色配置页完成保存。

### 3.2 简化导入流程

用户只需要三步：

```text
获取来源
  -> 自动编译与测试
  -> 预览、发布并绑定
```

导入任务自动完成：

1. 校验 GitHub HTTPS 地址或 ZIP；
2. 下载固定 commit 快照或保存上传制品；
3. 安全解压并识别 dot-skill 结构；
4. 转换为 Canonical PersonaSpec；
5. 编译 Runtime Prompt；
6. 执行规则测试和可选 Judge LLM；
7. 保存为草稿，等待用户发布。

### 3.3 角色配置

角色配置页中的 Companion Core 使用简单表单：

- 开关；
- 已发布 Persona 下拉框；
- 版本下拉框，留空表示始终跟随当前发布版；
- 用户称呼；
- 初始关系阶段；
- 允许发展的关系阶段；
- 亲密边界、记忆规则、主动行为规则；
- 语音回复风格、工具复述风格和即时操作确认语；
- 高级 JSON 预览。

Overlay 只能覆盖白名单字段，不能写入内部 trust、affection、intimacy、conflict 或 emotion 分数。

### 3.4 声音克隆

声音阶段复用现有页面和数据库：

1. 在“声音克隆”中新建音色并上传语音样本；
2. 等待供应商训练完成；
3. 在角色配置的“声音音色”下拉框选择训练成功的音色；
4. 保存并重启设备，使新配置生效。

Persona 与音色是两个独立配置项，不新建 Persona 音色绑定表。

## 4. 总体架构

```text
colleague-skill Gallery / GitHub / ZIP
                    |
                    v
manager-web -> manager-api Import Job
                    |
                    v  HMAC internal API
          xiaozhi-server Persona Compiler
                    |
          PersonaSpec + Runtime Prompt + Test Report
                    |
                    v
       manager-api MySQL Persona Registry
                    |
       Agent -> Persona Version + Overlay
                    |
                    v
xiaozhi-server Companion Runtime
  Persona + State + Memories + Current Turn
                    |
                    v
             LLM -> TTS -> ESP32
```

组件职责：

- manager-web：人物导入、版本管理、绑定和可视化状态；
- manager-api：数据真源、任务编排、用户隔离、生命周期和内部 Runtime API；
- Persona Compiler：无副作用解析、标准化、编译、规则测试和 Judge；
- Companion Runtime：每轮上下文、事件提取、状态更新、记忆和表现层；
- Voice Clone：继续使用原有训练、查询和角色音色选择链路。

## 5. 核心架构决策

### 5.1 dot-skill 只作为输入格式

运行时不直接读取第三方 Skill，也不执行其中脚本。所有来源先经过 Adapter 归一化：

```text
dot-skill schema 1/2/3
legacy meta.json + persona.md
manual Persona YAML
        -> PersonaSpec cyber-persona/v1
```

这样可以复用现有生态，又不把运行稳定性绑定到第三方目录结构。

### 5.2 三层数据必须分离

- Source Persona：相对稳定的人物身份、核心规则、表达 DNA、情绪逻辑和示例；
- Companion Overlay：某个智能体实例的称呼、边界、关系阶段和表达偏好；
- Runtime State：某个用户、智能体与 Persona 组合下的动态情绪、关系、事件和记忆。

更新 Persona 版本不会清空 Runtime State；切换音色也不会修改人物或关系状态。

### 5.3 数据真源

完整部署时：

- Persona Source/Version：MySQL；
- Agent 绑定和 Overlay：MySQL；
- Companion State/Event/Memory：MySQL；
- 导入 ZIP：`persona-artifacts` 持久卷；
- Server 本地缓存：仅加速，不是数据真源。

单体模式保留 Filesystem Persona Registry + SQLite Repository，方便本地开发。

### 5.4 公众人物策略

Adapter 识别 `public-figure` / `celebrity` 后：

- `family` 归一化为 `celebrity`；
- `is_public_figure=true`；
- 关系阶段最多到 `friend`；
- Overlay 不能把关系扩展到 ambiguous/lover/intimate；
- Runtime Prompt 明确这是 AI 角色，不代表真人本人。

这是人物运行策略，不参与导入任务状态流转。

## 6. PersonaSpec v1

Canonical Spec 的核心字段：

```yaml
schema_version: cyber-persona/v1
id: persona.relationship.rabbit
display_name: 小兔
source:
  adapter: dot-skill
  family: relationship
  upstream_id: meta-skill.relationship.rabbit
  upstream_version: v1
  source_url: https://github.com/example/repo
  source_commit: abcdef...
  artifact_sha256: 64-hex
  is_real_person: false
  is_public_figure: false
  is_fictional: true
identity: {}
core_rules: []
expression: {}
emotional_logic: {}
conflict_repair: {}
mental_models: []
decision_heuristics: []
relationship_policy: {}
examples: []
limitations: []
quality: {}
```

必须由可信导入链覆盖 `source_url`、`source_commit` 和 `artifact_sha256`，不能信任制品自报。

## 7. 导入任务状态机

```text
queued
  -> resolving_source
  -> downloading
  -> inspecting
  -> compiling
  -> validating
  -> ready
```

异常状态：

- `validation_failed`：制品已成功解析，但发布测试未通过；
- `failed`：下载、解压、编译或持久化失败；
- `cancelled`：用户取消。

服务重启时，Recovery Task 恢复长时间停留在编译/校验中的任务；重复写入同一 artifact hash 保持幂等。

## 8. API 基线

面向 manager-web：

```text
GET    /persona/gallery
GET    /persona/gallery/{provider}/{externalId}
POST   /persona/gallery/refresh
GET    /persona
GET    /persona/options
GET    /persona/{personaId}
GET    /persona/{personaId}/versions
GET    /persona/{personaId}/versions/{version}
GET    /persona/{personaId}/diff
POST   /persona/import/url
POST   /persona/import/upload
GET    /persona/import/jobs/{jobId}
POST   /persona/import/jobs/{jobId}/cancel
POST   /persona/{personaId}/versions/{version}/publish
POST   /persona/{personaId}/versions/{version}/rollback
POST   /persona/{personaId}/versions/{version}/archive
POST   /persona/{personaId}/versions/{version}/test
GET    /persona/{personaId}/versions/{version}/tests
GET    /persona/{personaId}/versions/{version}/export
GET    /persona/{personaId}/audit
```

Server 内部接口：

```text
POST /config/companion/persona/resolve
POST /config/companion/state
POST /config/companion/commit
POST /config/companion/memories/search
```

Compiler 内部接口由 manager-api 使用 `server.secret` 生成 HMAC 签名，并校验 timestamp、nonce 和 body hash。

## 9. 数据模型

主要表：

- `ai_persona_source`：人物来源、所有者、可见性、人物类型和当前发布版本；
- `ai_persona_version`：Canonical Spec、Runtime Prompt、校验和测试报告；
- `ai_persona_import_job`：异步导入进度、制品和编译结果；
- `ai_persona_test_run`：规则测试/Judge 历史；
- `ai_agent_persona`：智能体绑定、固定版本和 Overlay；
- `ai_companion_state`：情绪与关系当前状态，使用 revision 做 CAS；
- `ai_companion_event`：从对话提取的结构化事件；
- `ai_companion_turn`：轮次幂等记录；
- `ai_companion_memory`：长期记忆；
- `ai_companion_audit`：发布、回滚、归档和重置等管理操作。

关系状态主键是 `user_id + agent_id + persona_id`。同一 Persona 的不同发布版本共享状态；
同一用户绑定到同一智能体的多个设备共享该 Persona 状态；切换到不同 Persona 时使用独立状态。

## 10. Companion Runtime

每轮调用：

```text
before_turn
  -> resolve Persona
  -> load state
  -> retrieve memories
  -> build ephemeral context
  -> inject into LLM input

after_turn
  -> extract events
  -> reduce emotion/relationship
  -> generate memory candidates
  -> commit with turn id + expected revision
  -> update TTS/presentation hints
```

上下文只注入本轮 LLM 请求，不回写原始 system prompt。超时、数据库不可用、Persona 不可解析时 fail-open，
继续原有语音对话并记录降级指标。

## 11. 鲜活人物感的组成

第一版的人物感来自五个可验证组件：

1. 表达 DNA：口头禅、节奏、句长、调侃方式和禁止表达；
2. 情绪状态：valence、arousal、warmth、irritation、fatigue，随事件变化并自然衰减；
3. 关系状态：阶段与 trust/affection/intimacy/conflict 等内部状态；
4. 长期记忆：事实、偏好、共同事件和关系事件，经筛选后进入上下文；
5. 工具人格化：即时操作先短确认，信息工具结果保留事实后再按人物风格复述。

内部数值不直接展示给用户；管理端只显示关系阶段、有效轮次和记忆数量。

## 12. 安全与稳定性

必须持续保留：

- GitHub URL 仅允许 HTTPS 和受控 host；
- 禁止跳转到私网、回环和 link-local 地址；
- ZIP 限制体积、文件数、单文件大小、总解压大小和压缩比；
- 防 Zip Slip、符号链接和路径穿越；
- 不执行第三方脚本、工具声明或安装命令；
- Canonical Spec 和 Runtime Prompt 执行 Prompt Injection 扫描；
- 用户只能访问自己的 private Persona 和允许共享的 Persona；
- 内部 API 保持 HMAC、nonce 防重放和时间窗检查；
- 日志不记录原始对话、完整记忆、ZIP 内容和 Secret。

## 13. 配置与降级

Server 关键配置：

```yaml
companion:
  enabled: true
  persona_registry_backend: manager-api
  repository: auto
  context_timeout_ms: 500
```

降级顺序：

1. Judge LLM 不可用：保留规则测试结果；
2. Persona Resolve 不可用：使用短时缓存；
3. State/Memory 不可用：使用无状态 Persona；
4. Companion 整体异常：回退原始小智对话；
5. 运维紧急关闭：`companion.enabled=false`。

## 14. 测试计划

### 14.1 Python

- dot-skill schema 1/2/3 与 legacy layout；
- ZIP/GitHub 安全来源；
- PersonaSpec schema、Compiler 和 Prompt Injection；
- 公众人物关系上限；
- Emotion/Relationship reducer；
- Memory 排序、去重和隐私过滤；
- Runtime before/after turn、幂等和 fail-open；
- Manager API Repository 与 Filesystem Registry。

### 14.2 manager-api

- Gallery 同步和缓存；
- Import Job 自动状态流转、取消、恢复和幂等；
- 生命周期、可见性和用户资源隔离；
- Agent 绑定快照并发保护；
- Runtime Resolve/State/Commit/Memory；
- HMAC 签名和重放防护；
- Liquibase 在空库和升级库执行。

### 14.3 manager-web

- i18n 键一致性；
- Persona API 封装；
- Gallery、URL、ZIP 导入；
- 三步进度和失败状态；
- 版本管理、绑定和 Overlay 表单；
- Voice Clone 上传、训练和角色音色选择；
- 生产构建与页面快照。

### 14.4 现场端到端

1. 启动 MySQL、Redis、manager-api、xiaozhi-server 和 manager-web；
2. 从 Gallery 导入一个 dot-skill；
3. 自动编译测试并发布；
4. 绑定到测试智能体；
5. 使用同一用户进行多轮对话并重连；
6. 验证关系阶段、事件和记忆延续；
7. 发布 v2，再回滚 v1，状态不丢失；
8. 上传一段声音样本，训练后切换音色；
9. 用 ESP32 实机验证语音、打断、工具调用和重连。

## 15. 实施里程碑

### P0：Persona 契约与导入器——已实现

- PersonaSpec v1；
- dot-skill/legacy/manual Adapter；
- 安全来源读取；
- Runtime Prompt Compiler；
- Filesystem Registry 和 CLI。

### P1：Companion Runtime——已实现

- Session、Context Builder、State Reducer；
- Emotion/Relationship；
- Event/Memory；
- SQLite/manager-api Repository；
- 主对话链插入点和 fail-open。

### P2：人物管理闭环——已实现

- MySQL Persona Registry；
- Gallery/URL/ZIP 导入；
- Compiler 内部 API；
- 测试、发布、回滚、归档；
- Agent 绑定和 Runtime Resolve。

### P3：前端与交付——已实现

- Persona 人物库；
- 三步自动导入；
- 版本预览与 Diff；
- 角色配置简化；
- 指标、健康接口和 Docker Compose。

### P4：声音与表现——代码已接入，待真实供应商/设备验收

- 复用 Voice Clone；
- emotion style 向兼容 TTS 透传；
- 不兼容 Provider 自动忽略风格参数；
- ESP32 表现提示保持可选和兼容。

## 16. 下一步开发顺序

1. 在开发环境的空库和已有 Companion 数据库分别应用完整 Liquibase changelog；
2. 接入 colleague-skill Gallery 真实条目，完成导入、编译、测试、发布、绑定和回滚闭环；
3. 用至少 30 轮真实语音对话调参表达 DNA、关系阈值、记忆抽取和召回；
4. 选择一个实际 TTS Provider 跑通 Voice Clone，并验证动态情绪能力提示与降级；
5. 在 ESP32 实机完成延迟、打断、重连、工具调用、主动关心和音色切换验收；
6. 再决定离线主动推送、头像、Live2D 和表情映射等表现层扩展。

## 17. 完成定义

最终成品必须同时满足：

- 用户可在网页中导入、测试、发布、回滚和绑定人物；
- dot-skill 不在运行时执行，Canonical PersonaSpec 可追溯到来源 hash；
- 多轮对话中人物语言和行为稳定，不退化为通用助手；
- 情绪、关系和记忆跨会话延续，更新人物版本不会丢状态；
- 公众人物关系上限不可被 Overlay 放宽；
- Companion 故障不会中断原有语音聊天；
- 训练成功的克隆音色可在角色配置中直接启用；
- 核心单测、构建、数据库迁移和实机验收均通过。

## 18. 文档维护规则

本文件是最终产品实施真源。架构或状态机发生变化时优先更新本文件；底层类、接口和每轮调用细节同步到
`companion-core-implementation-plan.md`，部署命令同步到 `deploy/README.md`。
