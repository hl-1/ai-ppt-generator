[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path $PSScriptRoot).Path
Set-Location $Root

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "找不到 $Name，请先安装并加入 PATH。"
    }
}

function Stop-Tree([int]$ProcessId) {
    if ($ProcessId -gt 0 -and $ProcessId -ne $PID) {
        & taskkill.exe /PID $ProcessId /T /F *> $null
    }
}

function Stop-Port([int]$Port) {
    Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Tree $_.OwningProcess }
}

function Wait-Port([int]$Port, [int]$Timeout = 60) {
    $end = (Get-Date).AddSeconds($Timeout)
    do {
        if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
            return
        }
        Start-Sleep 1
    } while ((Get-Date) -lt $end)
    throw "端口 $Port 未启动，请检查服务窗口。"
}

Require-Command "make.exe"
Require-Command "docker.exe"
Require-Command "uv.exe"
Require-Command "npm.cmd"

Write-Host "[1/4] 关闭本项目旧服务..."
$patterns = "uvicorn app.main:app", "arq app.worker.settings.WorkerSettings", "vite"
Get-CimInstance Win32_Process |
    Where-Object {
        $commandLine = $_.CommandLine
        $_.ProcessId -ne $PID -and
        $commandLine -and
        ($patterns | Where-Object { $commandLine -like "*$_*" })
    } |
    ForEach-Object { Stop-Tree $_.ProcessId }
Stop-Port 39800
Stop-Port 39173

Write-Host "[2/4] 启动 PostgreSQL 和 Redis..."
& docker.exe compose up -d
if ($LASTEXITCODE -ne 0) { throw "Docker 基础设施启动失败。" }
Wait-Port 39432
Wait-Port 39379

Write-Host "[3/4] 执行数据库迁移..."
& make.exe migrate
if ($LASTEXITCODE -ne 0) { throw "数据库迁移失败。" }

Write-Host "[4/4] 打开 API、Worker、Web 服务窗口..."
$windowsPowerShell = (Get-Command pwsh.exe -ErrorAction SilentlyContinue).Source
if (-not $windowsPowerShell) { $windowsPowerShell = (Get-Command powershell.exe).Source }

foreach ($item in @(
    @("AI PPT API", "dev-api"),
    @("AI PPT Worker", "dev-worker"),
    @("AI PPT Web", "dev-web")
)) {
    $title = $item[0]
    $target = $item[1]
    $command = "`$Host.UI.RawUI.WindowTitle='$title'; Set-Location -LiteralPath '$Root'; & make.exe $target; Read-Host '服务已退出，按回车关闭窗口'"
    $encodedCommand = [Convert]::ToBase64String(
        [Text.Encoding]::Unicode.GetBytes($command)
    )
    Start-Process $windowsPowerShell -WorkingDirectory $Root -ArgumentList @(
        "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encodedCommand
    ) | Out-Null
}

Wait-Port 39800
Wait-Port 39173
Write-Host ""
Write-Host "项目已启动：" -ForegroundColor Green
Write-Host "前端: http://127.0.0.1:39173"
Write-Host "API:  http://127.0.0.1:39800"
