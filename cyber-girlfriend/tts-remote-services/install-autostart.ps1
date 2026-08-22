[CmdletBinding()]
param(
    [ValidateSet("index", "gpt")]
    [string]$DefaultEngine = "index",
    [switch]$Remove
)

$taskName = "Xiaozhi-Companion-TTS"
if ($Remove) {
    & schtasks.exe /Delete /TN $taskName /F
    exit $LASTEXITCODE
}

$switchScript = "E:\xiaozhi-tts\switch-tts-engine.ps1"
$taskCommand = "pwsh.exe -NoProfile -ExecutionPolicy Bypass -File `"$switchScript`" $DefaultEngine"
& schtasks.exe /Create /SC ONLOGON /TN $taskName /TR $taskCommand /RL LIMITED /F
exit $LASTEXITCODE
