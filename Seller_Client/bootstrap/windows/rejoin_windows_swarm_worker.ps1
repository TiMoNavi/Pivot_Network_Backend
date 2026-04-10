param(
  [string]$SessionFilePath = $env:SELLER_CLIENT_SESSION_FILE,
  [ValidateSet("wireguard", "public")]
  [string]$JoinMode = "wireguard",
  [string]$ManagerWireGuardAddress = "10.66.66.1",
  [string]$AdvertiseAddress = "10.66.66.10",
  [string]$DataPathAddress = "10.66.66.10",
  [string]$ListenAddress = "10.66.66.10:2377",
  [int]$CommandTimeoutSeconds = 35,
  [int]$JoinSettleTimeoutSeconds = 90,
  [int]$JoinSettleIntervalSeconds = 5,
  [int]$PreJoinOverlayReadyTimeoutSeconds = 45,
  [int]$PreJoinOverlayReadyIntervalSeconds = 3,
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
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
. (Join-Path $ScriptDir "swarm_runtime_common.ps1")

if (-not $SessionFilePath) {
  throw "Session file is required. Pass -SessionFilePath or set SELLER_CLIENT_SESSION_FILE."
}
if (-not (Test-Path $SessionFilePath)) {
  throw "Session file not found: $SessionFilePath"
}
$script:DockerCli = Get-DockerCliPath

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

function Join-NonEmptyText {
  param([string[]]$Parts)

  return ($Parts |
    Where-Object { $_ -and $_.Trim() } |
    ForEach-Object { $_.Trim() }) -join "`n"
}

function Invoke-ProcessCapture {
  param(
    [string]$FilePath,
    [string[]]$Arguments,
    [int]$TimeoutSeconds
  )

  $capture = Invoke-ExecutableCapture -FilePath $FilePath -Arguments $Arguments -TimeoutSeconds $TimeoutSeconds
  return [PSCustomObject]@{
    start_ok = $capture.start_ok
    timed_out = $capture.timed_out
    exit_code = $capture.exit_code
    stdout = $capture.stdout
    stderr = $capture.stderr
    combined_output = (Join-NonEmptyText -Parts @($capture.stdout, $capture.stderr))
  }
}

function Get-Snapshot {
  param(
    [string]$ManagerAddress,
    [string]$DockerDesktopName
  )

  $swarmText = Capture-Text { & $script:DockerCli info --format "{{json .Swarm}}" }
  $routeResult = Invoke-DockerDesktopDaemonCapture -Distro $DockerDesktopName -TimeoutSeconds 10 -Script "ip route get $ManagerAddress || true"

  [ordered]@{
    captured_at = (Get-Date).ToString("o")
    docker_swarm = Parse-JsonText -Text $swarmText
    docker_swarm_raw = $swarmText
    docker_desktop_route_to_manager = $routeResult.output
    route_exit_code = $routeResult.exit_code
    route_timed_out = $routeResult.timed_out
  }
}

function Get-SwarmJoinView {
  param(
    $Snapshot
  )

  $swarm = $null
  if ($null -ne $Snapshot) {
    $swarm = $Snapshot.docker_swarm
  }

  $localNodeState = ""
  $nodeId = ""
  $nodeAddr = ""
  $errorText = ""

  if ($null -ne $swarm) {
    if ($swarm.PSObject.Properties.Match("LocalNodeState").Count -gt 0) {
      $localNodeState = [string]$swarm.LocalNodeState
    }
    if ($swarm.PSObject.Properties.Match("NodeID").Count -gt 0) {
      $nodeId = [string]$swarm.NodeID
    }
    if ($swarm.PSObject.Properties.Match("NodeAddr").Count -gt 0) {
      $nodeAddr = [string]$swarm.NodeAddr
    }
    if ($swarm.PSObject.Properties.Match("Error").Count -gt 0) {
      $errorText = [string]$swarm.Error
    }
  }

  return [ordered]@{
    local_node_state = $localNodeState
    node_id = $nodeId
    node_addr = $nodeAddr
    error = $errorText
  }
}

function Wait-ForJoinSettle {
  param(
    [string]$ManagerAddress,
    [string]$DockerDesktopName,
    [int]$TimeoutSeconds,
    [int]$IntervalSeconds
  )

  $samples = @()
  $finalSnapshot = $null
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

  do {
    $finalSnapshot = Get-Snapshot -ManagerAddress $ManagerAddress -DockerDesktopName $DockerDesktopName
    $swarm = $finalSnapshot.docker_swarm
    $localNodeState = ""
    $nodeId = ""
    $nodeAddr = ""
    $errorText = ""

    if ($null -ne $swarm) {
      if ($swarm.PSObject.Properties.Match("LocalNodeState").Count -gt 0) {
        $localNodeState = [string]$swarm.LocalNodeState
      }
      if ($swarm.PSObject.Properties.Match("NodeID").Count -gt 0) {
        $nodeId = [string]$swarm.NodeID
      }
      if ($swarm.PSObject.Properties.Match("NodeAddr").Count -gt 0) {
        $nodeAddr = [string]$swarm.NodeAddr
      }
      if ($swarm.PSObject.Properties.Match("Error").Count -gt 0) {
        $errorText = [string]$swarm.Error
      }
    }

    $samples += [pscustomobject]@{
      captured_at = $finalSnapshot.captured_at
      local_node_state = $localNodeState
      node_id = $nodeId
      node_addr = $nodeAddr
      error = $errorText
      docker_swarm_raw = $finalSnapshot.docker_swarm_raw
    }

    if ($localNodeState -eq "active" -and $nodeId) {
      return [ordered]@{
        settled = $true
        success = $true
        terminal_reason = "active"
        final_snapshot = $finalSnapshot
        samples = $samples
      }
    }

    if ($localNodeState -in @("error", "inactive")) {
      return [ordered]@{
        settled = $true
        success = $false
        terminal_reason = $localNodeState
        final_snapshot = $finalSnapshot
        samples = $samples
      }
    }

    if ((Get-Date) -ge $deadline) {
      break
    }

    Start-Sleep -Seconds $IntervalSeconds
  } while ($true)

  return [ordered]@{
    settled = $false
    success = $false
    terminal_reason = "timeout"
    final_snapshot = $finalSnapshot
    samples = $samples
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

function Get-OverlayBindReadinessSample {
  param(
    [string]$DockerDesktopName,
    [string]$AdvertiseIp,
    [int]$SwarmGossipPort = 7946,
    [int]$SwarmOverlayPort = 4789
  )

  $scriptText = @'
ADDR="__ADDR__"
TCP_PORT="__TCP_PORT__"
UDP_PORT="__UDP_PORT__"
iface_line=$(ip -o -4 addr show scope global | grep -F "inet $ADDR/" | head -n 1 || true)
if [ -z "$iface_line" ]; then
  printf '{"address_present":false,"tcp_7946_ready":false,"udp_4789_ready":false,"matched_interface":null,"tcp_detail":"address_missing","udp_detail":"address_missing"}\n'
  exit 0
fi

iface=$(printf '%s\n' "$iface_line" | awk '{print $2}')
tcp_listener=false
udp_listener=false

if netstat -lnt 2>/dev/null | grep -Eq ":$TCP_PORT([[:space:]]|$)"; then
  tcp_listener=true
fi
if netstat -lnu 2>/dev/null | grep -Eq ":$UDP_PORT([[:space:]]|$)"; then
  udp_listener=true
fi

if [ "$tcp_listener" = true ]; then
  tcp_ready=true
  tcp_detail="listener_present"
else
  tcp_ready=false
  tcp_detail="bind_failed"
  nc -l -p "$TCP_PORT" -s "$ADDR" -w 5 >/dev/null 2>&1 &
  tcp_pid=$!
  sleep 1
  if kill -0 "$tcp_pid" 2>/dev/null; then
    tcp_ready=true
    tcp_detail="bind_ok"
    kill "$tcp_pid" >/dev/null 2>&1 || true
  fi
  wait "$tcp_pid" >/dev/null 2>&1 || true
fi

if [ "$udp_listener" = true ]; then
  udp_ready=true
  udp_detail="listener_present"
else
  udp_ready=false
  udp_detail="bind_failed"
  nc -u -l -p "$UDP_PORT" -s "$ADDR" -w 5 >/dev/null 2>&1 &
  udp_pid=$!
  sleep 1
  if kill -0 "$udp_pid" 2>/dev/null; then
    udp_ready=true
    udp_detail="bind_ok"
    kill "$udp_pid" >/dev/null 2>&1 || true
  fi
  wait "$udp_pid" >/dev/null 2>&1 || true
fi

printf '{"address_present":true,"tcp_7946_ready":%s,"udp_4789_ready":%s,"matched_interface":"%s","tcp_detail":"%s","udp_detail":"%s"}\n' "$tcp_ready" "$udp_ready" "$iface" "$tcp_detail" "$udp_detail"
'@
  $scriptText = $scriptText.Replace("__ADDR__", $AdvertiseIp)
  $scriptText = $scriptText.Replace("__TCP_PORT__", [string]$SwarmGossipPort)
  $scriptText = $scriptText.Replace("__UDP_PORT__", [string]$SwarmOverlayPort)

  $probe = Invoke-DockerDesktopDaemonCapture -Distro $DockerDesktopName -TimeoutSeconds 15 -Script $scriptText
  $payload = Parse-JsonText -Text $probe.output

  return [ordered]@{
    captured_at = (Get-Date).ToString("o")
    advertise_address = $AdvertiseIp
    address_present = [bool]($null -ne $payload -and $payload.address_present)
    tcp_7946_ready = [bool]($null -ne $payload -and $payload.tcp_7946_ready)
    udp_4789_ready = [bool]($null -ne $payload -and $payload.udp_4789_ready)
    matched_interface = if ($null -ne $payload) { [string]$payload.matched_interface } else { $null }
    tcp_detail = if ($null -ne $payload) { [string]$payload.tcp_detail } else { "probe_unavailable" }
    udp_detail = if ($null -ne $payload) { [string]$payload.udp_detail } else { "probe_unavailable" }
    exit_code = $probe.exit_code
    timed_out = $probe.timed_out
    raw_output = $probe.output
  }
}

function Wait-ForOverlayBindReadiness {
  param(
    [string]$DockerDesktopName,
    [string]$AdvertiseIp,
    [int]$TimeoutSeconds,
    [int]$IntervalSeconds
  )

  $samples = @()
  $finalSample = $null
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

  do {
    $finalSample = Get-OverlayBindReadinessSample `
      -DockerDesktopName $DockerDesktopName `
      -AdvertiseIp $AdvertiseIp
    $samples += [pscustomobject]$finalSample

    if ($finalSample.address_present -and $finalSample.tcp_7946_ready -and $finalSample.udp_4789_ready) {
      return [ordered]@{
        ready = $true
        terminal_reason = "ready"
        final_sample = $finalSample
        samples = $samples
      }
    }

    if ((Get-Date) -ge $deadline) {
      break
    }

    Start-Sleep -Seconds $IntervalSeconds
  } while ($true)

  return [ordered]@{
    ready = $false
    terminal_reason = "timeout"
    final_sample = $finalSample
    samples = $samples
  }
}

$session = Get-Content -Raw -Encoding UTF8 $SessionFilePath | ConvertFrom-Json
$joinMaterial = $session.onboarding_session.swarm_join_material
if ($null -eq $joinMaterial) {
  throw "swarm_join_material is missing from session file."
}

$sessionManagerAddress = [string]$joinMaterial.manager_addr
if (-not $sessionManagerAddress) {
  throw "swarm_join_material.manager_addr is missing from session file."
}
$managerPort = [int]$joinMaterial.manager_port
$effectiveManagerAddress = if ($JoinMode -eq "wireguard") {
  $sessionManagerAddress
} else {
  $sessionManagerAddress
}
$joinTarget = "${effectiveManagerAddress}:$managerPort"
$daemonWireGuardBootstrap = $null

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
$beforeSnapshot = Get-Snapshot -ManagerAddress $effectiveManagerAddress -DockerDesktopName $DockerDesktopDistro
$beforeState = $beforeSnapshot.docker_swarm_raw
$dockerCli = $script:DockerCli

if ($DryRun) {
  [PSCustomObject]@{
    session_file = $SessionFilePath
    join_mode = $JoinMode
    manager_addr_from_session = $sessionManagerAddress
    effective_manager_addr = $effectiveManagerAddress
    join_target = $joinTarget
    join_args = $joinArgs
    leave_existing_swarm = [bool]$LeaveExistingSwarm
    command_timeout_seconds = $CommandTimeoutSeconds
    join_settle_timeout_seconds = $JoinSettleTimeoutSeconds
    join_settle_interval_seconds = $JoinSettleIntervalSeconds
    pre_join_overlay_ready_timeout_seconds = $PreJoinOverlayReadyTimeoutSeconds
    pre_join_overlay_ready_interval_seconds = $PreJoinOverlayReadyIntervalSeconds
    post_join_probe_count = $PostJoinProbeCount
    probe_interval_seconds = $ProbeIntervalSeconds
    before_state = $beforeState
    before_snapshot = $beforeSnapshot
  } | ConvertTo-Json -Depth 6
  exit 0
}

$leaveOutput = $null
$leaveCapture = $null
if ($LeaveExistingSwarm) {
  $leaveCapture = Invoke-ProcessCapture -FilePath $dockerCli -Arguments @("swarm", "leave", "--force") -TimeoutSeconds $CommandTimeoutSeconds
  $leaveOutput = $leaveCapture.combined_output
}

if ($JoinMode -eq "wireguard") {
  $daemonWireGuardBootstrap = Ensure-DockerDesktopDaemonWireGuardInterface `
    -Distro $DockerDesktopDistro `
    -HostTunnelName "wg-seller" `
    -ManagerWireGuardAddress $effectiveManagerAddress `
    -InterfaceAddressCidr "$AdvertiseAddress/32" `
    -ProjectRoot $ProjectRoot
}

$preJoinOverlayReadiness = if ($PreJoinOverlayReadyTimeoutSeconds -gt 0) {
  Wait-ForOverlayBindReadiness `
    -DockerDesktopName $DockerDesktopDistro `
    -AdvertiseIp $AdvertiseAddress `
    -TimeoutSeconds $PreJoinOverlayReadyTimeoutSeconds `
    -IntervalSeconds $PreJoinOverlayReadyIntervalSeconds
} else {
  [ordered]@{
    ready = $true
    terminal_reason = "skipped"
    final_sample = $null
    samples = @()
  }
}

if (-not $preJoinOverlayReadiness.ready) {
  $afterSnapshot = Get-Snapshot -ManagerAddress $effectiveManagerAddress -DockerDesktopName $DockerDesktopDistro
  [PSCustomObject]@{
    session_file = $SessionFilePath
    join_mode = $JoinMode
    manager_addr_from_session = $sessionManagerAddress
    effective_manager_addr = $effectiveManagerAddress
    join_target = $joinTarget
    join_exit_code = 1
    leave_existing_swarm = [bool]$LeaveExistingSwarm
    command_timeout_seconds = $CommandTimeoutSeconds
    join_settle_timeout_seconds = $JoinSettleTimeoutSeconds
    join_settle_interval_seconds = $JoinSettleIntervalSeconds
    pre_join_overlay_ready_timeout_seconds = $PreJoinOverlayReadyTimeoutSeconds
    pre_join_overlay_ready_interval_seconds = $PreJoinOverlayReadyIntervalSeconds
    daemon_wireguard_bootstrap = $daemonWireGuardBootstrap
    pre_join_overlay_readiness = $preJoinOverlayReadiness
    leave_output = $leaveOutput
    leave_capture = $leaveCapture
    join_output = "pre-join overlay bind readiness check failed"
    join_capture = $null
    join_continued_in_background = $false
    join_idempotent_success = $false
    join_idempotent_reason = $null
    join_settle = $null
    before_state = $beforeState
    after_state = $afterSnapshot.docker_swarm_raw
    docker_desktop_route_to_manager = $afterSnapshot.docker_desktop_route_to_manager
    before_snapshot = $beforeSnapshot
    after_snapshot = [ordered]@{
      captured_at = $afterSnapshot.captured_at
      docker_swarm = $afterSnapshot.docker_swarm
      docker_swarm_raw = $afterSnapshot.docker_swarm_raw
      docker_desktop_route_to_manager = $afterSnapshot.docker_desktop_route_to_manager
      route_exit_code = $afterSnapshot.route_exit_code
      route_timed_out = $afterSnapshot.route_timed_out
      post_join_probe_count = 0
      probe_interval_seconds = $ProbeIntervalSeconds
      all_tcp_ports_reachable = $null
    }
    post_join_samples = @()
  } | ConvertTo-Json -Depth 10
  exit 1
}

$joinCapture = Invoke-ProcessCapture -FilePath $dockerCli -Arguments $joinArgs -TimeoutSeconds $CommandTimeoutSeconds
$joinOutput = $joinCapture.combined_output
$joinExitCode = if ($joinCapture.timed_out) {
  -1
} elseif ($joinCapture.start_ok -and $null -ne $joinCapture.exit_code) {
  [int]$joinCapture.exit_code
} else {
  1
}
$joinContinuedInBackground = [bool]($joinOutput -match 'continue in the background')
$joinSettle = $null
$afterSnapshot = Get-Snapshot -ManagerAddress $effectiveManagerAddress -DockerDesktopName $DockerDesktopDistro
$beforeJoinView = Get-SwarmJoinView -Snapshot $beforeSnapshot
$afterJoinView = Get-SwarmJoinView -Snapshot $afterSnapshot
$joinIdempotentSuccess = $false
$joinIdempotentReason = $null
if ($JoinSettleTimeoutSeconds -gt 0 -and ($joinExitCode -eq 0 -or $joinContinuedInBackground)) {
  $joinSettle = Wait-ForJoinSettle `
    -ManagerAddress $effectiveManagerAddress `
    -DockerDesktopName $DockerDesktopDistro `
    -TimeoutSeconds $JoinSettleTimeoutSeconds `
    -IntervalSeconds $JoinSettleIntervalSeconds
  if ($null -ne $joinSettle.final_snapshot) {
    $afterSnapshot = $joinSettle.final_snapshot
  }
  if ($joinSettle.success) {
    $joinExitCode = 0
  } elseif ($joinExitCode -eq 0) {
    $joinExitCode = 1
  }
}
$alreadyPartOfSwarm = [bool]($joinOutput -match 'already part of a swarm')
$expectedAddressSatisfied = (-not $AdvertiseAddress) -or ($afterJoinView.node_addr -eq $AdvertiseAddress)
if (
  $joinExitCode -ne 0 -and
  -not $joinContinuedInBackground -and
  $alreadyPartOfSwarm -and
  $beforeJoinView.local_node_state -eq "active" -and
  $afterJoinView.local_node_state -eq "active" -and
  $afterJoinView.node_id -and
  $expectedAddressSatisfied
) {
  $joinIdempotentSuccess = $true
  $joinIdempotentReason = "already_joined_and_active_with_expected_advertise_addr"
  $joinExitCode = 0
  $joinOutput = Join-NonEmptyText -Parts @(
    $joinOutput,
    "detected idempotent join success because the local node was already active in the swarm with the expected advertise address"
  )
  if ($null -eq $joinSettle) {
    $joinSettle = [ordered]@{
      settled = $true
      success = $true
      terminal_reason = "already_active"
      final_snapshot = $afterSnapshot
      samples = @()
    }
  }
}
$afterState = $afterSnapshot.docker_swarm_raw
$dockerDesktopRoute = $afterSnapshot.docker_desktop_route_to_manager
$postJoinSamples = @()
if ($joinExitCode -eq 0 -and $PostJoinProbeCount -gt 0) {
  $postJoinSamples = Get-PostJoinProbeSamples `
    -ManagerAddress $effectiveManagerAddress `
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
  manager_addr_from_session = $sessionManagerAddress
  effective_manager_addr = $effectiveManagerAddress
  join_target = $joinTarget
  join_exit_code = $joinExitCode
  leave_existing_swarm = [bool]$LeaveExistingSwarm
  command_timeout_seconds = $CommandTimeoutSeconds
  join_settle_timeout_seconds = $JoinSettleTimeoutSeconds
  join_settle_interval_seconds = $JoinSettleIntervalSeconds
  pre_join_overlay_ready_timeout_seconds = $PreJoinOverlayReadyTimeoutSeconds
  pre_join_overlay_ready_interval_seconds = $PreJoinOverlayReadyIntervalSeconds
  daemon_wireguard_bootstrap = $daemonWireGuardBootstrap
  pre_join_overlay_readiness = $preJoinOverlayReadiness
  leave_output = $leaveOutput
  leave_capture = $leaveCapture
  join_output = $joinOutput
  join_capture = $joinCapture
  join_continued_in_background = $joinContinuedInBackground
  join_idempotent_success = $joinIdempotentSuccess
  join_idempotent_reason = $joinIdempotentReason
  join_settle = $joinSettle
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
} | ConvertTo-Json -Depth 10

if ($joinExitCode -ne 0) {
  exit $joinExitCode
}
