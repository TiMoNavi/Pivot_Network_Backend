param(
  [string]$RollbackRoot = "D:\AI\Pivot_Client\seller_client\rollback",
  [switch]$SkipRollbackCapture,
  [switch]$RestartDockerDesktopProcesses,
  [switch]$ResetWsl,
  [int]$WaitTimeoutSeconds = 45,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$PSNativeCommandUseErrorActionPreference = $false

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$captureScript = Join-Path $ScriptDir "capture_repair_state.ps1"
. (Join-Path $ScriptDir "swarm_runtime_common.ps1")
$dockerDesktopExeCandidates = @(
  "C:\Program Files\Docker\Docker\Docker Desktop.exe",
  "C:\Program Files\Docker\Docker\Docker Desktop"
)
$linuxEnginePipe = "\\.\pipe\dockerDesktopLinuxEngine"
$dockerInfoTimeoutSeconds = 8
$dockerContextTimeoutSeconds = 6

function Capture-Text {
  param([scriptblock]$Command)
  try {
    return (& $Command 2>&1 | Out-String).Trim()
  } catch {
    return ($_ | Out-String).Trim()
  }
}

function Get-DockerDesktopExe {
  foreach ($candidate in $dockerDesktopExeCandidates) {
    if (Test-Path $candidate) {
      return $candidate
    }
  }
  return $null
}

function Get-DockerInfoState {
  $result = Invoke-DockerCliCapture -Arguments @("info", "--format", "{{json .Swarm}}") -TimeoutSeconds $dockerInfoTimeoutSeconds
  $healthy = (-not $result.timed_out) -and ($result.exit_code -eq 0) -and $result.output.StartsWith("{")
  [PSCustomObject]@{
    healthy = $healthy
    output = $result.output
    exit_code = $result.exit_code
    timed_out = $result.timed_out
  }
}

function Get-EngineState {
  $dockerInfoState = Get-DockerInfoState
  $dockerContexts = Invoke-DockerCliCapture -Arguments @("context", "ls", "--format", "{{json .}}") -TimeoutSeconds $dockerContextTimeoutSeconds
  [PSCustomObject]@{
    service = Get-Service -Name com.docker.service -ErrorAction SilentlyContinue | Select-Object Name, Status, StartType
    pipe_exists = Test-Path $linuxEnginePipe
    docker_contexts = $dockerContexts
    docker_info = $dockerInfoState
    processes = Get-Process -Name "Docker Desktop", "com.docker.backend", "com.docker.proxy" -ErrorAction SilentlyContinue |
      Select-Object Name, Id, StartTime
  }
}

function Try-StartDockerService {
  try {
    Start-Service -Name com.docker.service -ErrorAction Stop
    return [PSCustomObject]@{
      attempted = $true
      started = $true
      error = $null
    }
  } catch {
    return [PSCustomObject]@{
      attempted = $true
      started = $false
      error = $_.Exception.Message
    }
  }
}

$rollbackOutput = $null
if (-not $SkipRollbackCapture -and (Test-Path $captureScript)) {
  try {
    $rollbackJson = & $captureScript -OutputRoot $RollbackRoot -HostTunnelName "wg-seller"
    $rollbackOutput = ($rollbackJson | Out-String).Trim()
  } catch {
    $rollbackOutput = "rollback_capture_failed: $($_.Exception.Message)"
  }
}

$dockerDesktopExe = Get-DockerDesktopExe
$beforeState = Get-EngineState
$serviceStart = $null
$currentState = $beforeState

if ($DryRun) {
  [PSCustomObject]@{
    docker_desktop_exe = $dockerDesktopExe
    rollback_capture = $rollbackOutput
    restart_docker_desktop_processes = [bool]$RestartDockerDesktopProcesses
    reset_wsl = [bool]$ResetWsl
    before_state = $beforeState
  } | ConvertTo-Json -Depth 7
  exit 0
}

$actions = @()

if ($null -ne $beforeState.service -and $beforeState.service.Status -ne "Running") {
  $serviceStart = Try-StartDockerService
  if ($serviceStart.started) {
    $actions += "start-service:com.docker.service"
  } else {
    $actions += "start-service-failed:com.docker.service"
  }
}

if ($ResetWsl) {
  wsl.exe --shutdown | Out-Null
  $actions += "wsl-shutdown"
  Start-Sleep -Seconds 3
}

if ($RestartDockerDesktopProcesses) {
  Get-Process -Name "Docker Desktop", "com.docker.backend", "com.docker.proxy" -ErrorAction SilentlyContinue |
    Stop-Process -Force -ErrorAction SilentlyContinue
  $actions += "stop-docker-desktop-processes"
  Start-Sleep -Seconds 2
}

if ($dockerDesktopExe) {
  Start-Process -FilePath $dockerDesktopExe | Out-Null
  $actions += "start-docker-desktop-exe"
}

$deadline = (Get-Date).AddSeconds($WaitTimeoutSeconds)
do {
  $currentState = Get-EngineState
  if ($currentState.pipe_exists -and $currentState.docker_info.healthy) {
    break
  }
  Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)

$recovered = [bool]($currentState.pipe_exists -and $currentState.docker_info.healthy)

[PSCustomObject]@{
  docker_desktop_exe = $dockerDesktopExe
  rollback_capture = $rollbackOutput
  actions = $actions
  service_start = $serviceStart
  before_state = $beforeState
  after_state = $currentState
  recovered = $recovered
} | ConvertTo-Json -Depth 7

if (-not $recovered) {
  exit 1
}
