param(
  [string]$SessionFilePath = $env:SELLER_CLIENT_SESSION_FILE,
  [ValidateSet("wireguard", "public")]
  [string]$JoinMode = "wireguard",
  [string]$ManagerWireGuardAddress = "10.66.66.1",
  [string]$AdvertiseAddress = "10.66.66.10",
  [string]$DataPathAddress = "10.66.66.10",
  [string]$ListenAddress = "10.66.66.10:2377",
  [int]$PostJoinProbeCount = 30,
  [int]$ProbeIntervalSeconds = 2,
  [string]$ManagerHostNameHint = "docker-desktop",
  [string]$ManagerHostName = "81.70.52.75",
  [string]$ManagerUser = "root",
  [int]$ManagerSshPort = 22,
  [string]$ManagerSshKeyPath = "",
  [string]$ManagerMonitorUbuntuDistro = "Ubuntu",
  [int]$ManagerProbeCount = 12,
  [int]$ManagerProbeIntervalSeconds = 5,
  [switch]$SkipOfficialRejoin,
  [switch]$LeaveExistingSwarm,
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
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$rejoinScript = Join-Path $ScriptDir "rejoin_windows_swarm_worker.ps1"
$managerMonitorScript = Join-Path $ScriptDir "monitor_swarm_manager_truth.ps1"
. (Join-Path $ScriptDir "swarm_runtime_common.ps1")
$dockerCli = Get-DockerCliPath
$ManagerSshKeyPath = Resolve-ManagerSshKeyPath -ExplicitPath $ManagerSshKeyPath -ProjectRoot $ProjectRoot

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

function Invoke-BackendJson {
  param(
    [string]$Method,
    [string]$Url,
    [hashtable]$Headers,
    [object]$Body = $null
  )

  $jsonBody = $null
  if ($null -ne $Body) {
    $jsonBody = $Body | ConvertTo-Json -Depth 16 -Compress
  }

  $handler = $null
  $client = $null
  $request = $null
  $content = $null
  $response = $null
  try {
    Add-Type -AssemblyName "System.Net.Http" | Out-Null
    $handler = New-Object System.Net.Http.HttpClientHandler
    $client = New-Object System.Net.Http.HttpClient($handler)
    $request = New-Object System.Net.Http.HttpRequestMessage([System.Net.Http.HttpMethod]::new($Method), $Url)

    foreach ($entry in $Headers.GetEnumerator()) {
      if ($null -eq $entry.Value) {
        continue
      }
      [void]$request.Headers.TryAddWithoutValidation([string]$entry.Key, [string]$entry.Value)
    }

    if ($null -ne $jsonBody) {
      $content = New-Object System.Net.Http.StringContent($jsonBody, [System.Text.Encoding]::UTF8, "application/json")
      $request.Content = $content
    }

    $response = $client.SendAsync($request).GetAwaiter().GetResult()
    $raw = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    return [PSCustomObject]@{
      ok = [bool]$response.IsSuccessStatusCode
      status_code = [int]$response.StatusCode
      payload = Parse-JsonText -Text $raw
      raw = $raw
      error = if ($response.IsSuccessStatusCode) { $null } else { [string]$response.ReasonPhrase }
    }
  } catch {
    return [PSCustomObject]@{
      ok = $false
      status_code = $null
      payload = $null
      raw = $null
      error = $_.Exception.Message
    }
  } finally {
    if ($null -ne $response) {
      $response.Dispose()
    }
    if ($null -ne $content) {
      $content.Dispose()
    }
    if ($null -ne $request) {
      $request.Dispose()
    }
    if ($null -ne $client) {
      $client.Dispose()
    }
    if ($null -ne $handler) {
      $handler.Dispose()
    }
  }
}

function Get-CompactSessionSummary {
  param($SessionPayload)
  if ($null -eq $SessionPayload) {
    return $null
  }
  return [ordered]@{
    session_id = $SessionPayload.session_id
    status = $SessionPayload.status
    expected_wireguard_ip = $SessionPayload.expected_wireguard_ip
    last_join_complete = $SessionPayload.last_join_complete
    manager_acceptance = $SessionPayload.manager_acceptance
    effective_target_addr = $SessionPayload.effective_target_addr
    effective_target_source = $SessionPayload.effective_target_source
    truth_authority = $SessionPayload.truth_authority
    correction_history_count = @($SessionPayload.correction_history).Count
    minimum_tcp_validation = $SessionPayload.minimum_tcp_validation
  }
}

function Get-ManagerSelectedCandidate {
  param(
    $ManagerMonitorPayload
  )

  if ($null -eq $ManagerMonitorPayload) {
    return $null
  }
  if ($null -ne $ManagerMonitorPayload.latest_sample -and $null -ne $ManagerMonitorPayload.latest_sample.selected_candidate) {
    return $ManagerMonitorPayload.latest_sample.selected_candidate
  }
  return $null
}

function Exit-WithFailure {
  param(
    [string]$Step,
    [hashtable]$Payload
  )

  $body = [ordered]@{
    step = $Step
    session_id = $sessionId
  }
  foreach ($entry in $Payload.GetEnumerator()) {
    $body[$entry.Key] = $entry.Value
  }
  $body | ConvertTo-Json -Depth 12
  exit 1
}

$session = Get-Content -Raw -Encoding UTF8 $SessionFilePath | ConvertFrom-Json
$onboardingSession = $session.onboarding_session
if ($null -eq $onboardingSession) {
  throw "onboarding_session is missing from session file."
}
$joinMaterial = $onboardingSession.swarm_join_material
if ($null -eq $joinMaterial) {
  throw "swarm_join_material is missing from session file."
}

$sessionManagerAddress = [string]$joinMaterial.manager_addr
if ($JoinMode -eq "wireguard") {
  if (-not $sessionManagerAddress) {
    throw "swarm_join_material.manager_addr is missing from session file."
  }
  $ManagerWireGuardAddress = $sessionManagerAddress
}

$sessionId = [string]$onboardingSession.session_id
$computeNodeId = [string]$onboardingSession.requested_compute_node_id
$backendBaseUrl = [string]$session.backend_base_url
$backendApiPrefix = [string]$session.backend_api_prefix
$authToken = [string]$session.auth_token

if (-not $sessionId) {
  throw "session_id is missing from session file."
}
if (-not $backendBaseUrl) {
  throw "backend_base_url is missing from session file."
}
if (-not $backendApiPrefix) {
  throw "backend_api_prefix is missing from session file."
}
if (-not $authToken) {
  throw "auth_token is missing from session file."
}

$headers = @{
  Authorization = "Bearer $authToken"
}

$joinCompleteUrl = "$backendBaseUrl$backendApiPrefix/seller/onboarding/sessions/$sessionId/join-complete"
$correctionUrl = "$backendBaseUrl$backendApiPrefix/seller/onboarding/sessions/$sessionId/corrections"
$reverifyUrl = "$backendBaseUrl$backendApiPrefix/seller/onboarding/sessions/$sessionId/re-verify"
$authoritativeUrl = "$backendBaseUrl$backendApiPrefix/seller/onboarding/sessions/$sessionId/authoritative-effective-target"
$sessionUrl = "$backendBaseUrl$backendApiPrefix/seller/onboarding/sessions/$sessionId"

$joinCommand = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", $rejoinScript,
  "-SessionFilePath", $SessionFilePath,
  "-JoinMode", $JoinMode,
  "-ManagerWireGuardAddress", $ManagerWireGuardAddress,
  "-AdvertiseAddress", $AdvertiseAddress,
  "-DataPathAddress", $DataPathAddress,
  "-PostJoinProbeCount", [string]$PostJoinProbeCount,
  "-ProbeIntervalSeconds", [string]$ProbeIntervalSeconds
)
if ($ListenAddress) {
  $joinCommand += @("-ListenAddress", $ListenAddress)
}
if ($LeaveExistingSwarm) {
  $joinCommand += "-LeaveExistingSwarm"
}

$monitorCommand = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", $managerMonitorScript,
  "-SessionFilePath", $SessionFilePath,
  "-ComputeNodeId", $computeNodeId,
  "-ExpectedWireGuardAddress", $AdvertiseAddress,
  "-HostNameHint", $ManagerHostNameHint,
  "-ManagerHostName", $ManagerHostName,
  "-ManagerUser", $ManagerUser,
  "-ManagerSshPort", [string]$ManagerSshPort,
  "-ManagerSshKeyPath", $ManagerSshKeyPath,
  "-UbuntuDistro", $ManagerMonitorUbuntuDistro,
  "-ProbeCount", [string]$ManagerProbeCount,
  "-ProbeIntervalSeconds", [string]$ManagerProbeIntervalSeconds
)
if ($RemoveStaleDownNodes) {
  $monitorCommand += "-RemoveStaleDownNodes"
}

if ($DryRun) {
  [PSCustomObject]@{
    session_file = $SessionFilePath
    session_id = $sessionId
    join_mode = $JoinMode
    join_command = @("powershell.exe") + $joinCommand
    manager_monitor_command = @("powershell.exe") + $monitorCommand
    join_complete_url = $joinCompleteUrl
    correction_url = $correctionUrl
    reverify_url = $reverifyUrl
    authoritative_effective_target_url = $authoritativeUrl
    manager_ssh_key_path = $ManagerSshKeyPath
    skip_official_rejoin = [bool]$SkipOfficialRejoin
    leave_existing_swarm = [bool]$LeaveExistingSwarm
  } | ConvertTo-Json -Depth 10
  exit 0
}

$joinRaw = $null
$joinExitCode = 0
$joinPayload = $null
if ($SkipOfficialRejoin) {
  $currentSwarmRaw = Capture-Text { & $dockerCli info --format "{{json .Swarm}}" }
  $joinPayload = [PSCustomObject]@{
    session_file = $SessionFilePath
    join_mode = $JoinMode
    join_target = if ($JoinMode -eq "wireguard") { "${ManagerWireGuardAddress}:2377" } else { $null }
    join_exit_code = 0
    leave_existing_swarm = [bool]$LeaveExistingSwarm
    join_output = "skipped official rejoin because current swarm state is already active and seller-side WG path is established"
    before_state = $currentSwarmRaw
    after_state = $currentSwarmRaw
    docker_desktop_route_to_manager = $null
    before_snapshot = $null
    after_snapshot = $null
    post_join_samples = @()
  }
} else {
  $joinRaw = Capture-Text { & powershell.exe @joinCommand }
  $joinExitCode = $LASTEXITCODE
  $joinPayload = Parse-JsonText -Text $joinRaw
  if ($joinExitCode -ne 0) {
    Exit-WithFailure -Step "join_failed" -Payload @{
      join_exit_code = $joinExitCode
      join_result = $joinPayload
      join_raw = $joinRaw
    }
  }
}

$swarmInfoText = Capture-Text { & $dockerCli info --format "{{json .Swarm}}" }
$swarmInfo = Parse-JsonText -Text $swarmInfoText
$nodeRef = $null
$observedWireGuardIp = $AdvertiseAddress
if ($null -ne $swarmInfo) {
  $nodeRef = [string]$swarmInfo.NodeID
  if ($swarmInfo.NodeAddr) {
    $observedWireGuardIp = [string]$swarmInfo.NodeAddr
  }
}

$joinCompletePayload = [ordered]@{
  reported_phase = "repair"
  node_ref = if ($nodeRef) { $nodeRef } else { $null }
  compute_node_id = if ($computeNodeId) { $computeNodeId } else { $null }
  observed_wireguard_ip = $observedWireGuardIp
  observed_advertise_addr = $AdvertiseAddress
  observed_data_path_addr = $DataPathAddress
  notes = @(
    "manager addr correction cycle after live join",
    $(if ($SkipOfficialRejoin) {
        "official WG-target rejoin was skipped because the current swarm state was already active"
      } elseif ($null -ne $joinPayload -and $joinPayload.join_idempotent_success) {
        "official WG-target rejoin was treated as idempotent because the node was already active with the expected advertise address"
      } else {
        "official WG-target rejoin executed before join-complete submission"
      })
  )
  raw_payload = @{
    join_mode = $JoinMode
    join_result = $joinPayload
  }
}

$joinCompleteResponse = Invoke-BackendJson -Method "POST" -Url $joinCompleteUrl -Headers $headers -Body $joinCompletePayload
if (-not $joinCompleteResponse.ok) {
  Exit-WithFailure -Step "join_complete_failed" -Payload @{
    join_result = $joinPayload
    join_complete = $joinCompleteResponse
  }
}

if ($nodeRef) {
  $monitorCommand += @("-NodeRef", $nodeRef)
}
$managerMonitorRaw = Capture-Text { & powershell.exe @monitorCommand }
$managerMonitorExitCode = $LASTEXITCODE
$managerMonitor = Parse-JsonText -Text $managerMonitorRaw
if ($managerMonitorExitCode -ne 0 -or $null -eq $managerMonitor) {
  Exit-WithFailure -Step "manager_truth_monitor_failed" -Payload @{
    join_result = $joinPayload
    join_complete = $joinCompleteResponse
    manager_monitor_exit_code = $managerMonitorExitCode
    manager_monitor_raw = $managerMonitorRaw
    manager_monitor = $managerMonitor
  }
}

$managerSelectedCandidate = Get-ManagerSelectedCandidate -ManagerMonitorPayload $managerMonitor

$correctionResponse = $null
if (-not $managerMonitor.raw_success) {
  $correctionPayload = [ordered]@{
    reported_phase = "repair"
    source_surface = "runtime_manager_addr_correction_cycle"
    correction_action = "set_explicit_advertise_and_data_path_addr_after_live_join"
    target_wireguard_ip = $observedWireGuardIp
    observed_advertise_addr = $AdvertiseAddress
    observed_data_path_addr = $DataPathAddress
    notes = @(
      "official WG-target rejoin completed but manager raw truth still not converged",
      "recording runtime correction before backend re-verify"
    )
    raw_payload = @{
      join_mode = $JoinMode
      node_ref = $nodeRef
      compute_node_id = $computeNodeId
      docker_swarm = $swarmInfo
      manager_monitor = $managerMonitor
    }
  }

  $correctionResponse = Invoke-BackendJson -Method "POST" -Url $correctionUrl -Headers $headers -Body $correctionPayload
  if (-not $correctionResponse.ok) {
    Exit-WithFailure -Step "correction_failed" -Payload @{
      join_result = $joinPayload
      join_complete = $joinCompleteResponse
      manager_monitor = $managerMonitor
      correction = $correctionResponse
    }
  }
}

$reverifyNodeRef = if ($null -ne $managerSelectedCandidate -and $managerSelectedCandidate.id) {
  [string]$managerSelectedCandidate.id
} elseif ($nodeRef) {
  $nodeRef
} else {
  $null
}

$reverifyPayload = [ordered]@{
  reported_phase = "repair"
  node_ref = $reverifyNodeRef
  compute_node_id = if ($computeNodeId) { $computeNodeId } else { $null }
  notes = @(
    "manager reverify after operator correction cycle",
    "raw_success=$($managerMonitor.raw_success)"
  )
  raw_payload = @{
    manager_monitor = $managerMonitor
  }
}

$reverifyResponse = Invoke-BackendJson -Method "POST" -Url $reverifyUrl -Headers $headers -Body $reverifyPayload
if (-not $reverifyResponse.ok) {
  Exit-WithFailure -Step "reverify_failed" -Payload @{
    join_result = $joinPayload
    manager_monitor = $managerMonitor
    reverify = $reverifyResponse
  }
}

$finalSessionResponse = Invoke-BackendJson -Method "GET" -Url $sessionUrl -Headers $headers
if (-not $finalSessionResponse.ok) {
  Exit-WithFailure -Step "session_get_failed" -Payload @{
    reverify = $reverifyResponse
    final_session = $finalSessionResponse
  }
}

$authoritativeCorrectionResponse = $null
if ($finalSessionResponse.payload.manager_acceptance.status -ne "matched" -and -not $SkipBackendAuthoritativeCorrection) {
  $authoritativeCorrectionResponse = Invoke-BackendJson -Method "POST" `
    -Url $authoritativeUrl `
    -Headers $headers `
    -Body ([ordered]@{
      reported_phase = "repair"
      source_surface = "backend_authoritative_workflow"
      effective_target_addr = $AdvertiseAddress
      effective_target_reason = "fresh Windows WG-target rejoin evidence plus manager raw truth mismatch"
      notes = @(
        "formal backend authoritative correction after fresh runtime rejoin evidence",
        "manager raw truth retained separately in manager_acceptance"
      )
      raw_payload = @{
        expected_wireguard_ip = $AdvertiseAddress
        join_complete = $joinCompleteResponse.payload
        manager_monitor = $managerMonitor
      }
    })
  if (-not $authoritativeCorrectionResponse.ok) {
    Exit-WithFailure -Step "authoritative_effective_target_failed" -Payload @{
      reverify = $reverifyResponse
      authoritative_effective_target = $authoritativeCorrectionResponse
    }
  }
  $finalSessionResponse = Invoke-BackendJson -Method "GET" -Url $sessionUrl -Headers $headers
  if (-not $finalSessionResponse.ok) {
    Exit-WithFailure -Step "session_get_failed_after_authoritative_target" -Payload @{
      authoritative_effective_target = $authoritativeCorrectionResponse
      final_session = $finalSessionResponse
    }
  }
}

$workflowSummary = Get-WorkflowOutcomeSummary -SessionPayload $finalSessionResponse.payload -LocalSwarmInfo $swarmInfo

[PSCustomObject]@{
  session_id = $sessionId
  join_result = $joinPayload
  docker_swarm = $swarmInfo
  join_complete = @{
    ok = $joinCompleteResponse.ok
    status_code = $joinCompleteResponse.status_code
    session = Get-CompactSessionSummary -SessionPayload $joinCompleteResponse.payload
  }
  manager_monitor = @{
    exit_code = $managerMonitorExitCode
    raw_success = $managerMonitor.raw_success
    latest_sample = $managerMonitor.latest_sample
  }
  correction = @{
    ok = if ($null -ne $correctionResponse) { $correctionResponse.ok } else { $null }
    status_code = if ($null -ne $correctionResponse) { $correctionResponse.status_code } else { $null }
    session = if ($null -ne $correctionResponse) {
      Get-CompactSessionSummary -SessionPayload $correctionResponse.payload
    } else {
      $null
    }
  }
  reverify = @{
    ok = $reverifyResponse.ok
    status_code = $reverifyResponse.status_code
    session = Get-CompactSessionSummary -SessionPayload $reverifyResponse.payload
  }
  authoritative_effective_target = @{
    ok = if ($null -ne $authoritativeCorrectionResponse) { $authoritativeCorrectionResponse.ok } else { $null }
    status_code = if ($null -ne $authoritativeCorrectionResponse) { $authoritativeCorrectionResponse.status_code } else { $null }
    session = if ($null -ne $authoritativeCorrectionResponse) {
      Get-CompactSessionSummary -SessionPayload $authoritativeCorrectionResponse.payload
    } else {
      $null
    }
  }
  final_session = @{
    ok = $finalSessionResponse.ok
    status_code = $finalSessionResponse.status_code
    session = Get-CompactSessionSummary -SessionPayload $finalSessionResponse.payload
  }
  summary = @{
    success_standard = $workflowSummary.success_standard
    path_outcome = $workflowSummary.path_outcome
    swarm_connectivity_verified = $workflowSummary.swarm_connectivity_verified
    local_swarm_active = $workflowSummary.local_swarm_active
    manager_acceptance_matched = $workflowSummary.manager_acceptance_matched
    workflow_target_established = $workflowSummary.workflow_target_established
    workflow_target_addr = $workflowSummary.workflow_target_addr
    workflow_target_source = $workflowSummary.workflow_target_source
    raw_manager_target_established = $workflowSummary.raw_manager_target_established
    raw_manager_target_reachable = $workflowSummary.raw_manager_target_reachable
    authoritative_target_established = $workflowSummary.authoritative_target_established
    authoritative_target_reachable = $workflowSummary.authoritative_target_reachable
    manager_acceptance_status = $finalSessionResponse.payload.manager_acceptance.status
    observed_manager_node_addr = $finalSessionResponse.payload.manager_acceptance.observed_manager_node_addr
    effective_target_addr = $finalSessionResponse.payload.effective_target_addr
    effective_target_source = $finalSessionResponse.payload.effective_target_source
    truth_authority = $finalSessionResponse.payload.truth_authority
  }
} | ConvertTo-Json -Depth 12
