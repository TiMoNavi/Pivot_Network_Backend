param(
  [string]$SessionFilePath = $env:SELLER_CLIENT_SESSION_FILE,
  [ValidateSet("wireguard", "public")]
  [string]$JoinMode = "wireguard",
  [string]$ManagerWireGuardAddress = "10.66.66.1",
  [string]$AdvertiseAddress = "10.66.66.10",
  [string]$DataPathAddress = "10.66.66.10",
  [string]$ListenAddress = "10.66.66.10:2377",
  [int]$PostJoinProbeCount = 0,
  [int]$ProbeIntervalSeconds = 0,
  [string]$DockerDesktopDistro = "docker-desktop",
  [switch]$LeaveExistingSwarm,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$PSNativeCommandUseErrorActionPreference = $false

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "swarm_runtime_common.ps1")

if (-not $SessionFilePath) {
  throw "Session file is required. Pass -SessionFilePath or set SELLER_CLIENT_SESSION_FILE."
}
if (-not (Test-Path $SessionFilePath)) {
  throw "Session file not found: $SessionFilePath"
}

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
  if (-not $trimmed.StartsWith("{") -and -not $trimmed.StartsWith("[")) {
    return $null
  }
  try {
    return $trimmed | ConvertFrom-Json -Depth 16
  } catch {
    return $null
  }
}

function Get-Snapshot {
  param(
    [string]$ManagerAddress,
    [string]$DockerDesktopName
  )

  $swarmText = Capture-Text { docker info --format "{{json .Swarm}}" }
  $routeResult = Invoke-WslCapture -Distro $DockerDesktopName -TimeoutSeconds 10 -Script "ip route get $ManagerAddress || true"

  [ordered]@{
    captured_at = (Get-Date).ToString("o")
    docker_swarm = Parse-JsonText -Text $swarmText
    docker_swarm_raw = $swarmText
    docker_desktop_route_to_manager = $routeResult.output
    route_exit_code = $routeResult.exit_code
    route_timed_out = $routeResult.timed_out
  }
}

function Get-PostJoinProbeSamples {
  param(
    [string]$ManagerAddress,
    [string]$DockerDesktopName,
    [int]$SampleCount,
    [int]$IntervalSeconds
  )

  $samples = @()
  for ($index = 0; $index -lt $SampleCount; $index++) {
    $samples += [pscustomobject](Get-DockerDesktopProbeSample `
      -Distro $DockerDesktopName `
      -ManagerWireGuardAddress $ManagerAddress `
      -TcpPorts @(2377, 7946))
    if ($index -lt ($SampleCount - 1) -and $IntervalSeconds -gt 0) {
      Start-Sleep -Seconds $IntervalSeconds
    }
  }
  return $samples
}

$session = Get-Content -Raw $SessionFilePath | ConvertFrom-Json
$joinMaterial = $session.onboarding_session.swarm_join_material
if ($null -eq $joinMaterial) {
  throw "swarm_join_material is missing from session file."
}

$managerPort = [int]$joinMaterial.manager_port
$joinTarget = if ($JoinMode -eq "wireguard") {
  "${ManagerWireGuardAddress}:$managerPort"
} else {
  "$($joinMaterial.manager_addr):$managerPort"
}

$joinArgs = @(
  "swarm", "join",
  "--token", [string]$joinMaterial.join_token,
  "--advertise-addr", $AdvertiseAddress,
  "--data-path-addr", $DataPathAddress
)

if ($ListenAddress) {
  $joinArgs += @("--listen-addr", $ListenAddress)
}

$joinArgs += $joinTarget
$beforeSnapshot = Get-Snapshot -ManagerAddress $ManagerWireGuardAddress -DockerDesktopName $DockerDesktopDistro
$beforeState = $beforeSnapshot.docker_swarm_raw

if ($DryRun) {
  [PSCustomObject]@{
    session_file = $SessionFilePath
    join_mode = $JoinMode
    join_target = $joinTarget
    join_args = $joinArgs
    leave_existing_swarm = [bool]$LeaveExistingSwarm
    post_join_probe_count = $PostJoinProbeCount
    probe_interval_seconds = $ProbeIntervalSeconds
    before_state = $beforeState
    before_snapshot = $beforeSnapshot
  } | ConvertTo-Json -Depth 6
  exit 0
}

$leaveOutput = $null
if ($LeaveExistingSwarm) {
  $leaveOutput = Capture-Text { docker swarm leave --force }
}

$joinOutput = Capture-Text { & docker @joinArgs }
$joinExitCode = $LASTEXITCODE
$afterSnapshot = Get-Snapshot -ManagerAddress $ManagerWireGuardAddress -DockerDesktopName $DockerDesktopDistro
$afterState = $afterSnapshot.docker_swarm_raw
$dockerDesktopRoute = $afterSnapshot.docker_desktop_route_to_manager
$postJoinSamples = @()
if ($joinExitCode -eq 0 -and $PostJoinProbeCount -gt 0) {
  $postJoinSamples = Get-PostJoinProbeSamples `
    -ManagerAddress $ManagerWireGuardAddress `
    -DockerDesktopName $DockerDesktopDistro `
    -SampleCount $PostJoinProbeCount `
    -IntervalSeconds $ProbeIntervalSeconds
}
$allTcpPortsReachable = $null
if ($postJoinSamples.Count -gt 0) {
  $allTcpPortsReachable = [bool]($postJoinSamples | Where-Object { -not $_.all_tcp_ports_reachable } | Select-Object -First 1) -eq $false
}

[PSCustomObject]@{
  session_file = $SessionFilePath
  join_mode = $JoinMode
  join_target = $joinTarget
  join_exit_code = $joinExitCode
  leave_existing_swarm = [bool]$LeaveExistingSwarm
  leave_output = $leaveOutput
  join_output = $joinOutput
  before_state = $beforeState
  after_state = $afterState
  docker_desktop_route_to_manager = $dockerDesktopRoute
  before_snapshot = $beforeSnapshot
  after_snapshot = [ordered]@{
    captured_at = $afterSnapshot.captured_at
    docker_swarm = $afterSnapshot.docker_swarm
    docker_swarm_raw = $afterSnapshot.docker_swarm_raw
    docker_desktop_route_to_manager = $afterSnapshot.docker_desktop_route_to_manager
    route_exit_code = $afterSnapshot.route_exit_code
    route_timed_out = $afterSnapshot.route_timed_out
    post_join_probe_count = $PostJoinProbeCount
    probe_interval_seconds = $ProbeIntervalSeconds
    all_tcp_ports_reachable = $allTcpPortsReachable
  }
  post_join_samples = $postJoinSamples
} | ConvertTo-Json -Depth 8

if ($joinExitCode -ne 0) {
  exit $joinExitCode
}
