# dot-skill 人物风格与 IndexTTS2.5 MVP 使用指南

本功能用于验证三条最小链路：原样导入 dot-skill 人物风格、使用独立 IndexTTS2.5 服务合成普通语音，以及在 LLM 自然输出招牌表达时替换为固定录音。

它依赖智控台、Manager API、MySQL 和 xiaozhi-server，因此必须使用全模块部署。单独运行 `xiaozhi-server` 时可以手写 IndexTTS2.5 配置，但不能使用人物风格导入、绑定和招牌录音管理。

## 1. 部署要求

源码镜像构建会自动包含以下内容：

- Liquibase 数据库变更：`ai_character_style`、`ai_agent.character_style_id`、IndexTTS2.5 Provider 和默认音色。
- xiaozhi-server 的人物提示词、招牌路由和 IndexTTS2.5 Provider。
- 智控台的轻量人物风格管理弹窗、IndexTTS2.5 连接测试和远端音色管理。

全模块 Docker Compose 已将同一个目录挂载到两个容器：

```text
宿主机 ./main/xiaozhi-server/data/character_styles
  ├─ xiaozhi-server: /opt/xiaozhi-esp32-server/data/character_styles
  └─ manager-web/api: /opt/xiaozhi-esp32-server/data/character_styles
```

人物源码快照和招牌录音必须共享该目录。若是源码部署或自定义容器，给 Manager API 设置：

```bash
CHARACTER_STYLE_DIR=/absolute/path/to/xiaozhi-server/data/character_styles
```

同时确保 xiaozhi-server 的 `character_style_data_dir` 指向包含 `character_styles` 的同一 `data` 目录；该配置与日志目录解耦。源码分进程运行且 manager-api 使用默认 `/opt` 存储时，可配置为：

```yaml
character_style_data_dir: /opt/xiaozhi-esp32-server/data
```

也可以让两个进程统一设置 `CHARACTER_STYLE_DIR=/共享路径/character_styles`；xiaozhi-server 会自动使用其父目录作为 data 根目录。本地文件路径会在合并 manager-api 服务配置时保留，不由远端配置覆盖。

不要在数据库中填写本机或 Windows 绝对音频路径。

从仓库根目录构建并启动全模块：

```bash
docker build -f Dockerfile-server -t xiaozhi-server:mvp .
docker build -f Dockerfile-web -t xiaozhi-web:mvp .
cd main/xiaozhi-server
docker compose -f docker-compose_all.yml up -d
```

若使用自定义镜像名，需要同步修改 `docker-compose_all.yml` 的 `image`。Manager API 启动时会自动执行数据库变更；不要手工重复执行同一 Liquibase 变更。

## 2. IndexTTS2.5 远端契约

独立显卡电脑上的服务应提供：

```text
GET  /health/ready
POST /v1/tts
POST /v1/tts/stream
GET  /v1/voices
POST /v1/voices
DELETE /v1/voices/{voice_id}
```

普通接口返回 WAV；流式接口返回单声道有符号 16 位 PCM，并建议返回：

```text
X-Audio-Format: pcm_s16le_mono
X-Sample-Rate: 24000
```

可以先在 xiaozhi-server 所在机器验证远端：

```bash
curl -fsS http://INDEXTTS_HOST:8092/health/ready

curl -fsS http://INDEXTTS_HOST:8092/v1/tts \
  -H 'Content-Type: application/json' \
  -H 'Accept: audio/wav' \
  --data '{"request_id":"manual-test","text":"你好，这是连接测试。","voice_id":"tuniang-normal","lang":"zh","speed":1.0,"text_normalization":true}' \
  --output /tmp/index-test.wav

curl -fsS -D - http://INDEXTTS_HOST:8092/v1/tts/stream \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/octet-stream' \
  --data '{"request_id":"manual-stream-test","text":"你好，这是流式测试。","voice_id":"tuniang-normal","lang":"zh","speed":1.0,"text_normalization":true}' \
  --output /tmp/index-test.pcm
```

Docker 中的 `127.0.0.1` 指向 xiaozhi-server 容器自身。远端 Index 服务运行在另一台电脑时，应填写那台电脑可从容器访问的局域网 IP 或域名。

## 3. 智控台配置

### 3.1 配置 IndexTTS2.5

使用超级管理员进入“模型配置 → TTS”，编辑或新增 IndexTTS2.5。页面只显示：

- API 服务地址，例如 `http://INDEXTTS_HOST:8092`。
- 音色 ID，例如 `tuniang-normal`。
- 语言，例如 `zh`。
- 语速，范围 `0.5`～`2.0`。
- 请求超时秒数，MVP 默认 `60` 秒。
- 是否启用流式合成；该开关位于连接诊断上方的独立全宽设置卡。

点击“测试连接”会使用当前表单值分别检测健康检查、普通 WAV 和流式接口，不会保存配置。测试请求不携带 `emotion`、人物名、关系或用户状态。

测试通过后保存模型，在智能体的角色配置页选择该 TTS 和音色。配置变更在设备重连后生效。

运行时不跟随 HTTP 重定向，并限制普通 WAV 为 32 MiB、单个流式分段为 64 MiB；空流、奇数字节 PCM、截断 WAV 和超限响应都会明确失败。只有流式分段尚未向设备输出任何音频包时，才会改用同一 Index 服务的普通 WAV 接口。

### 3.2 管理 IndexTTS2.5 音色

在 IndexTTS2.5 模型的“音色管理”中：

1. 点击“刷新状态”读取远端音色。
2. 点击“同步远端音色”，将远端 Voice ID 同步到本地音色目录，供角色配置选择。
3. 点击“上传并注册音色”，填写 Voice ID、名称、语言和可选的参考音频文本，上传 WAV。
4. 注册成功后会自动同步；点击列表中的“试听”会请求 `/v1/tts` 并在浏览器播放返回的 WAV。

上传限制为 WAV、最大 20 MB；Voice ID 最长 80 个字符，只允许字母、数字、点、下划线和连字符。默认音色不允许删除；仍被角色或角色模板引用的音色也不允许删除。这里只做参考音频注册，不在 MVP 服务器上执行训练。

### 3.3 导入并绑定 dot-skill

进入“智能体管理 → 配置角色 → 人物风格 → 管理人物风格”：

1. 先明确选择“导入新人物”或“更新已有人物”，两种模式互斥。
2. 更新模式会要求先选择目标，并在提交前二次确认；导入模式不会改动已有人物。
3. 选择 GitHub 或 ZIP，填写人物名称和来源。版本可留空使用默认分支，也可填分支、标签或 Commit。
4. 在人物详情检查原始 `SKILL.md`、最终提示词、纳入文件、诊断和 SHA-256 哈希。
5. 点击绑定。

ZIP 必须包含 `SKILL.md`。人物相关引用应由 `SKILL.md` 通过 Markdown 链接或反引号路径明确引用；明确 Markdown 文件链接缺失时拒绝导入，目录导航链接会安全跳过，反引号中的文件名只在包内唯一匹配时纳入。未引用资料保留在安全源码快照中，但不会静默加入提示词。导入器只去除开头 frontmatter，不总结、不翻译、不润色、不截断人物正文和对话示例。

绑定后：

- dot-skill 的最终提示词是唯一人物身份和说话风格。
- 原“角色介绍”仍保存在数据库和页面中，但只读且运行时不注入。
- 原角色模板不可应用；昵称、模型、工具、语言、Memory 和 TTS 仍可配置。
- 解除绑定后原角色介绍自动恢复生效。

这只是可复用的轻量人物列表，不与完整版仓库同步，也没有 draft/published、版本回滚、关系成长、动态情绪或 PersonaSpec。

### 3.4 固定招牌录音（可选增强）

固定录音不是人物行为的触发器，也不是导入或绑定的必填项。一个人物可以保持零条录音映射；Skill 仍决定什么语境适合说招牌句，主 LLM 根据当前上下文决定是否自然输出，录音路由只替换模型已经输出的对应片段。

在人物详情的“招牌语音”页签：

1. 选择所属人物，先阅读页面上的三步触发链路。
2. 可点击“从 Skill 生成建议”；建议必须带原文证据，默认关闭并等待人工确认。
3. 填写“录音对应台词”，确保与 WAV 实际内容一致；“模型输出的等价写法”只填写全半角、大小写或标点变体，不得填写“想听那个了”等用户话术。
4. 按需开启人物级总开关和单条录音，保存后上传 WAV。
5. 在“上下文试跑”中输入用户话语，查看主 LLM 实际输出以及固定录音/当前 TTS 的路由结果。试跑没有历史和工具，不保存为真实对话。

上传限制：WAV、最大 5 MB、时长 0.2～15 秒。服务端会解码、混单声道、重采样并保存为 24 kHz/16-bit/mono PCM WAV。

只有“人物总开关开启 + 单条开关开启 + 有效录音存在”同时满足时才播放固定录音。运行时规范台词契约只在 Skill 与上下文本来已经决定使用时约束输出写法，录音可用本身不得提高使用频率。未配置、关闭、未上传、文件缺失、损坏或播放瞬间读取失败时，原文字均交给当前选中的 TTS，不会静音。LLM 原始完整文字继续用于字幕、日志和对话历史。

## 4. 验收建议

截至 2026-08-26 已完成的真实服务验证：

- 本项目 IndexTTS2.5 Provider 已实际调用局域网独立服务：健康检查 ready；非流式返回 22.05 kHz、单声道、16-bit WAV；流式转换为 16 kHz 设备 PCM 后产生 70 个音频包。
- `woniu101/tu-niang-skill` 当前公开 ZIP 已用 Manager API 解析器实测通过：最终提示词 84,459 字符，完整纳入 11 份明确引用资料，不重复拼接入口文件。

至少验证以下场景：

- 未绑定人物时，原角色介绍正常生效。
- 绑定后最终提示词能逐段定位 `SKILL.md` 原文、章节、边界、示例和引用资料。
- 解除绑定后，原角色介绍恢复。
- Index 普通与流式合成均能播放并可打断；流式首包前失败回退普通 WAV，出包后失败不整句重播。
- 招牌表达位于句首、句中、句尾和跨 LLM chunk 时均能匹配。
- 同一表达在一次顶层用户轮次及其工具调用前后最多播放一次。
- 关闭任一开关、删除或损坏录音后，使用 EdgeTTS 和 IndexTTS2.5 分别验证当前 TTS 回退。
- 对 10～20 个固定对话场景人工比较原 Skill 的称呼、节奏、幽默、边界和招牌表达时机。

仓库内自动回归命令：

```bash
cd main/xiaozhi-server
python -m compileall -q core tests
python -m unittest tests.test_index_tts_v2_5 tests.test_character_style_prompt tests.test_signature_router tests.test_tts_file_fallback

cd ../manager-web
npm run test:unit
npm run test:snapshot
npm run check:i18n
npm run build

cd ../manager-api
mvn -DskipTests=false -Dtest=CharacterStyleArchiveParserTest,GitHubSourceDownloaderTest,SignatureAudioNormalizerTest,CharacterStyleServiceImplTest,ConfigServiceImplTest,IndexTtsConnectionTesterTest,TimbreServiceImplTest test
mvn package -DskipTests
```

自动测试覆盖导入安全、正文保真、运行时互斥、路由匹配、音频回退、原子文件回滚、Index 请求契约和音色管理边界。远端非流式与流式基本调用已实机通过；设备播放、重连、网络中断注入和人物风格表现仍必须人工验收。
