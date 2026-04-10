param(
  [switch]$ForceRejoin,
  [switch]$SkipOfficialRejoin,
  [ValidateSet("wireguard", "public")]
  [string]$JoinMode = "wireguard",
  [string]$ManagerWireGuardAddress = "10.66.66.1",
  [string]$ManagerPublicAddress = "81.70.52.75",
  [string]$AdvertiseAddress = "10.66.66.10",
  [string]$DataPathAddress = "10.66.66.10",
  [string]$ListenAddress = "10.66.66.10:2377",
  [int]$DockerDesktopSoakSampleCount = 15,
  [int]$DockerDesktopSoakIntervalSeconds = 2,
  [switch]$IncludeOverlayUdpProbe,
  [int]$PostJoinProbeCount = 30,
  [int]$ProbeIntervalSeconds = 2,
  [int]$ManagerProbeCount = 12,
  [int]$ManagerProbeIntervalSeconds = 5,
  [string]$ManagerHostNameHint = "docker-desktop",
  [string]$ManagerSshUser = "root",
  [int]$ManagerSshPort = 22,
  [string]$ManagerSshKeyPath = "D:\AI\Pivot_backend_build_team\navi.pem",
  [string]$ManagerMonitorUbuntuDistro = "Ubuntu",
  [switch]$RemoveStaleDownNodes,
  [int]$MinimumTcpValidationPort = 8080,
  [int]$RejoinRecoverWaitTimeoutSeconds = 120,
  [switch]$SkipRejoinRecoverRetry,
  [switch]$SkipBackendAuthoritativeCorrection
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$PSNativeCommandUseErrorActionPreference = $false

$projectRoot = "D:\AI\Pivot_Client\seller_client"
$bootstrapWindowsRoot = Join-Path $projectRoot "bootstrap\windows"
. (Join-Path $bootstrapWindowsRoot "swarm_runtime_common.ps1")

function Invoke-Api {
  param(
    [string]$Method,
    [string]$Uri,
    [hashtable]$Headers = @{},
    $Body = $null
  )

  $params = @{
    Method = $Method
    Uri = $Uri
    Headers = $Headers
    UseBasicParsing = $true
    ErrorAction = "Stop"
  }
  if ($null -ne $Body) {
    $params.ContentType = "application/json"
    $params.Body = ($Body | ConvertTo-Json -Depth 16 -Compress)
  }

  $resp = Invoke-WebRequest @params
  $json = $null
  if ($resp.Content) {
    $json = $resp.Content | ConvertFrom-Json
  }
  return [PSCustomObject]@{
    status_code = [int]$resp.StatusCode
    json = $json
  }
}

function Refresh-LocalOnboardingSession {
  param(
    [hashtable]$Headers
  )

  $refresh = Invoke-Api -Method "POST" -Uri "http://127.0.0.1:8901/local-api/onboarding/refresh" -Headers $Headers -Body @{}
  return $refresh.json.onboarding_session
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

function Get-TcpValidationPayload {
  param(
    [string]$TargetAddress,
    [int]$TargetPort,
    [string]$TruthAuthority,
    [string]$EffectiveTargetSource
  )

  $probe = Test-TcpPort -TargetHost $TargetAddress -Port $TargetPort
  return [PSCustomObject]@{
    probe = $probe
    backend_payload = [ordered]@{
      reported_phase = "repair"
      target_addr = $TargetAddress
      target_port = $TargetPort
      reachable = [bool]$probe.reachable
      notes = @(
        "minimum TCP validation submitted from runtime_real_2b",
        "truth_authority=$TruthAuthority",
        "effective_target_source=$EffectiveTargetSource"
      )
      raw_payload = @{
        source_surface = "runtime_real_2b"
        tcp_probe = $probe
      }
    }
  }
}

function Invoke-PowerShellJsonScript {
  param(
    [string]$Path,
    [string[]]$Arguments
  )

  $raw = (& powershell -NoProfile -ExecutionPolicy Bypass -File $Path @Arguments | Out-String).Trim()
  $exitCode = $LASTEXITCODE
  $payload = $null
  if ($raw) {
    try {
      $payload = $raw | ConvertFrom-Json
    } catch {
      $payload = $null
    }
  }

  return [PSCustomObject]@{
    path = $Path
    args = $Arguments
    exit_code = $exitCode
    raw = $raw
    payload = $payload
  }
}

function Should-AttemptRejoinRecoverRetry {
  param($RejoinPayload)

  if ($null -eq $RejoinPayload) {
    return $true
  }

  $joinOutput = [string]$RejoinPayload.join_output
  $afterState = ""
  if ($null -ne $RejoinPayload.after_snapshot -and $null -ne $RejoinPayload.after_snapshot.docker_swarm) {
    $afterState = [string]$RejoinPayload.after_snapshot.docker_swarm.LocalNodeState
  }

  if ($joinOutput -match "continue in the background") {
    return $true
  }
  if ($joinOutput -match "Internal Server Error") {
    return $true
  }
  if ($joinOutput -match "authentication handshake failed") {
    return $true
  }
  if ($joinOutput -match "context deadline exceeded") {
    return $true
  }

  return $afterState -in @("pending", "error", "")
}

$result = [ordered]@{ steps = [ordered]@{} }
$currentStep = "bootstrap_start"

try {
  $startScript = Join-Path $bootstrapWindowsRoot "start_seller_client.ps1"
  $checkOverlayScript = Join-Path $bootstrapWindowsRoot "check_windows_overlay_runtime.ps1"
  $rejoinScript = Join-Path $bootstrapWindowsRoot "rejoin_windows_swarm_worker.ps1"
  $recoverScript = Join-Path $bootstrapWindowsRoot "recover_docker_desktop_engine.ps1"
  $managerMonitorScript = Join-Path $bootstrapWindowsRoot "monitor_swarm_manager_truth.ps1"

  $result.steps.bootstrap_start = [ordered]@{
    script_exists = (Test-Path $startScript)
    output = (& powershell -NoProfile -ExecutionPolicy Bypass -File $startScript | Out-String).Trim()
  }

  $root = $null
  for ($i = 0; $i -lt 15; $i++) {
    try {
      $root = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8901/"
      if ([int]$root.StatusCode -eq 200) {
        break
      }
    } catch {
      Start-Sleep -Seconds 2
    }
  }
  if ($null -eq $root -or [int]$root.StatusCode -ne 200) {
    throw "local_app_root_unavailable"
  }
  $result.steps.local_root = [ordered]@{
    status_code = [int]$root.StatusCode
    has_shell = $root.Content.Contains("鍗栧鎺ュ叆鏈湴澶栧３")
  }

  $currentStep = "window_session_open"
  $window = Invoke-Api -Method "POST" -Uri "http://127.0.0.1:8901/local-api/window-session/open" -Body @{}
  $headers = @{ "X-Window-Session-Id" = $window.json.session_id }
  $result.steps.window_session_open = [ordered]@{
    status_code = $window.status_code
    session_id = $window.json.session_id
    ttl_seconds = $window.json.ttl_seconds
  }

  $stamp = Get-Date -Format "yyyyMMddHHmmss"
  $rand = Get-Random -Minimum 1000 -Maximum 9999
  $email = "temp-seller-$stamp-$rand@example.com"
  $password = "PivotTmp!20260408$rand"
  $displayName = "Temp Seller $stamp"

  $currentStep = "register"
  $register = Invoke-Api -Method "POST" -Uri "http://127.0.0.1:8901/local-api/auth/register" -Headers $headers -Body @{
    email = $email
    display_name = $displayName
    password = $password
    role = "seller"
  }
  $result.steps.register = [ordered]@{
    status_code = $register.status_code
    seller_user_id = $register.json.user.id
  }

  $currentStep = "login"
  $login = Invoke-Api -Method "POST" -Uri "http://127.0.0.1:8901/local-api/auth/login" -Headers $headers -Body @{
    email = $email
    password = $password
  }
  $result.steps.login = [ordered]@{
    status_code = $login.status_code
    seller_user_id = $login.json.user.id
  }

  $dockerVersion = docker version --format "{{json .}}" | ConvertFrom-Json
  $dockerInfo = docker info --format "{{json .}}" | ConvertFrom-Json
  $wgIp = Get-NetIPAddress -InterfaceAlias "wg-seller" -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty IPAddress
  if (-not $wgIp) {
    $wgIp = $dockerInfo.Swarm.NodeAddr
  }
  $observedIps = @(
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
      Where-Object { $_.IPAddress -and $_.IPAddress -notlike "169.254.*" } |
      Select-Object -ExpandProperty IPAddress -Unique
  )
  $diskFreeGb = [int]([math]::Floor((Get-PSDrive -Name C).Free / 1GB))
  $memoryGb = [int]([math]::Floor($dockerInfo.MemTotal / 1GB))
  $runtimeVersion = [string]$dockerVersion.Server.Version
  $computeNodeId = "temp-seller-$stamp-node"

  $currentStep = "onboarding_start"
  $start = Invoke-Api -Method "POST" -Uri "http://127.0.0.1:8901/local-api/onboarding/start" -Headers $headers -Body @{
    requested_accelerator = "gpu"
    requested_compute_node_id = $computeNodeId
    requested_offer_tier = "medium"
  }
  $sessionId = $start.json.session.session_id
  $effectiveComputeNodeId = [string]$start.json.session.requested_compute_node_id
  if (-not $effectiveComputeNodeId) {
    $effectiveComputeNodeId = $computeNodeId
  }
  $sessionFile = [string]$start.json.paths.session_file
  $sessionState = Get-Content -Raw -Encoding UTF8 -Path $sessionFile | ConvertFrom-Json
  $backendBaseUrl = [string]$sessionState.backend_base_url
  $backendApiPrefix = [string]$sessionState.backend_api_prefix
  $backendHeaders = @{ Authorization = "Bearer $($sessionState.auth_token)" }

  $result.steps.onboarding_start = [ordered]@{
    status_code = $start.status_code
    session_id = $sessionId
    requested_compute_node_id = $effectiveComputeNodeId
    expected_wireguard_ip = $start.json.session.expected_wireguard_ip
    session_file = $sessionFile
  }

  $currentStep = "overlay_runtime_check"
  $overlayArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $checkOverlayScript,
    "-ManagerWireGuardAddress", $ManagerWireGuardAddress,
    "-ManagerPublicAddress", $ManagerPublicAddress,
    "-DockerDesktopSoakSampleCount", [string]$DockerDesktopSoakSampleCount,
    "-DockerDesktopSoakIntervalSeconds", [string]$DockerDesktopSoakIntervalSeconds
  )
  if ($IncludeOverlayUdpProbe) {
    $overlayArgs += "-IncludeOverlayUdpProbe"
  }
  $overlayRaw = (& powershell @overlayArgs | Out-String).Trim()
  $overlayStatus = $LASTEXITCODE
  $overlayResult = $overlayRaw | ConvertFrom-Json
  $result.steps.overlay_runtime_check = [ordered]@{
    exit_code = $overlayStatus
    docker_desktop = $overlayResult.docker_desktop
    windows_overlay = $overlayResult.windows_overlay
    ubuntu_advanced_mode = $overlayResult.ubuntu_advanced_mode
  }
  if ($overlayStatus -ne 0) {
    throw "overlay_runtime_check_failed"
  }
  if (-not $overlayResult.docker_desktop.soak_summary.all_tcp_ports_reachable) {
    throw "docker_desktop_control_plane_soak_failed"
  }

  $currentStep = "linux_substrate_probe"
  $remoteManagerAddr = $null
  if ($null -ne $dockerInfo.Swarm.RemoteManagers -and $dockerInfo.Swarm.RemoteManagers.Count -gt 0) {
    $remoteManagerAddr = [string]$dockerInfo.Swarm.RemoteManagers[0].Addr
  }
  $substrateRawPayload = @{
    swarm = @{
      node_id = [string]$dockerInfo.Swarm.NodeID
      node_addr = [string]$dockerInfo.Swarm.NodeAddr
      local_node_state = [string]$dockerInfo.Swarm.LocalNodeState
      manager_addr = $remoteManagerAddr
    }
    operating_system = [string]$dockerInfo.OperatingSystem
    overlay_runtime_check = @{
      manager_wireguard_address = [string]$ManagerWireGuardAddress
      manager_public_address = [string]$ManagerPublicAddress
      docker_desktop_route_get_manager = [string]$overlayResult.docker_desktop.route_get_manager
      docker_desktop_route_get_public_manager = [string]$overlayResult.docker_desktop.route_get_public_manager
      all_tcp_ports_reachable = [bool]$overlayResult.docker_desktop.soak_summary.all_tcp_ports_reachable
      sample_count = [int]$overlayResult.docker_desktop.soak_summary.sample_count
    }
  }
  $substrate = Invoke-Api -Method "POST" -Uri "http://127.0.0.1:8901/local-api/onboarding/probes/linux-substrate" -Headers $headers -Body ([ordered]@{
    reported_phase = "prepare"
    distribution_name = "Windows + Docker Desktop"
    kernel_release = [string]$dockerInfo.KernelVersion
    docker_available = $true
    docker_version = $runtimeVersion
    wireguard_available = [bool]$wgIp
    gpu_available = ($dockerInfo.Runtimes.PSObject.Properties.Name -contains "nvidia")
    cpu_cores = [int]$dockerInfo.NCPU
    memory_gb = $memoryGb
    disk_free_gb = $diskFreeGb
    observed_ips = $observedIps
    observed_wireguard_ip = [string]$wgIp
    observed_advertise_addr = [string]$dockerInfo.Swarm.NodeAddr
    observed_data_path_addr = [string]$dockerInfo.Swarm.NodeAddr
    notes = @(
      "real Windows substrate evidence submitted via seller client local API",
      "docker-desktop WG soak passed before official rejoin"
    )
    raw_payload = $substrateRawPayload
  })
  $result.steps.linux_substrate_probe = [ordered]@{
    status_code = $substrate.status_code
    observed_wireguard_ip = $wgIp
    expected_wireguard_ip_after_probe = $substrate.json.expected_wireguard_ip
  }

  $shouldRunOfficialRejoin = $true
  if ($SkipOfficialRejoin) {
    $shouldRunOfficialRejoin = $false
  }
  if ($ForceRejoin) {
    $shouldRunOfficialRejoin = $true
  }

  $currentStep = "docker_swarm_join"
  $rejoinResult = $null
  if ($shouldRunOfficialRejoin) {
    $rejoinArgs = @(
      "-SessionFilePath", $sessionFile,
      "-JoinMode", $JoinMode,
      "-ManagerWireGuardAddress", $ManagerWireGuardAddress,
      "-AdvertiseAddress", $AdvertiseAddress,
      "-DataPathAddress", $DataPathAddress,
      "-LeaveExistingSwarm",
      "-PostJoinProbeCount", [string]$PostJoinProbeCount,
      "-ProbeIntervalSeconds", [string]$ProbeIntervalSeconds
    )
    if ($ListenAddress) {
      $rejoinArgs += @("-ListenAddress", $ListenAddress)
    }

    $rejoinRun = Invoke-PowerShellJsonScript -Path $rejoinScript -Arguments $rejoinArgs
    $rejoinExitCode = $rejoinRun.exit_code
    $rejoinResult = $rejoinRun.payload
    $rejoinRecovery = $null
    $rejoinRetry = $null

    if ($rejoinExitCode -ne 0 -and -not $SkipRejoinRecoverRetry -and (Should-AttemptRejoinRecoverRetry -RejoinPayload $rejoinResult)) {
      $recoverRun = Invoke-PowerShellJsonScript -Path $recoverScript -Arguments @(
        "-RestartDockerDesktopProcesses",
        "-WaitTimeoutSeconds", [string]$RejoinRecoverWaitTimeoutSeconds
      )
      $rejoinRecovery = [ordered]@{
        exit_code = $recoverRun.exit_code
        result = $recoverRun.payload
        raw = $recoverRun.raw
      }

      if ($recoverRun.exit_code -eq 0) {
        $retryRun = Invoke-PowerShellJsonScript -Path $rejoinScript -Arguments $rejoinArgs
        $rejoinRetry = [ordered]@{
          exit_code = $retryRun.exit_code
          result = $retryRun.payload
          raw = $retryRun.raw
        }
        $rejoinExitCode = $retryRun.exit_code
        $rejoinResult = $retryRun.payload
      }
    }

    $result.steps.docker_swarm_join = [ordered]@{
      status = $(if ($rejoinExitCode -eq 0) {
        if ($null -ne $rejoinRetry) { "rejoined_after_recovery" } else { "rejoined" }
      } else { "failed" })
      exit_code = $rejoinExitCode
      join_mode = $JoinMode
      join_target = $(if ($null -ne $rejoinResult) { $rejoinResult.join_target } else { $null })
      leave_output = $(if ($null -ne $rejoinResult) { $rejoinResult.leave_output } else { $null })
      join_output = $(if ($null -ne $rejoinResult) { $rejoinResult.join_output } else { $null })
      before_snapshot = $(if ($null -ne $rejoinResult) { $rejoinResult.before_snapshot } else { $null })
      after_snapshot = $(if ($null -ne $rejoinResult) { $rejoinResult.after_snapshot } else { $null })
      post_join_samples = $(if ($null -ne $rejoinResult) { $rejoinResult.post_join_samples } else { $null })
      join_continued_in_background = $(if ($null -ne $rejoinResult) { $rejoinResult.join_continued_in_background } else { $null })
      join_settle = $(if ($null -ne $rejoinResult) { $rejoinResult.join_settle } else { $null })
      recovery = $rejoinRecovery
      retry = $rejoinRetry
    }
    if ($rejoinExitCode -ne 0) {
      throw "docker_swarm_rejoin_failed"
    }
  } else {
    $result.steps.docker_swarm_join = [ordered]@{
      status = "skipped"
      detail = "SkipOfficialRejoin was requested."
    }
  }

  $postJoinDockerInfo = docker info --format "{{json .}}" | ConvertFrom-Json
  $postJoinWgIp = Get-NetIPAddress -InterfaceAlias "wg-seller" -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty IPAddress
  if (-not $postJoinWgIp) {
    $postJoinWgIp = $postJoinDockerInfo.Swarm.NodeAddr
  }

  $currentStep = "container_runtime_probe"
  $runtimeProbe = Invoke-Api -Method "POST" -Uri "http://127.0.0.1:8901/local-api/onboarding/probes/container-runtime" -Headers $headers -Body ([ordered]@{
    reported_phase = "install"
    runtime_name = "docker"
    runtime_version = $runtimeVersion
    engine_available = $true
    image_store_accessible = $true
    network_ready = ([string]$postJoinDockerInfo.Swarm.LocalNodeState -eq "active")
    observed_images = @()
    notes = @(
      "container runtime probe submitted after bounded official rejoin",
      "local swarm state=$($postJoinDockerInfo.Swarm.LocalNodeState)"
    )
    raw_payload = @{
      docker_version = $dockerVersion
      docker_info = $postJoinDockerInfo
      rejoin = $rejoinResult
    }
  })
  $result.steps.container_runtime_probe = [ordered]@{
    status_code = $runtimeProbe.status_code
    local_node_state = [string]$postJoinDockerInfo.Swarm.LocalNodeState
    node_ref = [string]$postJoinDockerInfo.Swarm.NodeID
    node_addr = [string]$postJoinDockerInfo.Swarm.NodeAddr
  }

  $currentStep = "join_complete"
  $joinNotes = @(
    "fresh Windows join-complete submitted via seller client local API",
    "official Docker WG-target rejoin executed before join-complete submission"
  )
  $joinComplete = Invoke-Api -Method "POST" -Uri "http://127.0.0.1:8901/local-api/onboarding/join-complete" -Headers $headers -Body ([ordered]@{
    reported_phase = "install"
    node_ref = [string]$postJoinDockerInfo.Swarm.NodeID
    compute_node_id = [string]$effectiveComputeNodeId
    observed_wireguard_ip = [string]$postJoinWgIp
    observed_advertise_addr = [string]$AdvertiseAddress
    observed_data_path_addr = [string]$DataPathAddress
    notes = $joinNotes
    raw_payload = @{
      evidence_source = "windows_local_api"
      docker_swarm = $postJoinDockerInfo.Swarm
      rejoin = $rejoinResult
    }
  })
  $result.steps.join_complete = [ordered]@{
    status_code = $joinComplete.status_code
    session_status = $joinComplete.json.status
    manager_acceptance_status = $joinComplete.json.manager_acceptance.status
    manager_node_addr = $joinComplete.json.manager_acceptance.observed_manager_node_addr
  }

  $currentStep = "manager_truth_monitor"
  $managerMonitorRaw = (& powershell -NoProfile -ExecutionPolicy Bypass -File $managerMonitorScript `
    -SessionFilePath $sessionFile `
    -ComputeNodeId $effectiveComputeNodeId `
    -NodeRef ([string]$postJoinDockerInfo.Swarm.NodeID) `
    -ExpectedWireGuardAddress $AdvertiseAddress `
    -HostNameHint $ManagerHostNameHint `
    -ManagerHostName $ManagerPublicAddress `
    -ManagerUser $ManagerSshUser `
    -ManagerSshPort $ManagerSshPort `
    -ManagerSshKeyPath $ManagerSshKeyPath `
    -UbuntuDistro $ManagerMonitorUbuntuDistro `
    -ProbeCount $ManagerProbeCount `
    -ProbeIntervalSeconds $ManagerProbeIntervalSeconds | Out-String).Trim()
  $managerMonitorExitCode = $LASTEXITCODE
  $managerMonitor = $managerMonitorRaw | ConvertFrom-Json
  $managerSelectedCandidate = Get-ManagerSelectedCandidate -ManagerMonitorPayload $managerMonitor
  $result.steps.manager_truth_monitor = [ordered]@{
    exit_code = $managerMonitorExitCode
    raw_success = $managerMonitor.raw_success
    latest_sample = $managerMonitor.latest_sample
  }
  if ($managerMonitorExitCode -ne 0) {
    throw "manager_truth_monitor_failed"
  }

  $currentStep = "runtime_rejoin_correction"
  $runtimeCorrection = $null
  if (-not $managerMonitor.raw_success) {
    $runtimeCorrection = Invoke-Api -Method "POST" `
      -Uri "$backendBaseUrl$backendApiPrefix/seller/onboarding/sessions/$sessionId/corrections" `
      -Headers $backendHeaders `
      -Body ([ordered]@{
        reported_phase = "repair"
        source_surface = "windows_runtime_real_2b"
        correction_action = "runtime_rejoin_correction"
        target_wireguard_ip = $AdvertiseAddress
        observed_advertise_addr = $AdvertiseAddress
        observed_data_path_addr = $DataPathAddress
        notes = @(
          "official WG-target rejoin completed but manager raw truth still not converged",
          "recording runtime correction before backend re-verify"
        )
        raw_payload = @{
          rejoin = $rejoinResult
          manager_monitor = $managerMonitor
        }
      })
    Refresh-LocalOnboardingSession -Headers $headers | Out-Null
  }
  $result.steps.runtime_rejoin_correction = [ordered]@{
    applied = [bool]($null -ne $runtimeCorrection)
    status_code = $(if ($null -ne $runtimeCorrection) { $runtimeCorrection.status_code } else { $null })
  }

  $cleanupMonitor = $null
  if (-not $managerMonitor.raw_success -and $RemoveStaleDownNodes) {
    $currentStep = "manager_cleanup"
    $cleanupMonitorRaw = (& powershell -NoProfile -ExecutionPolicy Bypass -File $managerMonitorScript `
      -SessionFilePath $sessionFile `
      -ComputeNodeId $effectiveComputeNodeId `
      -NodeRef ([string]$postJoinDockerInfo.Swarm.NodeID) `
      -ExpectedWireGuardAddress $AdvertiseAddress `
      -HostNameHint $ManagerHostNameHint `
      -ManagerHostName $ManagerPublicAddress `
      -ManagerUser $ManagerSshUser `
      -ManagerSshPort $ManagerSshPort `
      -ManagerSshKeyPath $ManagerSshKeyPath `
      -UbuntuDistro $ManagerMonitorUbuntuDistro `
      -ProbeCount 1 `
      -ProbeIntervalSeconds 0 `
      -RemoveStaleDownNodes | Out-String).Trim()
    $cleanupMonitor = $cleanupMonitorRaw | ConvertFrom-Json
    $result.steps.manager_cleanup = [ordered]@{
      removed_node_ids = $cleanupMonitor.cleanup.removed_node_ids
      remove_exit_code = $cleanupMonitor.cleanup.remove_exit_code
      remove_output = $cleanupMonitor.cleanup.remove_output
    }
  }

  $currentStep = "backend_reverify"
  $reverifyNodeRef = [string]$postJoinDockerInfo.Swarm.NodeID
  if ($null -ne $managerSelectedCandidate -and $managerSelectedCandidate.id) {
    $reverifyNodeRef = [string]$managerSelectedCandidate.id
  }
  $reverify = Invoke-Api -Method "POST" `
    -Uri "$backendBaseUrl$backendApiPrefix/seller/onboarding/sessions/$sessionId/re-verify" `
    -Headers $backendHeaders `
    -Body ([ordered]@{
      reported_phase = "repair"
      node_ref = $reverifyNodeRef
      compute_node_id = $effectiveComputeNodeId
      notes = @(
        "backend re-verify requested after fresh manager truth monitor",
        "raw_success=$($managerMonitor.raw_success)"
      )
      raw_payload = @{
        manager_monitor = $managerMonitor
        manager_cleanup = $cleanupMonitor
      }
    })
  $backendSession = Refresh-LocalOnboardingSession -Headers $headers
  $result.steps.backend_reverify = [ordered]@{
    status_code = $reverify.status_code
    status = $backendSession.status
    manager_acceptance = $backendSession.manager_acceptance
    effective_target_addr = $backendSession.effective_target_addr
    effective_target_source = $backendSession.effective_target_source
    truth_authority = $backendSession.truth_authority
  }

  $currentStep = "authoritative_effective_target"
  $authoritativeCorrection = $null
  if ($backendSession.manager_acceptance.status -ne "matched" -and -not $SkipBackendAuthoritativeCorrection) {
    $authoritativeCorrection = Invoke-Api -Method "POST" `
      -Uri "$backendBaseUrl$backendApiPrefix/seller/onboarding/sessions/$sessionId/authoritative-effective-target" `
      -Headers $backendHeaders `
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
          join_complete = $joinComplete.json
          manager_monitor = $managerMonitor
          manager_cleanup = $cleanupMonitor
        }
      })
    $backendSession = Refresh-LocalOnboardingSession -Headers $headers
  }
  $result.steps.authoritative_effective_target = [ordered]@{
    applied = [bool]($null -ne $authoritativeCorrection)
    status_code = $(if ($null -ne $authoritativeCorrection) { $authoritativeCorrection.status_code } else { $null })
    effective_target_addr = $backendSession.effective_target_addr
    effective_target_source = $backendSession.effective_target_source
    truth_authority = $backendSession.truth_authority
  }

  $currentStep = "minimum_tcp_validation"
  $tcpValidation = $null
  $tcpValidationLocalProbe = $null
  $validationTarget = [string]$backendSession.effective_target_addr
  if (-not $validationTarget -and $backendSession.manager_acceptance.status -eq "matched") {
    $validationTarget = [string]$backendSession.manager_acceptance.observed_manager_node_addr
  }
  if ($validationTarget) {
    $tcpValidationLocalProbe = Get-TcpValidationPayload `
      -TargetAddress $validationTarget `
      -TargetPort $MinimumTcpValidationPort `
      -TruthAuthority ([string]$backendSession.truth_authority) `
      -EffectiveTargetSource ([string]$backendSession.effective_target_source)
    $tcpValidation = Invoke-Api -Method "POST" `
      -Uri "$backendBaseUrl$backendApiPrefix/seller/onboarding/sessions/$sessionId/minimum-tcp-validation" `
      -Headers $backendHeaders `
      -Body $tcpValidationLocalProbe.backend_payload
    $backendSession = Refresh-LocalOnboardingSession -Headers $headers
  }
  $result.steps.minimum_tcp_validation = [ordered]@{
    attempted = [bool]$validationTarget
    validation_target = $validationTarget
    local_probe = $(if ($null -ne $tcpValidationLocalProbe) { $tcpValidationLocalProbe.probe } else { $null })
    status_code = $(if ($null -ne $tcpValidation) { $tcpValidation.status_code } else { $null })
    minimum_tcp_validation = $backendSession.minimum_tcp_validation
  }

  $currentStep = "backend_get_session"
  $backendFinal = Invoke-Api -Method "GET" -Uri "$backendBaseUrl$backendApiPrefix/seller/onboarding/sessions/$sessionId" -Headers $backendHeaders
  $backendSession = Refresh-LocalOnboardingSession -Headers $headers
  $result.steps.backend_get_session = [ordered]@{
    status_code = $backendFinal.status_code
    session_id = $backendFinal.json.session_id
    status = $backendFinal.json.status
    manager_acceptance = $backendFinal.json.manager_acceptance
    effective_target_addr = $backendFinal.json.effective_target_addr
    effective_target_source = $backendFinal.json.effective_target_source
    truth_authority = $backendFinal.json.truth_authority
    minimum_tcp_validation = $backendFinal.json.minimum_tcp_validation
  }

  $workflowSummary = Get-WorkflowOutcomeSummary -SessionPayload $backendFinal.json

  $result.summary = [ordered]@{
    seller_email = $email
    seller_user_id = $login.json.user.id
    session_id = $sessionId
    node_id = [string]$postJoinDockerInfo.Swarm.NodeID
    node_addr = [string]$postJoinDockerInfo.Swarm.NodeAddr
    wg_ip = [string]$postJoinWgIp
    path_outcome = $workflowSummary.path_outcome
    workflow_target_established = $workflowSummary.workflow_target_established
    workflow_target_addr = $workflowSummary.workflow_target_addr
    workflow_target_source = $workflowSummary.workflow_target_source
    raw_manager_target_established = $workflowSummary.raw_manager_target_established
    raw_manager_target_reachable = $workflowSummary.raw_manager_target_reachable
    authoritative_target_established = $workflowSummary.authoritative_target_established
    authoritative_target_reachable = $workflowSummary.authoritative_target_reachable
    minimum_tcp_reachable = $workflowSummary.minimum_tcp_reachable
    manager_acceptance_status = $backendFinal.json.manager_acceptance.status
    observed_manager_node_addr = $backendFinal.json.manager_acceptance.observed_manager_node_addr
    effective_target_addr = $backendFinal.json.effective_target_addr
    effective_target_source = $backendFinal.json.effective_target_source
    truth_authority = $backendFinal.json.truth_authority
    minimum_tcp_validation = $backendFinal.json.minimum_tcp_validation
  }
}
catch {
  $err = $_
  $errorPayload = [ordered]@{
    step = $currentStep
    message = $err.Exception.Message
  }
  if ($err.Exception.PSObject.Properties.Match("Response").Count -gt 0 -and $err.Exception.Response) {
    try {
      $reader = New-Object System.IO.StreamReader($err.Exception.Response.GetResponseStream())
      $body = $reader.ReadToEnd()
      $errorPayload.response_body = $body
    } catch {
    }
  }
  $result.error = $errorPayload
}

$result | ConvertTo-Json -Depth 16 -Compress
