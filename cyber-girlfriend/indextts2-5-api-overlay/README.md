# IndexTTS2.5 整合包 API 覆盖层

本目录保存已部署到 Windows 整合包 `E:\IndexTTS-2.5` 的 API 层源码，避免远端改造只存在于单台机器。

部署时将 `index_api/` 中的文件覆盖到整合包同名目录。`runtime.py` 等模型加载文件继续使用整合包现有版本。本覆盖层新增：

- 音色列表：`GET /v1/voices`
- 上传或更新音色：`POST /v1/voices`
- 删除非默认音色：`DELETE /v1/voices/{voice_id}`
- 原有非流式、分段流式合成和八维情绪接口

音色注册请求使用 JSON 和 Base64 WAV，单文件默认上限 20MB。音色清单写入 `voices/voices.json`，上传的音频写入 `reference/{voice_id}.wav`。开发阶段接口未增加鉴权，不应直接暴露到公网。
