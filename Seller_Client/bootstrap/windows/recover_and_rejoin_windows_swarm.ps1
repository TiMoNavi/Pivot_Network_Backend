param(
  [string]$SessionFilePath = $env:SELLER_CLIENT_SESSION_FILE,
  [ValidateSet("wireguard", "public")]
  [string]$JoinMode = "wireguard",
  [string]$ManagerWireGuardAddress = "10.66.66.1",
  [string]$AdvertiseAddress = "10.66.66.10",
  [string]$DataPathAddress = "10.66.66.10",
  [string]$ListenAddress = "10.66.66.10:2377",
  [switch]$RecoverDockerDesktop,
  [switch]$RecoverResetWsl,
  [switch]$RecoverRestartDockerDesktopProcesses,
  [int]$RecoverWaitTimeoutSeconds = 60,
  [int]$LeaveTimeoutSeconds = 25,
  [int]$PostJoinProbeCount = 12,
  [int]$ProbeIntervalSeconds = 2,
  [int]$ManagerProbeCount = 6,
  [int]$ManagerProbeIntervalSeconds = 3,
  [switch]$RemoveStaleDownNodes,
  [int]$MinimumTcpValidationPort = 8080,
  [switch]$SkipBackendAuthoritativeCorrection,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$PSNativeCommandUseErrorActionPreference = $false

if (-not $SessionFilePath) {
  throw "Session file is required. Pass -SessionFilePath or set SELLER_CLIENT_SESSION_FILE."
}
if (-not (Test-Path $SessionFilePath)) {
  throw "Session file not found: $SessionFilePath"
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$recoverScript = Join-Path $ScriptDir "recover_docker_desktop_engine.ps1"
$cycleScript = Join-Path $ScriptDir "attempt_manager_addr_correction_cycle.ps1"
. (Join-Path $ScriptDir "swarm_runtime_common.ps1")
$dockerCli = Get-DockerCliPath

function Capture-Text {
  param([scriptblock]$Command)
  try {
    return (& $Command 2>&1 | Out-String).Trim()
  } catch {
    return ($_ | Out-String).Trim()
  }
}

function Parse-JsonText {
  param([string]$Text)

  if (-not $Text) {
    return $null
  }

  $trimmed = $Text.Trim()
  $trimmed = $trimmed -replace "`0", ""
  $candidates = New-Object System.Collections.Generic.List[string]
  $candidates.Add($trimmed)

  $firstObject = $trimmed.IndexOf("{")
  $lastObject = $trimmed.LastIndexOf("}")
  if ($firstObject -ge 0 -and $lastObject -gt $firstObject) {
    $candidates.Add($trimmed.Substring($firstObject, $lastObject - $firstObject + 1))
  }

  $firstArray = $trimmed.IndexOf("[")
  $lastArray = $trimmed.LastIndexOf("]")
  if ($firstArray -ge 0 -and $lastArray -gt $firstArray) {
    $candidates.Add($trimmed.Substring($firstArray, $lastArray - $firstArray + 1))
  }

  foreach ($candidate in ($candidates | Select-Object -Unique)) {
    if (-not $candidate) {
      continue
    }
    try {
      return $candidate | ConvertFrom-Json
    } catch {
      continue
    }
  }

  return $null
}

function Get-SwarmState {
  $swarmRaw = Capture-Text { & $dockerCli info --format "{{json .Swarm}}" }
  $parsed = Parse-JsonText -Text $swarmRaw
  $localNodeState = $null
  if ($null -ne $parsed -and $parsed.PSObject.Properties.Match("LocalNodeState").Count -gt 0) {
    $localNodeState = [string]$parsed.LocalNodeState
  }

  [PSCustomObject]@{
    raw = $swarmRaw
    parsed = $parsed
    local_node_state = $localNodeState
    healthy = [bool]($null -ne $parsed)
  }
}

function Invoke-PowerShellJsonScript {
  param(
    [string]$Path,
    [string[]]$Arguments
  )

  $raw = Capture-Text { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Path @Arguments }
  $exitCode = $LASTEXITCODE
  [PSCustomObject]@{
    path = $Path
    args = $Arguments
    exit_code = $exitCode
    raw = $raw
    payload = Parse-JsonText -Text $raw
  }
}

function Invoke-DockerLeaveWithTimeout {
  param([int]$TimeoutSeconds)

  $dockerExe = $dockerCli
  $capture = Invoke-ExecutableCapture -FilePath $dockerExe -Arguments @("swarm", "leave", "--force") -TimeoutSeconds $TimeoutSeconds
  return [PSCustomObject]@{
    start_ok = $capture.start_ok
    timed_out = $capture.timed_out
    exit_code = $capture.exit_code
    stdout = $capture.stdout
    stderr = $capture.stderr
  }
}

function Exit-WithFailure {
  param(
    [string]$Step,
    [System.Collections.IDictionary]$Body
  )

  $payload = [ordered]@{
    step = $Step
    session_file = $SessionFilePath
  }
  foreach ($entry in $Body.GetEnumerator()) {
    $payload[$entry.Key] = $entry.Value
  }

  $payload | ConvertTo-Json -Depth 12
  exit 1
}

$initialSwarm = Get-SwarmState

$recoverArgs = @("-WaitTimeoutSeconds", [string]$RecoverWaitTimeoutSeconds)
if ($RecoverResetWsl) {
  $recoverArgs += "-ResetWsl"
}
if ($RecoverRestartDockerDesktopProcesses) {
  $recoverArgs += "-RestartDockerDesktopProcesses"
}

$cycleArgs = @(
  "-SessionFilePath", $SessionFilePath,
  "-JoinMode", $JoinMode,
  "-ManagerWireGuardAddress", $ManagerWireGuardAddress,
  "-AdvertiseAddress", $AdvertiseAddress,
  "-DataPathAddress", $DataPathAddress,
  "-PostJoinProbeCount", [string]$PostJoinProbeCount,
  "-ProbeIntervalSeconds", [string]$ProbeIntervalSeconds,
  "-ManagerProbeCount", [string]$ManagerProbeCount,
  "-ManagerProbeIntervalSeconds", [string]$ManagerProbeIntervalSeconds
)
if ($ListenAddress) {
  $cycleArgs += @("-ListenAddress", $ListenAddress)
}
if ($RemoveStaleDownNodes) {
  $cycleArgs += "-RemoveStaleDownNodes"
}
if ($SkipBackendAuthoritativeCorrection) {
  $cycleArgs += "-SkipBackendAuthoritativeCorrection"
}

if ($DryRun) {
  [PSCustomObject]@{
    session_file = $SessionFilePath
    initial_swarm = $initialSwarm
    recover_script = @("powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $recoverScript) + $recoverArgs
    correction_cycle_script = @("powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $cycleScript) + $cycleArgs
    recover_docker_desktop = [bool]$RecoverDockerDesktop
    recover_reset_wsl = [bool]$RecoverResetWsl
    recover_restart_docker_desktop_processes = [bool]$RecoverRestartDockerDesktopProcesses
    leave_timeout_seconds = $LeaveTimeoutSeconds
  } | ConvertTo-Json -Depth 10
  exit 0
}

$recoverResult = $null
if ($RecoverDockerDesktop -or -not $initialSwarm.healthy) {
  $recoverResult = Invoke-PowerShellJsonScript -Path $recoverScript -Arguments $recoverArgs
  if ($recoverResult.exit_code -ne 0) {
    Exit-WithFailure -Step "docker_recover_failed" -Body ([ordered]@{
      initial_swarm = $initialSwarm
      recover = $recoverResult
    })
  }
}

$preLeaveSwarm = Get-SwarmState
$leaveAttempt = $null
$postLeaveSwarm = $preLeaveSwarm
$needsLeave = $false

if ($null -ne $preLeaveSwarm.parsed) {
  $state = [string]$preLeaveSwarm.local_node_state
  if ($state -and $state -notin @("inactive", "")) {
    $needsLeave = $true
  }
}

if ($needsLeave) {
  $leaveAttempt = Invoke-DockerLeaveWithTimeout -TimeoutSeconds $LeaveTimeoutSeconds
  $postLeaveSwarm = Get-SwarmState

  $postLeaveState = if ($null -ne $postLeaveSwarm.parsed) { [string]$postLeaveSwarm.local_node_state } else { $null }
  if ($leaveAttempt.timed_out -or ($postLeaveState -and $postLeaveState -notin @("inactive", ""))) {
    Exit-WithFailure -Step "docker_swarm_leave_failed" -Body ([ordered]@{
      initial_swarm = $initialSwarm
      recover = $recoverResult
      pre_leave_swarm = $preLeaveSwarm
      leave = $leaveAttempt
      post_leave_swarm = $postLeaveSwarm
    })
  }
}

$cycleResult = Invoke-PowerShellJsonScript -Path $cycleScript -Arguments $cycleArgs
$finalSwarm = Get-SwarmState

if ($cycleResult.exit_code -ne 0) {
  Exit-WithFailure -Step "correction_cycle_failed" -Body ([ordered]@{
    initial_swarm = $initialSwarm
    recover = $recoverResult
    pre_leave_swarm = $preLeaveSwarm
    leave = $leaveAttempt
    post_leave_swarm = $postLeaveSwarm
    correction_cycle = $cycleResult
    final_swarm = $finalSwarm
  })
}

[PSCustomObject]@{
  session_file = $SessionFilePath
  initial_swarm = $initialSwarm
  recover = $recoverResult
  pre_leave_swarm = $preLeaveSwarm
  leave = $leaveAttempt
  post_leave_swarm = $postLeaveSwarm
  correction_cycle = $cycleResult.payload
  correction_cycle_raw = $cycleResult.raw
  final_swarm = $finalSwarm
} | ConvertTo-Json -Depth 12
