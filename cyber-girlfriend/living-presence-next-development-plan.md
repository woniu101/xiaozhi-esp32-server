# Companion Core 活人感下一阶段开发方案

> 状态：Planned v1.0
>
> 更新日期：2026-08-22
>
> 适用基线：`cyber-girlfriend-final-product-plan.md` 的 P0-P6 已实现版本
>
> 目标：指导后续 P7-P13 开发，使人物、关系、记忆、主动行为和声音形成同一套可验证的行为链路

## 1. 结论与开发重点

当前项目已经具备 Persona 导入/发布、人物绑定、关系状态、长期记忆、主动关心、动态 TTS 和诊断基础，不需要重写 Companion Core。距离“活人感”最主要的差距不是再增加一份人物提示词，而是以下链路仍未统一：

1. ASR 感知到的用户情绪没有稳定地结构化传入 Companion；
2. 文本回复计划、人物当前心情、TTS 情绪和设备表情各自决策，可能互相矛盾；
3. 关系变化依赖少量关键词事件，普通但持续的相处很难产生合理变化；
4. 主动关心主要由固定时间触发，缺少“为什么此刻想起用户”的事件依据；
5. GPT-SoVITS V2 与 IndexTTS2.5 已能工作，但尚未形成按人物、音色校准的统一表达层；
6. 现有测试以功能正确为主，尚不能回答“像不像这个人”“情绪是否自然”。

下一阶段按以下优先级推进：

1. 先统一每轮输入信号与表达计划，消除错情绪、串情绪；
2. 再升级情绪、关系、记忆和主动行为；
3. 然后增强 Persona 编译与两类 TTS 的音色校准；
4. 最后用固定语音回归集持续验收，而不是凭单次试听判断。

## 2. 当前实现审计

### 2.1 可直接复用的能力

- `core/companion/importers/`：dot-skill 安全导入、Canonical PersonaSpec 编译和校验；
- `core/companion/context_builder.py`：Persona、关系、记忆、回应计划的上下文装配；
- `core/companion/relationship/`：关系状态和关系阶段基础模型；
- `core/companion/repositories/`：SQLite/manager-api 状态、记忆、Outbox；
- `core/companion/proactive.py` 与 `proactive_playback.py`：在线主动播放和基本约束；
- `core/companion/presentation.py`：文本表现风格到设备表现提示的基础映射；
- `core/providers/tts/gpt_sovits_v2.py`：参考音频式语气合成；
- `core/providers/tts/index_tts_v2_5.py`：八维情绪向量式合成；
- 管理端角色配置、音色管理、最近一轮诊断和人物记忆管理界面。

### 2.2 已确认的主要问题

#### 输入感知

- `core/providers/asr/utils.py` 能产生情绪信息，但 `core/handle/receiveAudioHandle.py` 没有为每一轮稳定保留结构化字段；
- 当前 `RuleBasedEventExtractor` 主要依赖少量正则规则，语义覆盖不足；
- 用户情绪、人物自身心情、该句应采用的表达语气没有明确分层。

#### 表达链路

- `ResponsePlanner`、`EmotionEngine.describe()`、`resolve_presentation()` 和 TTS Provider 分别推断表达；
- `CompanionTurnContext.expected_expression` 已生成但没有成为唯一执行依据；
- TTS Provider 使用可变的当前情绪状态，工具回复、主动回复、打断或并发轮次存在继承旧语气的风险；
- 当前只有第一段文本参与部分表现决策，长回复内不同句子的语气不可控。

#### 关系与记忆

- 关系变化集中在关心、感谢、辱骂、道歉、共同计划和重要倾诉等稀疏事件；
- dot-skill 导入后的 `stage_transition_rules` 尚未真正成为关系引擎策略；
- 关系阶段已经保存，但阶段变化对称呼、主动程度、玩笑尺度、冲突修复等行为影响仍不够明显。

#### 主动行为

- 当前主动关心以间隔、安静时段、次数和拒绝冷却为主；
- 缺少承诺到期、未完话题、近期低落、习惯时间、久别重逢等机会事件；
- 主动调度状态仍需要进一步持久化，才能可靠支持服务重启和多实例。

#### 声音表达

- GPT-SoVITS V2 的情绪依赖参考音频；绝对路径配置不利于迁移，且缺少参考资产完整性检查；
- IndexTTS2.5 的八维向量是模型控制维度，不应直接等同于产品层人物情绪；
- 两个 Provider 尚无统一的“产品表达风格 → Provider 参数”协议；
- 当前缺少每个音色的强度、语速、参考片段或向量校准档案。

## 3. 目标架构

每一轮只允许产生一份不可变的 `TurnExpressionPlan`，文本、TTS、设备表情和诊断都消费它：

```text
语音/文本输入
  → UserTurnSignal（用户说了什么、声音表现、文本情绪、置信度）
  → Companion 事件、关系、记忆和人物心情更新
  → ResponsePlan（这一轮说什么、边界和行为意图）
  → TurnExpressionPlan（这一轮怎么说）
  → LLM 文本生成
  → SentenceTtsEnvelope（每句绑定 turn_id/sentence_id/表达参数）
  → GPT-SoVITS V2 或 IndexTTS2.5
  → 设备播放/表情 + 诊断记录
```

### 3.1 `UserTurnSignal`

建议新增为不可变数据对象：

```python
@dataclass(frozen=True)
class UserTurnSignal:
    turn_id: str
    text: str
    source: str                    # voice/text/tool
    acoustic_emotion: str | None
    acoustic_confidence: float
    text_emotion: str | None
    text_confidence: float
    valence: float
    arousal: float
```

要求：

- ASR 没有说话人或没有情绪时仍返回纯净文本；
- 声学与文本判断冲突时保留两个来源，不提前覆盖；
- 低置信度只进入诊断，不直接推动关系或强情绪；
- 不把原始音频或不必要的原始识别 JSON 写入长期诊断。

### 3.2 `TurnExpressionPlan`

产品层使用 8 个主表达风格和可叠加修饰词：

- 主风格：`neutral`、`intimate`、`joyful`、`playful`、`excited`、`comforting`、`vulnerable`、`annoyed`；
- 修饰词：`soft`、`restrained`、`apologetic`、`shy`；
- 强度：`0.0-1.0`；
- 语速：建议限制在 `0.85-1.15`；
- 原因码：只记录可审计的因素，例如 `user_distress`、`relationship_reunion`，不保存模型推理过程。

```python
@dataclass(frozen=True)
class TurnExpressionPlan:
    turn_id: str
    primary_style: str
    modifiers: tuple[str, ...]
    intensity: float
    speed: float
    reason_codes: tuple[str, ...]
    device_expression: str
    provider_hint: dict[str, object]
```

产品层的 8 种风格不是 GPT-SoVITS 或 IndexTTS 的固定参数。Provider Adapter 负责分别映射为参考音频预设或八维向量。

### 3.3 `SentenceTtsEnvelope`

```python
@dataclass(frozen=True)
class SentenceTtsEnvelope:
    turn_id: str
    sentence_id: str
    text: str
    expression_plan: TurnExpressionPlan
```

所有普通回复、工具回复和主动回复必须通过该对象进入 TTS。取消轮次后，根据 `turn_id` 丢弃迟到音频，禁止 Provider 从全局可变字段读取上一轮情绪。

## 4. 分阶段实施

## P7：统一输入与每轮表达计划

目标：先解决最影响体验的“听错情绪、文本与声音不一致、上一轮语气串到下一轮”。

### 开发内容

1. 在 ASR 到会话入口间传递 `UserTurnSignal`，兼容旧 Provider 只返回字符串的情况；
2. 让事件提取器同时消费文本、声学情绪与置信度；
3. 合并 `ResponsePlanner`、`EmotionEngine.describe()` 和 `resolve_presentation()` 的表达决策入口；
4. 生成一次 `TurnExpressionPlan`，提供给 Prompt、TTS、设备表现和诊断；
5. 使用 `SentenceTtsEnvelope` 替换 TTS Provider 的全局 `current_emotion_style` 依赖；
6. 主动回复和工具回复也必须显式生成新计划；
7. 最近一轮诊断展示最终主风格、修饰词、强度、Provider 映射和降级原因。

### 主要修改位置

- `main/xiaozhi-server/core/providers/asr/utils.py`
- `main/xiaozhi-server/core/handle/receiveAudioHandle.py`
- `main/xiaozhi-server/core/companion/state_models.py`
- `main/xiaozhi-server/core/companion/response_planner.py`
- `main/xiaozhi-server/core/companion/presentation.py`
- `main/xiaozhi-server/core/connection.py`
- `main/xiaozhi-server/core/providers/tts/base.py`
- 两个目标 TTS Provider 与主动播放路径

### 验收标准

- 连续执行开心 → 悲伤 → 工具回复 → 主动回复，四轮语气互不污染；
- ASR 无情绪、低置信度或返回旧格式时仍能正常对话；
- 打断上一轮后不播放上一轮迟到音频；
- 文本计划、TTS 参数和设备表情使用相同主风格；
- 不支持动态情绪的 TTS 自动退化为普通合成。

## P8：情绪引擎 2.0

目标：让人物有连续但不过度戏剧化的心情，并能正确回应用户情绪。

### 状态分层

- `UserAffect`：当前用户的情绪估计，只描述用户；
- `CompanionMood`：人物跨轮延续的心情，例如愉悦、唤醒度、亲近、烦躁、疲劳；
- `TurnExpression`：当前一句实际采用的表达方式。

### 策略

- 使用 ASR 声学信号 + 文本规则/本地轻模型，首版不增加一次远程 LLM 调用；
- 加入迟滞和最短保持时间，避免一句话造成情绪来回跳；
- 同类事件连续出现时衰减增量，避免情绪被刷满；
- 根据 Persona 增加 `reactivity`、`recovery_rate`、`expressiveness` 配置；
- 限制负面情绪强度，`annoyed` 默认以克制修饰输出，不辱骂、不惩罚用户；
- 声音强度低于文本行为强度上限，防止 TTS 过度表演。

### 验收标准

- 相似输入在相邻轮次表现稳定；
- 明确高兴、委屈、疲惫、冲突和道歉能产生不同但合理的行为；
- 用户低落时人物可以关心，但不会错误模仿成同样低落；
- 情绪随时间回归 Persona 基线。

## P9：关系、记忆与阶段行为

目标：让关系由持续相处形成，并在行为上可感知，而不是只显示一个阶段标签。

### 新增关系事件

- 有效持续对话、主动关心被接受或拒绝；
- 承诺创建、履行和失约；
- 正确记住偏好、用户纠正错误记忆；
- 冲突、修复、边界被尊重或被越过；
- 久别与回归、固定称呼、共同仪式；
- 重要事件后续追问、共同完成计划。

### 阶段策略

- 为 PersonaSpec 落地 `stage_transition_rules`，由本项目的关系引擎执行；
- dot-skill 提供人物倾向和行为素材，不允许直接写入信任/好感分数；
- 阶段上限由角色配置的 `allowed_stages` 决定；
- 阶段变化至少影响称呼、主动频率、玩笑尺度、自我暴露、冲突修复和告别/重逢表达；
- 使用冷却、有效轮次、事件多样性和冲突门槛，避免短时间刷关系。

### 验收标准

- 普通稳定交流也能缓慢发展关系；
- 单一关键词或重复夸奖不能快速升阶；
- 切换 Persona 时状态隔离，切回后恢复；
- 阶段升级后行为差异可由盲测识别，且不突破配置上限。

## P10：事件驱动的主动关心

目标：从“每隔几小时问候”升级为“因为记得某件事而联系用户”。

### 机会来源

- 承诺或计划到期；
- 上一轮未完话题；
- 近期低落、疲惫或压力事件；
- 用户习惯时间和固定仪式；
- 生日、考试、出差等重要日期；
- 长时间未互动后的重逢；
- 可选的时间、天气或设备事件。

### 调度规则

- 机会先计算分数，再应用在线状态、空闲状态、安静时段、每日上限、拒绝冷却和未回复退避；
- 主动消息必须带 `opportunity_id`，同一机会只发送一次；
- 将待触发机会、最近发送时间、未回复次数持久化；
- 多实例通过租约或数据库原子更新避免重复发送；
- 首版仍只做在线主动播放，离线推送另立需求。

### 验收标准

- 重启服务不会忘记或重复发送同一机会；
- 被拒绝后按人物配置退避；
- 主动内容能引用真实记忆来源，不编造共同经历；
- 主动回复也生成独立的表达计划和句子 ID。

## P11：Persona 编译质量 2.0

目标：把 dot-skill 的人物素材编译成可执行的对话行为，而不是把长 Markdown 直接塞入 Prompt。

### 编译产物

- 口头禅及使用条件、句长和停顿倾向；
- 幽默、调侃、关心、冲突和修复方式；
- 各关系阶段的称呼、边界、主动行为和自我暴露程度；
- 禁止表达、低频表达和最近表达去重策略；
- 问候、低落、成功、调侃、边界、道歉、记忆、工具调用、主动关心、告别和重逢场景示例。

### 原则

- 蒸馏在导入/发布阶段执行，运行时只读取已编译产物；
- 来源文件不执行脚本；
- 编译结果保留 source hash 和 warning，可回滚；
- 开源 Skill 可复用人物风格，但关系规则、状态和安全边界仍由本项目管理。

### 验收标准

- 同一人物在 50 轮对话中不明显退化成通用助手；
- 不同 Persona 对相同场景的回应可被盲测区分；
- 人物特征不是靠每句重复口头禅实现；
- 版本升级不会清空既有关系与记忆。

## P12：GPT-SoVITS V2 与 IndexTTS2.5 表达层

目标：让两类模型共享产品表达语义，同时保留各自最合适的控制方式。

### 4.12.1 通用 Provider 协议

新增统一 Provider 入参：

- `voice_id`；
- `primary_style`、`modifiers`、`intensity`、`speed`；
- `turn_id`、`sentence_id`；
- `fallback_allowed`。

Provider 返回：

- 实际采用的 preset/vector/alpha/speed；
- 是否降级及原因；
- 合成耗时、首包耗时和音频时长。

### 4.12.2 GPT-SoVITS V2

GPT-SoVITS V2 不使用固定八维向量。建议每个音色维护以下参考资产角色：

- `neutral`：日常平稳；
- `joyful`：自然开心；
- `playful`：调侃或俏皮；
- `comforting`：轻柔安慰；
- `vulnerable`：低落或委屈；
- `annoyed`：克制不满；
- `excited`：高唤醒兴奋。

`intimate` 默认由 neutral/comforting 参考 + 较低语速实现，不要求额外强制切片。情绪功能关闭时只使用 neutral 参考资产。

配置优化：

- manager-api 管理 `asset_id`，不要把另一台电脑的绝对路径存为业务配置；
- 远端服务通过 `voice_id + preset` 解析自己的本地文件；
- 上传时同时保存参考文本、语言、采样率、时长和 hash；
- 发布前检查文件存在、文本非空、音频时长和静音比例；
- 缺少目标 preset 时按 `同音色 neutral → Provider 默认 → 普通 TTS` 降级；
- 管理端提供逐 preset 试听及同文本 A/B 对比。

参考音频需要从音色素材中自行挑选/切片并人工复核；不要假设官方能自动生成目标人物的七类参考音频。

### 4.12.3 IndexTTS2.5

IndexTTS2.5 的 8 个原生维度按部署接口定义保留，例如 happy、angry、sad、afraid、disgusted、melancholic、surprised、calm。产品层风格通过映射表转换，不直接向 UI 暴露为人物情绪定义。

优化内容：

- 所有向量在本项目归一化/限幅后再发送，避免远端二次归一化改变比例；
- 去除导致低强度仍然明显着色的隐藏 alpha 下限；
- 对 neutral 做“省略情绪参数”和“低强度 calm”A/B 验收；
- 为每个 `voice_id` 保存向量、alpha、speed 的校准覆盖；
- 管理端展示最终有效向量与 alpha，而不仅显示“动态情绪已开启”；
- 为过强的 angry/afraid/disgusted 设置产品上限，人物不满优先采用低强度 + restrained。

### 4.12.4 动态情绪开关

- 保留智能体级总开关；
- 增加音色级“支持/已校准”状态；
- 关闭时仍保留人物文本风格，只禁用 Provider 情绪参数；
- 开启但资源不完整时允许降级并在诊断中明确显示；
- 管理端不能把 GPT-SoVITS 的参考预设误显示为 IndexTTS 八维情绪。

### 验收标准

- 同一句文本可在中性、开心、安慰、不满四种场景中稳定区分；
- 人物音色不因表达控制明显漂移；
- 迁移服务器时无需编辑数据库中的 Windows/Linux 绝对路径；
- 任一情绪资源缺失不会中断整轮对话；
- Provider 参数与该句的 turn/sentence ID 可追踪。

## P13：活人感评测与回归集

目标：建立可重复的质量门禁，避免每次优化只靠主观试听。

### 数据集

首版为童锦程和兔娘类 Persona 各准备 50-100 轮固定场景，覆盖：

- 日常问候、无聊闲聊和重复话题；
- 开心分享、疲惫、委屈、冲突、道歉和修复；
- 个人偏好、承诺、后续追问和错误记忆纠正；
- 工具调用、主动关心、拒绝主动、久别重逢；
- 打断、重连、TTS 超时和情绪资源缺失。

### 指标

- 人物可识别度与跨轮一致性；
- 情绪判断准确率与文本/声音一致性；
- 关系阶段边界正确率；
- 记忆准确率、错误引用率和编造率；
- 主动消息相关性、接受率和打扰率；
- 句式/口头禅重复率；
- 首 Token、首包音频、整轮耗时、打断停止时延；
- GPT-SoVITS 与 IndexTTS 的音色相似度和表达自然度人工评分。

### 门禁建议

- 核心单测和前端构建全部通过；
- 串轮情绪、迟到音频、重复主动消息为 0；
- 事实型记忆不得凭空生成；
- 固定场景的表达风格命中率达到 85% 后再扩大风格数量；
- 实机首包和打断 SLO 达标后再加入 Live2D。

## 5. 推荐执行顺序

| 顺序 | 工作包 | 预期产物 | 依赖 |
|---|---|---|---|
| 1 | P7.1 ASR 结构化信号 | `UserTurnSignal` 与兼容适配 | 无 |
| 2 | P7.2 统一表达计划 | `TurnExpressionPlan` | P7.1 |
| 3 | P7.3 句子级 TTS 信封 | 无跨轮情绪污染 | P7.2 |
| 4 | P8 情绪引擎 2.0 | 三层情绪状态与迟滞策略 | P7 |
| 5 | P9 关系与记忆事件 | 可解释升阶与阶段行为 | P8 |
| 6 | P10 主动机会队列 | 事件驱动、可持久化调度 | P9 |
| 7 | P11 Persona 编译 2.0 | 场景行为与阶段素材 | P9 |
| 8 | P12 TTS 表达校准 | GPT 预设与 Index 向量档案 | P7、P8 |
| 9 | P13 固定回归集 | 自动报告与实机验收表 | 全部 |

P7 应作为下一个实际开发迭代。P8-P12 可以先设计数据结构，但不要在 P7 完成前同时改动多条运行链路。

## 6. 数据库与接口演进建议

优先复用现有 Companion 状态、事件、诊断和音色表，新增字段使用向后兼容迁移：

- Companion 事件增加 `source`、`confidence`、`opportunity_id` 等结构化元数据；
- 最近一轮诊断增加 expression plan 摘要、实际 Provider 参数和降级原因；
- 音色资产增加 `asset_id`、`preset`、`content_hash`、`duration_ms`、`remote_status`；
- 音色校准增加 `provider`、`voice_id`、`style`、`mapping_json`、`version`；
- 主动机会增加唯一键、触发时间、状态、租约和去重字段。

所有变更必须：

- 使用 Liquibase 新 changelog，不修改已部署的历史 changelog；
- API 新字段保持可选，旧管理端和旧 Python 服务能继续运行；
- Provider 未升级时自动走 neutral/普通合成；
- 不在诊断中保存原始私密对话或模型完整推理过程。

## 7. 测试矩阵

### 单元测试

- ASR 新旧返回格式、置信度边界和纯文本降级；
- 表达计划优先级、迟滞、修饰词组合和强度限幅；
- turn/sentence ID 隔离、打断和迟到音频丢弃；
- 关系事件去重、冷却、升阶上限和回滚；
- 主动机会去重、重启恢复、拒绝冷却和多实例抢占；
- GPT preset 缺失降级和 Index 向量限幅/归一化。

### 集成测试

- WebSocket 真实对话链路；
- manager-api 暂停、恢复与 Outbox 重放；
- GPT-SoVITS V2、IndexTTS2.5 正常、超时、资源缺失；
- 管理端音色上传、同步、试听、删除和跨机迁移；
- ESP32/py-xiaozhi 播放、打断、重连和主动播放。

### 发布前人工验收

- 同一音色至少用四种典型风格完成盲听；
- 同一场景由两个 Persona 回答，能识别人物差异；
- 关系初识、熟悉、朋友/暧昧三个阶段行为有明显但不突兀的差异；
- 主动关心能解释触发来源，用户拒绝后不继续打扰。

## 8. 完成定义

本路线完成时，必须同时满足：

- 用户的文本和声学情绪以结构化信号进入 Companion；
- 每轮只有一份表达计划，文本、TTS、设备表现和诊断一致；
- 普通、工具、主动和异常降级回复均不会继承上一轮情绪；
- 关系由多种真实事件缓慢发展，阶段上限由本项目配置控制；
- 主动关心由记忆或事件驱动，并能跨重启去重；
- dot-skill 编译结果能稳定体现人物的语言、边界和关系阶段行为；
- GPT-SoVITS V2 和 IndexTTS2.5 可按音色校准、可迁移、可降级；
- 固定语音回归集能给出人物、情绪、关系、记忆、主动性和时延报告。

## 9. 明确不在本阶段处理

- Live2D、头像、身体动作和复杂视觉舞台；
- 离线手机推送和跨渠道消息；
- 让 Persona 或 dot-skill 直接修改关系分数；
- 用单次远程 LLM 调用承担所有情绪分类；
- 在完成表达一致性与实机 SLO 前增加更多 TTS 模型。

上述内容在 P7-P13 稳定后再评估，避免视觉或模型数量掩盖核心对话链路问题。
