param(
    [string]$StateDir,
    [switch]$Apply,
    [string]$LogPath = ""
)

$ErrorActionPreference = "Stop"

if (-not $LogPath) {
    $LogDir = "D:\AI\Pivot_backend_build_team\.cache\installer"
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    $LogPath = Join-Path $LogDir "install_windows.log"
}

function Test-IsAdmin {
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source

if (-not $pythonExe) {
    Write-Error "Python is required to run the seller client installer skeleton."
}

if ($Apply -and -not (Test-IsAdmin)) {
    $argList = @(
        '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f $MyInvocation.MyCommand.Path)
    )
    if ($StateDir) {
        $argList += @('-StateDir', ('"{0}"' -f $StateDir))
    }
    $argList += @('-LogPath', ('"{0}"' -f $LogPath))
    $argList += '-Apply'
    $elevated = Start-Process powershell -Verb RunAs -ArgumentList $argList -PassThru -Wait
    Write-Output "Installer requested elevation and has finished. Review log: $LogPath"
    if (Test-Path $LogPath) {
        Write-Output "--- installer log tail ---"
        Get-Content -Tail 80 $LogPath
    }
    exit 0
}

Start-Transcript -Path $LogPath -Append | Out-Null

$installerArgs = @()
if ($StateDir) {
    $installerArgs += @('--state-dir', $StateDir)
}
if ($Apply) {
    $installerArgs += '--apply'
}

Write-Output "Running seller client installer skeleton (Windows)..."
try {
    & $pythonExe "$scriptDir\installer.py" @installerArgs
}
finally {
    Stop-Transcript | Out-Null
}
