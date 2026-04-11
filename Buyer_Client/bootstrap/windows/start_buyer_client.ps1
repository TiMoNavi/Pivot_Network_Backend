$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BootstrapDir = Split-Path -Parent $ScriptDir
$ProjectRoot = Split-Path -Parent $BootstrapDir
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

function Resolve-Python {
  if (Test-Path $VenvPython) {
    return $VenvPython
  }
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    return $python.Source
  }
  throw "Python 3.11+ not found. Install Python first."
}

$PythonExe = Resolve-Python
if (-not (Test-Path $VenvPython)) {
  & $PythonExe -m venv (Join-Path $ProjectRoot ".venv")
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -e $ProjectRoot

$Port = if ($env:BUYER_CLIENT_APP_PORT) { $env:BUYER_CLIENT_APP_PORT } else { "8902" }
$BackendBaseUrl = if ($env:BUYER_CLIENT_BACKEND_BASE_URL) { $env:BUYER_CLIENT_BACKEND_BASE_URL } else { "https://pivotcompute.store" }
$WorkspaceRoot = if ($env:BUYER_CLIENT_WINDOWS_WORKSPACE_ROOT) { $env:BUYER_CLIENT_WINDOWS_WORKSPACE_ROOT } else { "D:\AI\Pivot_Client\buyer_client" }

$Listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
foreach ($Listener in $Listeners) {
  Stop-Process -Id $Listener.OwningProcess -Force -ErrorAction SilentlyContinue
}

$Command = "set BUYER_CLIENT_BACKEND_BASE_URL=$BackendBaseUrl&& set BUYER_CLIENT_WINDOWS_WORKSPACE_ROOT=$WorkspaceRoot&& cd /d `"$ProjectRoot`" && `"$VenvPython`" -m uvicorn buyer_client_app.main:app --host 127.0.0.1 --port $Port"
Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $Command -WorkingDirectory $ProjectRoot
Start-Sleep -Seconds 2
try {
  Start-Process "http://127.0.0.1:$Port/"
} catch {
  Write-Warning "Browser launch skipped: $($_.Exception.Message)"
}
