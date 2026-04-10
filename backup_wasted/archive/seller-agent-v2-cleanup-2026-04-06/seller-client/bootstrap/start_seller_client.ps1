$ErrorActionPreference = "Stop"

$LegacyScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $LegacyScriptDir
$NewScript = Join-Path $ProjectRoot "bootstrap\windows\start_seller_console.ps1"

if (Test-Path $NewScript) {
  & $NewScript
  exit $LASTEXITCODE
}

$ScriptDir = $LegacyScriptDir
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$RuntimePython = Join-Path $ProjectRoot ".runtime\python\python.exe"

function Resolve-Python {
  if (Test-Path $VenvPython) {
    return $VenvPython
  }
  if (Test-Path $RuntimePython) {
    return $RuntimePython
  }
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    return $python.Source
  }
  throw "Python 3.11+ not found. Install Python or place a runtime at .runtime\python\python.exe"
}

$PythonExe = Resolve-Python

if (-not (Test-Path $VenvPython)) {
  & $PythonExe -m venv (Join-Path $ProjectRoot ".venv")
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -e $ProjectRoot

$Port = if ($env:SELLER_CLIENT_APP_PORT) { $env:SELLER_CLIENT_APP_PORT } else { "8901" }
$BackendBaseUrl = if ($env:SELLER_CLIENT_BACKEND_BASE_URL) { $env:SELLER_CLIENT_BACKEND_BASE_URL } else { "https://pivotcompute.store" }

$Listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
foreach ($Listener in $Listeners) {
  Stop-Process -Id $Listener.OwningProcess -Force -ErrorAction SilentlyContinue
}

Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "set SELLER_CLIENT_BACKEND_BASE_URL=$BackendBaseUrl&& cd /d `"$ProjectRoot`" && `"$VenvPython`" -m uvicorn seller_client_app.main:app --host 127.0.0.1 --port $Port" -WorkingDirectory $ProjectRoot
Start-Sleep -Seconds 2
try {
  Start-Process "http://127.0.0.1:$Port/"
} catch {
  Write-Warning "Browser launch skipped: $($_.Exception.Message)"
}
