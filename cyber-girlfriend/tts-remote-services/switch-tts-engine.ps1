[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("index", "gpt", "stop", "status")]
    [string]$Engine = "status"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$engines = @{
    index = @{
        Pattern = "*uvicorn index_api.app:app*"
        Start = 'cmd.exe /d /c "E:\IndexTTS-2.5\start-index-api.cmd"'
        Health = "http://192.168.18.14:8092/health/ready"
    }
    gpt = @{
        Pattern = "*GPT-SoVITS-v2pro-20250604*api_v2.py*"
        Start = 'cmd.exe /d /c "E:\GPT-SoVITS-v2pro-20250604\start-gpt-sovits-v2.cmd"'
        Health = "http://192.168.18.14:9880/openapi.json"
    }
}

function Get-EngineProcesses([string]$Name) {
    $pattern = $engines[$Name].Pattern
    @(Get-CimInstance Win32_Process | Where-Object {
        $_.ProcessId -ne $PID -and
        $_.Name -eq "python.exe" -and
        $_.CommandLine -like $pattern
    })
}

function Stop-Engine([string]$Name) {
    foreach ($process in (Get-EngineProcesses $Name)) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Output "stopped $Name pid=$($process.ProcessId)"
    }
}

function Start-Engine([string]$Name) {
    if (@(Get-EngineProcesses $Name).Count -gt 0) {
        Write-Output "$Name already running"
        return
    }
    $result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
        CommandLine = $engines[$Name].Start
    }
    if ($result.ReturnValue -ne 0) {
        throw "failed to start $Name, WMI return value=$($result.ReturnValue)"
    }
    Write-Output "starting $Name wrapper pid=$($result.ProcessId)"

    for ($attempt = 1; $attempt -le 30; $attempt++) {
        & curl.exe --silent --fail --max-time 2 $engines[$Name].Health | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Output "$Name ready"
            return
        }
        Start-Sleep -Milliseconds 1500
    }
    throw "$Name did not become ready within 45 seconds"
}

if ($Engine -eq "status") {
    foreach ($name in @("index", "gpt")) {
        $processes = @(Get-EngineProcesses $name)
        $ids = (($processes | ForEach-Object { $_.ProcessId }) -join ",")
        Write-Output "$name running=$($processes.Count -gt 0) pids=$ids"
    }
    exit 0
}

if ($Engine -eq "stop") {
    Stop-Engine "index"
    Stop-Engine "gpt"
    exit 0
}

# RTX 3080 机器上的两个整合包不能稳定同时常驻。切换前先释放另一套模型。
$other = if ($Engine -eq "index") { "gpt" } else { "index" }
Stop-Engine $other
Start-Sleep -Seconds 2
Start-Engine $Engine
