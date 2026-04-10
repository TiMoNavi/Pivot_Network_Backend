param(
  [string]$ExpectedWireGuardIp = "10.66.66.10",
  [int]$OverlaySampleCount = 3,
  [int]$OverlayIntervalSeconds = 1,
  [switch]$SkipRepair,
  [switch]$PrintJson,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$SharedRoot = Split-Path -Parent $ProjectRoot
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$BootstrapHealthReport = Join-Path (Join-Path $ProjectRoot "health") "latest-health-report.json"
$CodexConfigTemplatePath = Join-Path $SharedRoot "env_setup_and_install\codex.config.toml"

function Resolve-Python {
  if (Test-Path $VenvPython) {
    return $VenvPython
  }
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {
    return $python.Source
  }
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    return $py.Source
  }
  throw "Python 3.11+ not found on PATH."
}

if ($DryRun) {
  [PSCustomObject]@{
    bootstrap_script = $MyInvocation.MyCommand.Path
    project_root = $ProjectRoot
    venv_dir = $VenvDir
    venv_python = $VenvPython
    venv_exists = (Test-Path $VenvPython)
    codex_config_template_path = $CodexConfigTemplatePath
    codex_config_template_exists = (Test-Path $CodexConfigTemplatePath)
    bootstrap_health_report = $BootstrapHealthReport
    expected_wireguard_ip = $ExpectedWireGuardIp
    repair_enabled = (-not $SkipRepair)
  } | ConvertTo-Json -Depth 4
  exit 0
}

$BootstrapPython = Resolve-Python

if (-not (Test-Path $VenvPython)) {
  & $BootstrapPython -m venv $VenvDir
}

& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -e $ProjectRoot

if (Test-Path $CodexConfigTemplatePath) {
  $env:SELLER_CLIENT_CODEX_CONFIG_TEMPLATE_PATH = $CodexConfigTemplatePath
}

$arguments = @(
  "-m", "seller_client_app.local_system",
  "--expected-wireguard-ip", $ExpectedWireGuardIp,
  "--overlay-sample-count", [string]$OverlaySampleCount,
  "--overlay-interval-seconds", [string]$OverlayIntervalSeconds
)
if (-not $SkipRepair) {
  $arguments += "--repair"
}

$jsonText = (& $VenvPython @arguments | Out-String).Trim()
if (-not $jsonText) {
  throw "seller_client_app.local_system produced no output."
}
$payload = $jsonText | ConvertFrom-Json

if ($PrintJson) {
  $payload | ConvertTo-Json -Depth 12
  exit 0
}

Write-Host ""
Write-Host "Pivot Seller Client install/check summary" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot"
Write-Host "Health report: $BootstrapHealthReport"
Write-Host "Overall status: $($payload.summary.status)"
Write-Host ""
Write-Host "Sections:" -ForegroundColor Cyan
Write-Host "  system                $($payload.system.status)"
Write-Host "  python_runtime        $($payload.python_runtime.status)"
Write-Host "  codex                 $($payload.codex.status)"
Write-Host "  wsl                   $($payload.wsl.status)"
Write-Host "  wireguard             $($payload.wireguard.status)"
Write-Host "  docker                $($payload.docker.status)"
Write-Host "  backend_connectivity  $($payload.backend_connectivity.status)"
Write-Host "  seller_client_runtime $($payload.seller_client_runtime.status)"

if ($payload.summary.warnings.Count -gt 0) {
  Write-Host ""
  Write-Host "Warnings:" -ForegroundColor Yellow
  foreach ($warning in $payload.summary.warnings) {
    Write-Host "  - $warning"
  }
}

if ($payload.repair_actions.Count -gt 0) {
  Write-Host ""
  Write-Host "Applied actions:" -ForegroundColor Cyan
  foreach ($action in $payload.repair_actions) {
    Write-Host "  - $action"
  }
}

Write-Host ""
Write-Host "Next step:" -ForegroundColor Cyan
Write-Host "  Run bootstrap/windows/start_seller_client.ps1 after the warnings are acceptable."
