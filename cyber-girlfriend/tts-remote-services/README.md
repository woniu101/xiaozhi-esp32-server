# 远端 TTS 服务管理

这组脚本用于 `192.168.18.14` 上的 Windows 整合包。实测 RTX 3080 机器同时常驻
IndexTTS2.5 与 GPT-SoVITS V2 时会发生系统内存分配失败，因此默认采用互斥切换。

部署到 `E:\xiaozhi-tts` 后执行：

```powershell
pwsh -File E:\xiaozhi-tts\switch-tts-engine.ps1 status
pwsh -File E:\xiaozhi-tts\switch-tts-engine.ps1 index
pwsh -File E:\xiaozhi-tts\switch-tts-engine.ps1 gpt
pwsh -File E:\xiaozhi-tts\switch-tts-engine.ps1 stop
```

只允许一个默认模型登录自启动：

```powershell
pwsh -File E:\xiaozhi-tts\install-autostart.ps1 -DefaultEngine index
pwsh -File E:\xiaozhi-tts\install-autostart.ps1 -Remove
```

`start-index-api.cmd` 与 `start-gpt-sovits-v2.cmd` 分别部署到两个整合包根目录，日志也写入各自根目录。
