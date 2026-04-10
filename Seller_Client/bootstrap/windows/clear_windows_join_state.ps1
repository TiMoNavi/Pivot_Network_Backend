param(
  [int]$LeaveTimeoutSeconds = 25,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$PSNativeCommandUseErrorActionPreference = $false

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
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
  $nodeId = $null
  $nodeAddr = $null
  $errorText = $null

  if ($null -ne $parsed) {
    if ($parsed.PSObject.Properties.Match("LocalNodeState").Count -gt 0) {
      $localNodeState = [string]$parsed.LocalNodeState
    }
    if ($parsed.PSObject.Properties.Match("NodeID").Count -gt 0) {
      $nodeId = [string]$parsed.NodeID
    }
    if ($parsed.PSObject.Properties.Match("NodeAddr").Count -gt 0) {
      $nodeAddr = [string]$parsed.NodeAddr
    }
    if ($parsed.PSObject.Properties.Match("Error").Count -gt 0) {
      $errorText = [string]$parsed.Error
    }
  }

  return [ordered]@{
    raw = $swarmRaw
    parsed = $parsed
    local_node_state = $localNodeState
    node_id = $nodeId
    node_addr = $nodeAddr
    error = $errorText
  }
}

function Invoke-DockerLeaveWithTimeout {
  param([int]$TimeoutSeconds)

  $capture = Invoke-ExecutableCapture -FilePath $dockerCli -Arguments @("swarm", "leave", "--force") -TimeoutSeconds $TimeoutSeconds
  return [ordered]@{
    start_ok = $capture.start_ok
    timed_out = $capture.timed_out
    exit_code = $capture.exit_code
    stdout = $capture.stdout
    stderr = $capture.stderr
    output = $capture.output
  }
}

function Exit-WithResult {
  param(
    [bool]$Ok,
    [string]$Status,
    [string]$Step,
    [System.Collections.IDictionary]$Body
  )

  $payload = [ordered]@{
    ok = $Ok
    status = $Status
    step = $Step
  }
  foreach ($entry in $Body.GetEnumerator()) {
    $payload[$entry.Key] = $entry.Value
  }

  $payload | ConvertTo-Json -Depth 12
  if ($Ok) {
    exit 0
  }
  exit 1
}

$beforeState = Get-SwarmState
$needsLeave = $false
$state = [string]$beforeState.local_node_state
if ($state -and $state -notin @("inactive", "")) {
  $needsLeave = $true
}

if ($DryRun) {
  Exit-WithResult -Ok $true -Status "dry_run" -Step "clear_join_state_dry_run" -Body ([ordered]@{
    docker_cli = $dockerCli
    leave_timeout_seconds = $LeaveTimeoutSeconds
    needs_leave = $needsLeave
    before_state = $beforeState
    after_state = $beforeState
  })
}

if (-not $needsLeave) {
  Exit-WithResult -Ok $true -Status "already_clear" -Step "clear_join_state" -Body ([ordered]@{
    docker_cli = $dockerCli
    leave_timeout_seconds = $LeaveTimeoutSeconds
    needs_leave = $false
    before_state = $beforeState
    leave = $null
    after_state = $beforeState
  })
}

$leaveAttempt = Invoke-DockerLeaveWithTimeout -TimeoutSeconds $LeaveTimeoutSeconds
$afterState = Get-SwarmState
$afterNodeState = [string]$afterState.local_node_state
$leaveOutput = [string]$leaveAttempt.output
$alreadyClear = $leaveOutput -match 'not part of a swarm'
$cleared = ($afterNodeState -in @("", "inactive")) -or $alreadyClear

if (-not $leaveAttempt.start_ok) {
  Exit-WithResult -Ok $false -Status "leave_start_failed" -Step "clear_join_state" -Body ([ordered]@{
    docker_cli = $dockerCli
    leave_timeout_seconds = $LeaveTimeoutSeconds
    needs_leave = $needsLeave
    before_state = $beforeState
    leave = $leaveAttempt
    after_state = $afterState
  })
}

if ($leaveAttempt.timed_out) {
  Exit-WithResult -Ok $false -Status "leave_timed_out" -Step "clear_join_state" -Body ([ordered]@{
    docker_cli = $dockerCli
    leave_timeout_seconds = $LeaveTimeoutSeconds
    needs_leave = $needsLeave
    before_state = $beforeState
    leave = $leaveAttempt
    after_state = $afterState
  })
}

if (-not $cleared) {
  Exit-WithResult -Ok $false -Status "leave_failed" -Step "clear_join_state" -Body ([ordered]@{
    docker_cli = $dockerCli
    leave_timeout_seconds = $LeaveTimeoutSeconds
    needs_leave = $needsLeave
    before_state = $beforeState
    leave = $leaveAttempt
    after_state = $afterState
  })
}

Exit-WithResult -Ok $true -Status "cleared" -Step "clear_join_state" -Body ([ordered]@{
  docker_cli = $dockerCli
  leave_timeout_seconds = $LeaveTimeoutSeconds
  needs_leave = $needsLeave
  before_state = $beforeState
  leave = $leaveAttempt
  after_state = $afterState
})
