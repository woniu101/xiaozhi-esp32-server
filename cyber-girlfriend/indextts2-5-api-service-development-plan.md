# IndexTTS2.5 API 服务改造与动态情绪接入方案

> 状态：Implementation Baseline v1.0
> 编写日期：2026-08-21
> 目标仓库：`index-tts/index-tts`（部署 IndexTTS2.5 的电脑）
> 上游基线：以目标电脑实际检出的 Git commit 为准
> 用途：在另一台电脑的新开发窗口中，作为 IndexTTS2.5 项目侧的独立实施与验收文档

## 0. 给新开发窗口的执行指令

在开始编码前，先完整阅读本文档，并在目标电脑的 IndexTTS2.5 仓库内完成以下只读检查：

1. 记录 `git rev-parse HEAD`、操作系统、Python、PyTorch、CUDA、显卡型号和显存。
2. 确认 WebUI 能用预定参考音频稳定合成语音。
3. 检查本地 `indextts/infer_v2_5.py` 的 `IndexTTS2.__init__`、`infer` 和 `infer_generator` 签名，不可仅按本文档猜测。
4. 检查工作区是否已有用户修改；保留并避开无关改动。
5. 先实施“阶段一：稳定非流式 API”，完成自动测试和真实显卡冒烟测试后再交付。
6. 本次只改 IndexTTS2.5 项目，不修改 `xiaozhi-esp32-server`，也不修改设备端协议。

若目标仓库代码与本文档描述不同，以本地源码为事实依据，保持本文档定义的外部 API 契约，并在交付说明中记录兼容调整。

---

## 1. 背景与结论

现有 IndexTTS2.5 WebUI 已能完成音色克隆，但 WebUI 不是稳定的服务接口，无法直接作为 `xiaozhi-esp32-server` 的长期 TTS 后端。建议在 IndexTTS2.5 仓库中增加一层轻量 API 服务：

- 模型只在进程启动时加载一次；
- 通过固定 `voice_id` 选择服务器本地参考音频；
- 接收 Companion Core 生成的八维情绪向量；
- 返回标准 WAV；
- 在非流式接口稳定后，再提供“按文本段返回”的实验性流式接口；
- WebUI 保留用于人工调音和验证，不把 Gradio 接口当生产接口。

第一阶段的核心链路为：

```text
xiaozhi-esp32-server
  -> HTTP POST /v1/tts
  -> IndexTTS2.5 API 参数校验
  -> voice_id 查找本地参考音频
  -> 八维情绪向量归一化
  -> 单实例、单并发 GPU 推理
  -> PCM16 / 22050 Hz / 单声道 WAV
  -> xiaozhi 服务端继续执行设备所需的编码和播放链路
```

## 2. 改造边界

### 2.1 本次必须实现

- 独立 API 启动入口和配置文件；
- 存活、就绪、能力、音色列表接口；
- 非流式 TTS 接口；
- `voice_id` 到本地参考音频的注册表；
- IndexTTS2.5 原生八维情绪向量接入；
- 语速、语言和文本规范化参数；
- 模型单例、GPU 串行推理、有界排队；
- 统一错误结构、请求日志、耗时与 RTF 指标；
- 无 GPU 的接口测试和有 GPU 的真实冒烟测试；
- 启动、配置、调用和排障说明。

### 2.2 第二阶段实现

- 实验性的按段 PCM 流式接口；
- 客户端断开后的分段取消；
- 首包延迟、分段数量和流式完整性测试。

### 2.3 本次不实现

- 不修改 `xiaozhi-esp32-server`；
- 不修改 ESP32 或其他设备端协议；
- 不重新训练 IndexTTS2.5 模型；
- 不重写 `indextts/infer_v2_5.py` 的核心推理过程；
- 不把 Gradio WebUI 的内部路由当正式 API；
- 不做真正的 token/帧级低延迟流式；
- 不加入账号、API Key、双授权或声音授权流程；
- 不在 IndexTTS 服务中重复实现 Companion Core 的情绪判断逻辑；
- 不在第一阶段启用 QwenEmotion 文本情绪模型。

## 3. 已核对的 IndexTTS2.5 能力

截至本文档编写日期，官方 `main` 分支公开接口具备以下能力：

- 初始化入口：`from indextts.infer_v2_5 import IndexTTS2`；
- IndexTTS2.5 推理必须提供 `lang`；
- 支持单参考音频音色克隆；
- 支持独立情绪参考音频；
- 支持八维情绪向量；
- 支持 `emo_alpha` 情绪强度；
- 支持文本推导情绪，但需要初始化时启用 `use_qwen_emo=True`；
- 支持 `duration_factor` 语速/时长控制；
- 原生推理输出采样率为 22050 Hz；
- `stream_return=True` 会按内部文本段依次产出音频张量和段间静音。

官方参考：

- [IndexTTS 官方仓库](https://github.com/index-tts/index-tts)
- [IndexTTS2.5 推理源码](https://github.com/index-tts/index-tts/blob/main/indextts/infer_v2_5.py)

### 3.1 八维情绪向量顺序

顺序必须固定为：

```text
[happy, angry, sad, afraid, disgusted, melancholic, surprised, calm]
```

中文语义分别是：

```text
[高兴, 愤怒, 悲伤, 恐惧, 反感, 低落, 惊讶, 平静]
```

严禁在 API 内部按字典遍历顺序拼接向量。应使用固定常量显式映射，并在能力接口中返回顺序。

### 3.2 关于原生“流式”的准确说明

当前 `stream_return=True` 是按模型内部切分后的完整文本段产出音频，不是 token 级或音频帧级流式。短句很可能只产生一个语音段，因此首包延迟不一定明显优于非流式接口。

接口和文档中必须称为“分段流式”或 `segment_streaming`，不能宣传为真正的实时流式。第一阶段优先把非流式链路做稳定。

## 4. 设计原则

1. 外部契约稳定，内部适配上游源码变化。
2. 模型只加载一次，不在每个请求中重新初始化。
3. GPU 推理默认单并发；HTTP 可以并发接收，请求进入有界队列。
4. Companion Core 决定语义情绪，IndexTTS2.5 只负责把情绪向量表现为声音。
5. 第一阶段只开放必要参数，禁止客户端透传任意 `generation_kwargs`。
6. 参考音频只能通过 `voice_id` 选择，不能由调用方提交任意文件路径或 URL。
7. WebUI 和 API 第一阶段不同时占用同一块显卡，避免重复加载和显存争用。
8. 所有真实 GPU 功能必须在交付前至少完成一组中性和三组情绪冒烟测试。

## 5. 推荐目录结构

在 IndexTTS2.5 仓库根目录新增以下文件。若本地仓库已有服务目录，可保持职责不变地合并到现有结构中。

```text
index-tts/
├── api_server_v2_5.py
├── api_config.yaml
├── voices/
│   ├── voices.yaml
│   └── references/
│       └── target_voice.wav
├── indextts_service/
│   ├── __init__.py
│   ├── app.py
│   ├── audio.py
│   ├── config.py
│   ├── errors.py
│   ├── runtime.py
│   ├── schemas.py
│   └── voice_registry.py
└── tests/
    └── api_service/
        ├── conftest.py
        ├── test_audio.py
        ├── test_health.py
        ├── test_schemas.py
        ├── test_tts_api.py
        └── test_voice_registry.py
```

职责划分：

| 文件 | 职责 |
| --- | --- |
| `api_server_v2_5.py` | 命令行入口，读取配置并启动 Uvicorn |
| `app.py` | FastAPI 生命周期、路由和依赖装配 |
| `config.py` | YAML 与环境变量配置、路径解析和启动校验 |
| `schemas.py` | 请求、响应和能力模型 |
| `runtime.py` | IndexTTS2.5 单例、队列、锁、推理和指标 |
| `voice_registry.py` | `voice_id` 注册、音频存在性检查和元数据输出 |
| `audio.py` | Tensor/NumPy 到 PCM16/WAV 的转换 |
| `errors.py` | 稳定错误码和异常到 HTTP 的映射 |

不要为了 API 服务复制一份 `infer_v2_5.py`。服务层直接调用仓库内的原生类，减少后续升级时的分叉成本。

## 6. 配置设计

### 6.1 `api_config.yaml`

建议配置：

```yaml
server:
  host: 0.0.0.0
  port: 7861
  request_timeout_seconds: 120
  max_queue_size: 4
  cors_origins: []

model:
  cfg_path: checkpoints/config.yaml
  model_dir: checkpoints
  device: cuda:0
  use_bf16: true
  use_cuda_kernel: true
  use_deepspeed: false
  use_accel: false
  use_torch_compile: false
  use_qwen_emo: false
  low_vram: false

inference:
  default_lang: ZH
  allowed_languages: [ZH, EN, JA, ES, AR]
  max_text_length: 300
  interval_silence_ms: 120
  max_text_tokens_per_segment: 120
  default_emotion_alpha: 0.75
  apply_emotion_bias: true
  text_normalization: true
  warmup_on_start: true
  warmup_text: "你好，很高兴见到你。"

voices:
  registry_path: voices/voices.yaml

logging:
  level: INFO
  log_request_text: false
```

注意：

- 所有相对路径统一相对于仓库根目录或配置文件目录解析，选一种规则并写测试；
- 启动时必须输出最终解析后的绝对模型路径、设备和精度，但不要打印声音二进制；
- `low_vram` 只有本地 `IndexTTS2` 实例确实暴露对应属性时才设置；
- `allowed_languages` 以目标电脑源码中的 `lang_to_token` 支持范围为最终依据。

### 6.2 `voices/voices.yaml`

示例：

```yaml
voices:
  - id: target_voice
    name: 目标音色
    reference_audio: references/target_voice.wav
    enabled: true
    default_language: ZH
    description: 主项目使用的克隆音色
```

启动时对每个启用音色执行：

- ID 格式校验：`^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$`；
- 重复 ID 校验；
- 解析后的音频必须位于 `voices/` 根目录内；
- 文件必须存在、可读且是允许的音频格式；
- 尝试读取音频头和时长，失败则服务不进入 ready；
- 参考音频建议为干净、单人、少混响、无背景音乐的 5～15 秒语音。

禁止请求体传入 `C:\...`、`/home/...`、UNC 路径或 HTTP URL。此限制是输入安全和可重复部署要求，不是授权机制。

## 7. HTTP API 契约

统一前缀：`/v1`。健康检查除外。

### 7.1 `GET /health/live`

用途：只判断进程是否存活，不触发 GPU 推理。

响应：

```json
{
  "status": "ok"
}
```

### 7.2 `GET /health/ready`

用途：判断配置、音色注册表和模型是否已经加载，可否接收推理请求。

成功响应：

```json
{
  "status": "ready",
  "model": "IndexTTS2.5",
  "device": "cuda:0",
  "voices": 1
}
```

模型加载中或启动失败时返回 HTTP 503，并包含稳定错误码。

### 7.3 `GET /v1/capabilities`

响应至少包括：

```json
{
  "model": "IndexTTS2.5",
  "api_version": "1.0",
  "sample_rate": 22050,
  "channels": 1,
  "sample_format": "pcm_s16le",
  "output_formats": ["wav"],
  "languages": ["ZH", "EN", "JA", "ES", "AR"],
  "emotion": {
    "mode": "vector",
    "dimensions": 8,
    "order": [
      "happy",
      "angry",
      "sad",
      "afraid",
      "disgusted",
      "melancholic",
      "surprised",
      "calm"
    ]
  },
  "streaming": {
    "supported": false,
    "type": "segment"
  }
}
```

阶段二启用流式后将 `supported` 改为 `true`，API 版本不需要变化。

### 7.4 `GET /v1/voices`

只返回已启用的安全元数据，不返回服务器文件路径：

```json
{
  "voices": [
    {
      "id": "target_voice",
      "name": "目标音色",
      "default_language": "ZH",
      "description": "主项目使用的克隆音色"
    }
  ]
}
```

### 7.5 `POST /v1/tts`

请求：

```json
{
  "request_id": "01K32EXAMPLE",
  "text": "你今天回来得有点晚，我还以为你忘记我了。",
  "voice_id": "target_voice",
  "lang": "ZH",
  "speed": 1.0,
  "text_normalization": true,
  "emotion": {
    "mode": "vector",
    "vector": [0.05, 0.0, 0.12, 0.0, 0.0, 0.28, 0.0, 0.22],
    "alpha": 0.75
  }
}
```

`emotion` 可省略。省略时按中性方式合成，不应由服务端再次分析文本情绪。

成功响应：

- HTTP 200；
- `Content-Type: audio/wav`；
- WAV 内容为单声道、22050 Hz、PCM16；
- 建议响应头：

```text
X-Request-ID: 01K32EXAMPLE
X-Audio-Sample-Rate: 22050
X-Audio-Channels: 1
X-Audio-Duration-Ms: 2840
X-Inference-Time-Ms: 1160
X-Queue-Wait-Ms: 5
```

### 7.6 请求校验规则

| 字段 | 规则 |
| --- | --- |
| `request_id` | 可省略；省略则服务端生成；最大 64 字符 |
| `text` | 去除首尾空白后非空；第一阶段最大 300 字符 |
| `voice_id` | 必须存在且启用 |
| `lang` | 必须在本地源码支持的白名单中；省略则取音色或全局默认值 |
| `speed` | `0.5～2.0`；转换为 `duration_factor = 1 / speed` |
| `text_normalization` | 布尔值；省略取服务默认值 |
| `emotion.mode` | 第一阶段只接受 `vector` |
| `emotion.vector` | 恰好 8 个有限浮点数；单项范围 `0.0～1.2` |
| `emotion.alpha` | `0.0～1.0`；省略取默认值 |

不要开放 `output_path`、`spk_audio_prompt`、`emo_audio_prompt`、`generation_kwargs` 或任意磁盘路径参数。

### 7.7 错误响应

统一格式：

```json
{
  "error": {
    "code": "VOICE_NOT_FOUND",
    "message": "voice_id 不存在或未启用",
    "request_id": "01K32EXAMPLE"
  }
}
```

建议映射：

| HTTP | 错误码 | 场景 |
| --- | --- | --- |
| 400 | `INVALID_REQUEST` | 文本、语言、语速或情绪参数非法 |
| 404 | `VOICE_NOT_FOUND` | 音色不存在或未启用 |
| 429 | `QUEUE_FULL` | 等待队列达到上限 |
| 499/日志状态 | `CLIENT_DISCONNECTED` | 客户端在响应前断开；是否返回 499 取决于框架能力 |
| 500 | `INFERENCE_FAILED` | 模型推理或音频转换失败 |
| 503 | `MODEL_NOT_READY` | 模型未加载或启动检查失败 |
| 504 | `INFERENCE_TIMEOUT` | 排队加推理超过配置时限 |

生产响应只给出安全摘要，完整堆栈记录在服务器日志中。

## 8. 推理适配设计

### 8.1 模型初始化

`runtime.py` 在应用 lifespan 启动阶段创建一个 `IndexTTS2`：

```python
from indextts.infer_v2_5 import IndexTTS2

tts = IndexTTS2(
    cfg_path=config.model.cfg_path,
    model_dir=config.model.model_dir,
    use_bf16=config.model.use_bf16,
    device=config.model.device,
    use_cuda_kernel=config.model.use_cuda_kernel,
    use_deepspeed=config.model.use_deepspeed,
    use_accel=config.model.use_accel,
    use_torch_compile=config.model.use_torch_compile,
    use_qwen_emo=False,
)
```

实际调用参数必须根据目标电脑源码签名做兼容检查。模型加载成功、音色注册表有效并完成可选 warmup 后，`/health/ready` 才返回 200。

第一阶段固定 `use_qwen_emo=False`，原因是 Companion Core 已完成上下文、关系状态和语义情绪判断。若 IndexTTS 再根据单句判断情绪，会造成情绪来源冲突、显存增加和延迟上升。

### 8.2 情绪向量处理

处理顺序：

1. 按固定顺序读取 8 个数；
2. 拒绝 NaN、Infinity、负数和超出范围的值；
3. 调用本地模型的 `normalize_emo_vec(vector, apply_bias=...)`；
4. 将归一化后的向量和 `emo_alpha` 传入 `infer`；
5. `use_random=False`，优先保证音色稳定和结果可复现；
6. 记录归一化后的向量，但默认不记录完整文本。

官方归一化会对各维应用偏置，并将总强度压到不超过 0.8。服务层不要再自行实现一套不同的总和缩放算法；若目标版本没有公开该方法，才复制同版本逻辑到适配层并补单元测试。

调用形式：

```python
result = tts.infer(
    spk_audio_prompt=voice.reference_audio,
    text=request.text,
    output_path=None,
    lang=request.lang,
    emo_vector=normalized_vector,
    emo_alpha=request.emotion.alpha,
    use_emo_text=False,
    use_random=False,
    interval_silence=config.inference.interval_silence_ms,
    max_text_tokens_per_segment=config.inference.max_text_tokens_per_segment,
    duration_factor=1.0 / request.speed,
    text_normalization=request.text_normalization,
    stream_return=False,
    verbose=False,
)
```

目标版本返回值必须由测试确认。当前官方实现中，`output_path=None`、非流式模式返回 `(sampling_rate, wav_data)`。

### 8.3 WAV 编码

服务不能依赖临时文件完成正常请求，应优先在内存中完成：

1. 接收模型返回的 NumPy 数组；
2. 统一形状为单声道一维数组；
3. 如果不是 `int16`，先裁剪再转换；
4. 使用标准库 `wave` 和 `io.BytesIO` 封装 PCM16 WAV；
5. 返回字节并计算音频时长。

必须测试空数组、二维 `(n, 1)`、二维 `(1, n)`、浮点数组和 `int16` 数组，避免声道或转置错误。

## 9. 并发、队列和生命周期

### 9.1 单 GPU 调度

默认只有一个推理 worker：

```text
HTTP 请求 -> 非阻塞获取队列名额 -> 有界 FIFO 队列 -> 单 GPU worker -> 响应
```

要求：

- HTTP 事件循环中不得直接运行阻塞的 GPU 推理；
- 使用一个专用线程执行器或单独 worker 线程；
- 同一 `IndexTTS2` 实例一次只执行一个 `infer`；
- 队列满立即返回 429，不允许内存无限堆积；
- 记录排队时间和实际推理时间；
- 关闭服务时停止接收新请求，等待当前请求完成到合理上限，再释放资源。

不建议简单设置多个 Uvicorn worker。每个进程都会重新加载一份模型，可能直接耗尽显存。

### 9.2 WebUI 共存策略

第一阶段采用互斥运行：

- 调音时启动 `webui.py`；
- 对外服务时停止 WebUI，再启动 `api_server_v2_5.py`；
- 不让两个进程同时各加载一份模型到同一块显卡。

后续若确实需要同时使用，再把 WebUI 与 API 抽到同一个 runtime 单例中。这属于可选阶段，不能阻塞第一阶段交付。

### 9.3 音色缓存注意事项

官方实现会缓存当前参考音频的说话人条件。注册表应保存稳定的绝对路径，以便相同 `voice_id` 命中缓存。频繁切换多个音色可能反复清理和重建缓存，第一版优先服务一个主音色，不提前修改上游缓存结构。

## 10. 阶段二：实验性分段流式

### 10.1 接口

新增：

```text
POST /v1/tts/stream
Content-Type: application/octet-stream
X-Audio-Format: pcm_s16le
X-Audio-Sample-Rate: 22050
X-Audio-Channels: 1
X-Streaming-Type: segment
```

请求体与 `/v1/tts` 相同。响应体为连续的裸 PCM16 小端字节，不使用 WAV 容器，避免无法预先确定 WAV 长度的问题。

### 10.2 实现方式

- 调用 `tts.infer(..., stream_return=True, output_path=None)` 获取生成器；
- 在专用 GPU worker 内迭代生成器；
- 把每个张量转成连续的 PCM16 字节并放入线程安全队列；
- 异步 `StreamingResponse` 从队列逐块读取；
- 每段后保留一次模型产生的静音，不额外重复插入；
- 生成结束放入 EOF 标记；异常放入错误标记并记录 request ID。

当前官方生成器会依次产出“语音段、静音、语音段、静音……”，其中最后也可能带静音。实现和测试必须以目标 commit 的真实行为为准，防止重复静音、漏掉最后一段或拼接点击声。

### 10.3 限制

- 这仍然是分段流式；
- 短句可能只有一个语音块；
- 不对外暴露 `quick_streaming_tokens`，除非目标版本明确实现、官方文档说明并完成稳定测试；
- 客户端断开时，在下一个段边界停止继续生产；已进入 CUDA 内核的当前段不能安全强杀；
- 不通过强制终止推理线程实现取消，避免损坏模型状态。

如果真实测试表明首包收益很小、段间停顿明显或结果不稳定，则保留非流式接口作为正式能力，并把流式标记为关闭。

## 11. 日志与可观测性

每个请求至少记录：

- `request_id`；
- `voice_id`；
- 语言；
- 文本字符数，不默认记录全文；
- 是否使用情绪向量及归一化后向量；
- 排队时间；
- 推理时间；
- 输出音频时长；
- RTF：`inference_seconds / audio_seconds`；
- 流式首包时间和块数量；
- 成功、错误码或客户端断开状态。

启动日志至少记录：

- 服务版本与本地 Git commit；
- IndexTTS2.5 配置和模型目录；
- GPU、精度和加速开关；
- 已加载音色数量；
- warmup 结果；
- 模型加载后显存占用。

不得记录参考音频二进制、任意磁盘遍历结果或完整异常环境变量。

## 12. 依赖和启动方式

沿用 IndexTTS 官方的 `uv` 环境。在 `pyproject.toml` 中增加并锁定服务端依赖，至少包括：

- `fastapi`；
- `uvicorn`；
- `pydantic`；
- YAML 解析库（若仓库现有依赖已提供则复用）；
- `httpx`（测试用）。

建议命令：

```bash
uv sync --all-extras
uv run python api_server_v2_5.py --config api_config.yaml
```

启动后检查：

```bash
curl http://127.0.0.1:7861/health/live
curl http://127.0.0.1:7861/health/ready
curl http://127.0.0.1:7861/v1/capabilities
curl http://127.0.0.1:7861/v1/voices
```

非流式合成示例：

```bash
curl -X POST http://127.0.0.1:7861/v1/tts \
  -H "Content-Type: application/json" \
  -d '{
    "text": "你终于回来啦，我刚才还有一点担心你。",
    "voice_id": "target_voice",
    "lang": "ZH",
    "speed": 1.0,
    "emotion": {
      "mode": "vector",
      "vector": [0.18, 0.0, 0.0, 0.0, 0.0, 0.08, 0.0, 0.24],
      "alpha": 0.75
    }
  }' \
  --output output.wav
```

不要在本文档中写死目标电脑的公网地址。接入时由 `xiaozhi-esp32-server` 配置目标电脑的局域网地址，例如 `http://192.168.x.x:7861`。

## 13. 测试计划

### 13.1 无 GPU 自动测试

使用假的 runtime/模型返回固定 NumPy 音频，覆盖：

- live、ready、capabilities、voices；
- 模型未就绪返回 503；
- 空文本、超长文本、非法语言和非法语速；
- 未知音色；
- 情绪向量长度不是 8；
- NaN、Infinity、负数、越界和非法 alpha；
- `speed` 到 `duration_factor` 的转换；
- 向量顺序和官方归一化调用；
- WAV 头、采样率、声道数、位深和音频时长；
- 队列满返回 429；
- 推理异常返回稳定错误结构；
- 参考音频路径穿越被拒绝；
- 两个并发请求在模型层严格串行。

### 13.2 真实 GPU 冒烟测试

使用同一音色、同一组短句分别测试：

1. 无向量/中性；
2. 轻微高兴；
3. 轻微低落；
4. 克制或平静；
5. 高兴和低落的小幅混合。

不要一开始使用全强度单向量。先从总强度约 `0.2～0.5`、`alpha=0.6～0.8` 调试，确认音色没有明显漂移后再扩大范围。

每次检查：

- 是否能播放；
- 是否保持目标音色；
- 情绪差异是否可听；
- 是否出现爆音、断字、重复、长静音或尾部丢失；
- 采样率和声道是否正确；
- 推理耗时、音频时长和 RTF；
- 连续调用后的显存是否持续单调增长。

### 13.3 稳定性测试

- 连续 100 次短句合成，无进程崩溃、死锁和请求永久挂起；
- 两个及以上客户端并发请求，模型实际执行仍为单并发；
- 队列达到上限时快速返回 429；
- 中途停止客户端，不破坏后续请求；
- WebUI 停止后启动 API，显存足够且只加载一份模型；
- 服务重启后 readiness 从 503 正确转为 200；
- 错误请求不影响下一次正常推理。

### 13.4 阶段二流式测试

- 单段和多段文本都能播放；
- 拼接后的 PCM 顺序正确；
- 不重复插入静音；
- 最后一个语音段不丢失；
- 记录首包延迟；
- 客户端断开后最迟在下一个段边界停止；
- 流式完成后模型仍能处理下一请求。

## 14. 验收标准

### 14.1 阶段一验收

- [ ] API 进程启动时只加载一次 IndexTTS2.5；
- [ ] `/health/live`、`/health/ready`、`/v1/capabilities`、`/v1/voices` 正常；
- [ ] `/v1/tts` 可通过 `voice_id` 合成 PCM16、22050 Hz、单声道 WAV；
- [ ] 八维情绪顺序与官方定义一致；
- [ ] 情绪向量已校验并使用官方归一化；
- [ ] 中性、高兴、低落至少三组真实音频通过人工试听；
- [ ] 两个并发请求不会同时进入同一模型实例；
- [ ] 队列有上限，满载时返回明确错误；
- [ ] 连续 100 次请求无崩溃、死锁和持续显存泄漏；
- [ ] 所有自动测试通过；
- [ ] WebUI 原有功能未被破坏；
- [ ] README 已说明配置、启动、调用、停止和排障方式。

性能不设脱离硬件的绝对秒数门槛，但必须记录目标显卡上的冷启动耗时、warmup 后首包/总耗时、音频时长和 RTF。若 warmup 后 RTF 大于 1，需要列出当前加速配置和后续优化建议，不能用降低正确性来掩盖。

### 14.2 阶段二验收

- [ ] 能力接口明确标记 `segment` 流式；
- [ ] 裸 PCM 格式和响应头稳定；
- [ ] 多段合成无漏段、重复段和重复静音；
- [ ] 首包延迟相对非流式有实测收益；
- [ ] 客户端断开不会损坏模型状态；
- [ ] 无收益或不稳定时可通过配置关闭，不影响 `/v1/tts`。

## 15. 实施阶段与提交顺序

### 阶段 0：本地兼容性审计

产出：

- 本地 Git commit；
- 环境和 GPU 信息；
- `IndexTTS2` 初始化与推理签名；
- WebUI 可工作的参考音频、语言和模型参数；
- 当前一次正常合成的耗时、RTF 和显存基线。

### 阶段 1：稳定非流式服务

建议提交顺序：

1. 配置、Schema、错误码和音色注册表；
2. 音频内存编码与单元测试；
3. 模型 runtime、单并发队列和生命周期；
4. 健康、能力、音色和 `/v1/tts` 路由；
5. mock 自动测试；
6. GPU 冒烟、100 次稳定性测试和 README。

阶段一完成并验收后即可供 `xiaozhi-esp32-server` 接入，不必等待流式。

### 阶段 2：分段流式实验

实现 `/v1/tts/stream`，测量实际首包收益。只有通过完整性和稳定性测试后才在能力接口中启用。

### 阶段 3：部署加固

- systemd、Windows 计划任务或容器化三选一；
- 优雅关闭；
- 日志轮转；
- 局域网防火墙；
- 健康探针；
- 按目标硬件对 BF16、CUDA kernel、DeepSpeed、torch compile 做 A/B 测试。

### 阶段 4：可选优化

- WebUI 与 API 共用 runtime；
- 多音色缓存策略；
- vLLM 生产部署评估；
- 更细粒度流式的上游改造评估。

阶段四不是当前交付条件。

## 16. 部署与网络约束

按当前开发要求，API 不实现账号、Token 或授权流程。仍需满足以下部署约束：

- 默认只允许可信局域网访问；
- 通过操作系统防火墙限制来源 IP；
- 不直接暴露到公网；
- 不接受任意本地路径、远程 URL 或上传的参考音频；
- 请求正文设置大小限制；
- 配置合理的超时和队列上限；
- 服务仅以普通用户权限运行。

这些约束是为了防止误调用、路径读取和资源耗尽，不改变“开发阶段无授权机制”的产品决定。

## 17. 交付物

另一台电脑完成改造后，应交付：

1. API 服务源代码；
2. `api_config.example.yaml` 或去除机器路径后的示例配置；
3. 音色注册表示例；
4. 自动测试和测试结果；
5. 一组不含敏感参考音频的调用示例；
6. GPU 冒烟和 100 次稳定性测试摘要；
7. README 启动与排障说明；
8. 本地 commit 与相对官方上游的变更清单；
9. 与本文档契约不一致的地方及原因；
10. 供 `xiaozhi-esp32-server` 后续接入的基地址、`voice_id`、格式和能力信息。

## 18. 交付前禁止事项

- 不得只启动接口而未实际合成音频就宣称完成；
- 不得只测试 WebUI，不测试 API；
- 不得让请求体控制服务器磁盘路径；
- 不得默认开启多进程 Uvicorn worker；
- 不得用全局无限队列掩盖 GPU 吞吐不足；
- 不得在 async 路由中直接阻塞执行 GPU 推理；
- 不得把 Companion Core 情绪标签直接当作 IndexTTS 向量顺序；
- 不得宣称当前按段输出是真正的 token 级流式；
- 不得修改核心推理算法来解决服务层可以处理的问题；
- 不得在未跑一两个真实成功样例前交付。

## 19. 后续与 xiaozhi 项目的接口约定

IndexTTS2.5 电脑完成阶段一后，后续主项目只需实现一个新的 TTS provider：

```text
Companion Core 动态情绪状态
  -> 主项目统一情绪表示
  -> IndexTTS2.5 八维适配器
  -> POST /v1/tts
  -> 接收 WAV
  -> 主项目现有音频编码与设备播放链路
```

动态情绪开关应放在 `xiaozhi-esp32-server` 的角色/TTS 配置中，而不是 IndexTTS 服务里。关闭时主项目省略 `emotion`；开启时主项目发送八维向量。IndexTTS 服务始终只执行请求，不自行决定是否为某个角色启用动态情绪。

这样可同时保留：

- GPT-SoVITS V2：继续走其已有调用方式；
- IndexTTS2.5：使用本文件定义的标准 HTTP API 和八维情绪；
- 未来其他模型：各自实现统一情绪到模型原生能力的适配器，不强迫所有模型内部都使用八维向量。

---

## 20. 新窗口可直接使用的任务描述

```text
请先完整阅读《IndexTTS2.5 API 服务改造与动态情绪接入方案》，然后在当前 IndexTTS2.5 仓库实施阶段 0 和阶段 1。

约束：
1. 只修改当前 IndexTTS2.5 项目，不修改 xiaozhi-esp32-server 和设备端。
2. 保留现有 WebUI，不重写核心推理算法。
3. 先核对本地 commit、infer_v2_5.py 签名和工作区改动，再编码。
4. 模型单例、GPU 单并发、有界队列；请求不得传入任意参考音频路径或 URL。
5. 第一阶段提供 WAV 非流式接口和八维动态情绪，不启用 QwenEmotion。
6. 使用 apply_patch 编辑文件，保留无关用户改动。
7. 完成自动测试后，必须用真实显卡至少测试中性和两种不同情绪，再交付。
8. 交付时报告改动文件、启动命令、curl 示例、测试结果、性能数据和已知限制。

若本地源码与方案存在差异，以本地源码为事实依据，但保持文档定义的外部 API 契约，并明确记录兼容调整。
```
