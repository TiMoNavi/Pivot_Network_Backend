param(
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$SharedRoot = Split-Path -Parent $ProjectRoot
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$CodexConfigTemplatePath = Join-Path $SharedRoot "env_setup_and_install\codex.config.toml"
$Port = if ($env:SELLER_CLIENT_APP_PORT) { $env:SELLER_CLIENT_APP_PORT } else { "8901" }
$BackendBaseUrl = if ($env:SELLER_CLIENT_BACKEND_BASE_URL) { $env:SELLER_CLIENT_BACKEND_BASE_URL } else { "https://pivotcompute.store" }

if ($DryRun) {
  [PSCustomObject]@{
    bootstrap_script = $MyInvocation.MyCommand.Path
    project_root = $ProjectRoot
    shared_root = $SharedRoot
    venv_dir = $VenvDir
    venv_exists = (Test-Path $VenvDir)
    venv_python = $VenvPython
    venv_python_exists = (Test-Path $VenvPython)
    codex_config_template_path = $CodexConfigTemplatePath
    codex_config_template_exists = (Test-Path $CodexConfigTemplatePath)
    port = $Port
    backend_base_url = $BackendBaseUrl
  } | ConvertTo-Json -Depth 3
  exit 0
}

if (-not (Test-Path $VenvPython)) {
  throw "Seller client virtual environment is missing. Run bootstrap/windows/install_and_check_seller_client.ps1 first."
}

if (Test-Path $CodexConfigTemplatePath) {
  $env:SELLER_CLIENT_CODEX_CONFIG_TEMPLATE_PATH = $CodexConfigTemplatePath
}

$Listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($Listeners) {
  $owners = ($Listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
  throw "Port $Port is already in use by process id(s): $owners. Stop the existing listener before starting the seller client."
}

$Command = "set SELLER_CLIENT_BACKEND_BASE_URL=$BackendBaseUrl&& set SELLER_CLIENT_CODEX_CONFIG_TEMPLATE_PATH=$CodexConfigTemplatePath&& cd /d `"$ProjectRoot`" && `"$VenvPython`" -m uvicorn seller_client_app.main:app --host 127.0.0.1 --port $Port"
Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $Command -WorkingDirectory $ProjectRoot

Start-Sleep -Seconds 2
try {
  Start-Process "http://127.0.0.1:$Port/"
} catch {
  Write-Warning "Browser launch skipped: $($_.Exception.Message)"
}

Write-Output "Pivot Seller Client started on http://127.0.0.1:$Port/"
