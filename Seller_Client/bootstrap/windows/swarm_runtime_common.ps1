$script:LinuxEnginePipe = "\\.\pipe\dockerDesktopLinuxEngine"

function Convert-ToWslPath {
  param([string]$WindowsPath)

  $fullPath = [System.IO.Path]::GetFullPath($WindowsPath)
  $drive = $fullPath.Substring(0, 1).ToLowerInvariant()
  $rest = $fullPath.Substring(2).Replace("\", "/")
  return "/mnt/$drive$rest"
}

function Convert-ToDockerDesktopHostPath {
  param([string]$WindowsPath)

  $fullPath = [System.IO.Path]::GetFullPath($WindowsPath)
  $drive = $fullPath.Substring(0, 1).ToLowerInvariant()
  $rest = $fullPath.Substring(2).Replace("\", "/")
  return "/mnt/host/$drive$rest"
}

function Resolve-ExistingFilePath {
  param([string[]]$Candidates)

  foreach ($candidate in ($Candidates | Where-Object { $_ } | Select-Object -Unique)) {
    $resolved = $candidate
    try {
      $resolved = [System.IO.Path]::GetFullPath($candidate)
    } catch {
    }
    if (Test-Path $resolved) {
      return [string]$resolved
    }
  }

  return $null
}

function Test-WireGuardConfigFile {
  param([string]$Path)

  if (-not $Path) {
    return $false
  }

  $resolved = $Path
  try {
    $resolved = [System.IO.Path]::GetFullPath($Path)
  } catch {
  }

  if (-not (Test-Path $resolved)) {
    return $false
  }

  try {
    $content = Get-Content -Path $resolved -Raw -Encoding UTF8 -ErrorAction Stop
  } catch {
    return $false
  }

  if (-not $content) {
    return $false
  }

  $trimmed = $content.Trim()
  if (-not $trimmed) {
    return $false
  }

  if ($trimmed -match 'Unable to access interface: Permission denied') {
    return $false
  }

  return [bool](
    $trimmed -match '(?m)^\[Interface\]\s*$' -and
    $trimmed -match '(?m)^\s*Address\s*=' -and
    $trimmed -match '(?m)^\s*PrivateKey\s*=' -and
    $trimmed -match '(?m)^\[Peer\]\s*$'
  )
}

function Resolve-ExistingWireGuardConfigPath {
  param([string[]]$Candidates)

  foreach ($candidate in ($Candidates | Where-Object { $_ } | Select-Object -Unique)) {
    $resolved = $candidate
    try {
      $resolved = [System.IO.Path]::GetFullPath($candidate)
    } catch {
    }

    if ((Test-Path $resolved) -and (Test-WireGuardConfigFile -Path $resolved)) {
      return [string]$resolved
    }
  }

  return $null
}

function Resolve-ManagerSshKeyPath {
  param(
    [string]$ExplicitPath = "",
    [string]$ProjectRoot = ""
  )

  $candidates = @()
  if ($ExplicitPath) {
    $candidates += $ExplicitPath
  }
  if ($env:SELLER_CLIENT_MANAGER_SSH_KEY_PATH) {
    $candidates += $env:SELLER_CLIENT_MANAGER_SSH_KEY_PATH
  }
  if ($ProjectRoot) {
    $sharedRoot = Split-Path -Parent $ProjectRoot
    $workspaceRoot = Split-Path -Parent $sharedRoot
    $candidates += (Join-Path $ProjectRoot "navi.pem")
    $candidates += (Join-Path $sharedRoot "navi.pem")
    $candidates += (Join-Path $sharedRoot "server_access\navi.pem")
    $candidates += (Join-Path $workspaceRoot "Pivot_backend_build_team\navi.pem")
  }

  $resolved = Resolve-ExistingFilePath -Candidates $candidates
  if ($resolved) {
    return $resolved
  }

  $checked = ($candidates | Where-Object { $_ } | Select-Object -Unique) -join ", "
  if ($checked) {
    throw "Manager SSH key not found. Pass -ManagerSshKeyPath or set SELLER_CLIENT_MANAGER_SSH_KEY_PATH. Checked: $checked"
  }

  throw "Manager SSH key not found. Pass -ManagerSshKeyPath or set SELLER_CLIENT_MANAGER_SSH_KEY_PATH."
}

function Resolve-SellerWireGuardConfigPath {
  param(
    [string]$HostTunnelName = "wg-seller",
    [string]$ExplicitPath = "",
    [string]$ProjectRoot = ""
  )

  $candidates = @()
  if ($ExplicitPath) {
    $candidates += $ExplicitPath
  }
  if ($env:SELLER_CLIENT_WG_CONFIG_PATH) {
    $candidates += $env:SELLER_CLIENT_WG_CONFIG_PATH
  }
  if ($ProjectRoot) {
    $candidates += (Join-Path $ProjectRoot ".cache\seller-zero-flow\wireguard\$HostTunnelName.conf")
  }

  $resolved = Resolve-ExistingWireGuardConfigPath -Candidates $candidates
  if ($resolved) {
    return $resolved
  }

  if ($ProjectRoot) {
    $rollbackRoot = Join-Path $ProjectRoot "rollback"
    if (Test-Path $rollbackRoot) {
      $latestRollback = Get-ChildItem -Path $rollbackRoot -Filter "$HostTunnelName.conf" -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { Test-WireGuardConfigFile -Path $_.FullName } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
      if ($null -ne $latestRollback) {
        return [string]$latestRollback.FullName
      }
    }
  }

  $allowLegacyFallback = [string]$env:SELLER_CLIENT_ALLOW_LEGACY_WG_CONFIG_FALLBACK
  if ($ProjectRoot -and $allowLegacyFallback -eq "1") {
    $legacyPath = Join-Path $ProjectRoot "bootstrap\windows\legacy\root-scripts\ubuntu-$HostTunnelName.conf"
    if (Test-WireGuardConfigFile -Path $legacyPath) {
      return [string]([System.IO.Path]::GetFullPath($legacyPath))
    }
  }

  $checked = ($candidates | Where-Object { $_ } | Select-Object -Unique) -join ", "
  $guidance = "Set SELLER_CLIENT_WG_CONFIG_PATH or seed .cache\seller-zero-flow\wireguard\$HostTunnelName.conf with the machine-specific WireGuard config."
  if ($checked) {
    throw "Seller WireGuard config not found. $guidance Checked: $checked"
  }

  throw "Seller WireGuard config not found. $guidance"
}

function Get-WireGuardInterfaceAddressFromConfig {
  param([string]$ConfigPath)

  if (-not $ConfigPath -or -not (Test-Path $ConfigPath)) {
    return $null
  }

  foreach ($line in (Get-Content -Path $ConfigPath -Encoding UTF8 -ErrorAction SilentlyContinue)) {
    if ($line -match '^\s*Address\s*=\s*(.+?)\s*$') {
      $entries = [string]$Matches[1] -split ','
      if ($entries.Count -gt 0) {
        return ($entries[0]).Trim()
      }
    }
  }

  return $null
}

function Normalize-CapturedText {
  param([string]$Text)

  if ($null -eq $Text) {
    return ""
  }

  $clean = $Text -replace "`0", ""
  $lines = $clean -split "`r?`n" | ForEach-Object { $_.TrimEnd() }
  $filtered = $lines | Where-Object {
    $_ -and
    $_ -notmatch '^\s*wsl:'
  }
  return ($filtered -join "`n").Trim()
}

function Get-DockerCliPath {
  $command = Get-Command docker.exe -ErrorAction SilentlyContinue
  if ($null -ne $command -and $command.Source) {
    return [string]$command.Source
  }

  $candidates = @(
    (Join-Path ${env:ProgramFiles} "Docker\Docker\resources\bin\docker.exe"),
    (Join-Path ${env:ProgramW6432} "Docker\Docker\resources\bin\docker.exe"),
    "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
  ) | Select-Object -Unique

  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path $candidate)) {
      return [string]$candidate
    }
  }

  throw "docker.exe was not found on PATH or in the standard Docker Desktop install directory."
}

function Convert-ToNativeArgumentString {
  param([string[]]$Arguments)

  $rendered = foreach ($argument in $Arguments) {
    if ($null -eq $argument -or $argument -eq "") {
      '""'
      continue
    }

    if ($argument -notmatch '[\s"]') {
      $argument
      continue
    }

    $escaped = $argument -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    '"' + $escaped + '"'
  }

  return ($rendered -join " ").Trim()
}

function Invoke-ExecutableCapture {
  param(
    [string]$FilePath,
    [string[]]$Arguments,
    [int]$TimeoutSeconds = 20
  )

  try {
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FilePath
    $startInfo.Arguments = Convert-ToNativeArgumentString -Arguments $Arguments
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    [void]$process.Start()

    $timedOut = -not $process.WaitForExit($TimeoutSeconds * 1000)
    if ($timedOut) {
      try {
        $process.Kill()
      } catch {
      }
    } else {
      $process.WaitForExit()
    }

    $stdoutRaw = $process.StandardOutput.ReadToEnd()
    $stderrRaw = $process.StandardError.ReadToEnd()

    return [PSCustomObject]@{
      output = Normalize-CapturedText ($stdoutRaw + "`n" + $stderrRaw)
      stdout = Normalize-CapturedText $stdoutRaw
      stderr = Normalize-CapturedText $stderrRaw
      exit_code = if ($timedOut) { -1 } else { $process.ExitCode }
      timed_out = $timedOut
      start_ok = $true
    }
  } catch {
    return [PSCustomObject]@{
      output = Normalize-CapturedText ([string]$_.Exception.Message)
      stdout = ""
      stderr = Normalize-CapturedText ([string]$_.Exception.Message)
      exit_code = $null
      timed_out = $false
      start_ok = $false
    }
  }
}

function Invoke-DockerCliCapture {
  param(
    [string[]]$Arguments,
    [int]$TimeoutSeconds = 20
  )

  return Invoke-ExecutableCapture -FilePath (Get-DockerCliPath) -Arguments $Arguments -TimeoutSeconds $TimeoutSeconds
}

function Invoke-CmdCapture {
  param(
    [string]$Command,
    [int]$TimeoutSeconds
  )

  $tempPath = Join-Path $env:TEMP ("cmd-capture-" + [guid]::NewGuid().ToString("N") + ".log")
  $process = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "$Command > ""$tempPath"" 2>&1" -PassThru -WindowStyle Hidden
  $timedOut = -not $process.WaitForExit($TimeoutSeconds * 1000)
  if ($timedOut) {
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
  }
  $rawOutput = if (Test-Path $tempPath) { Get-Content -Raw $tempPath } else { "" }
  Remove-Item $tempPath -Force -ErrorAction SilentlyContinue
  $output = if ($null -eq $rawOutput) { "" } else { [string]$rawOutput }

  [PSCustomObject]@{
    output = Normalize-CapturedText $output
    exit_code = if ($timedOut) { -1 } else { $process.ExitCode }
    timed_out = $timedOut
  }
}

function Invoke-WslCapture {
  param(
    [string]$Distro,
    [string]$Script,
    [int]$TimeoutSeconds = 20
  )

  $encoded = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($Script))
  $command = "wsl.exe -d $Distro -- sh -lc ""printf '%s' '$encoded' | base64 -d | sh"""
  return Invoke-CmdCapture -Command $command -TimeoutSeconds $TimeoutSeconds
}

function Invoke-DockerDesktopDaemonCapture {
  param(
    [string]$Distro,
    [string]$Script,
    [int]$TimeoutSeconds = 20
  )

  $wrapped = @"
set -eu
pid=`$(pidof dockerd | awk '{print `$1}')
if [ -z "`$pid" ]; then
  echo dockerd-pid-missing
  exit 1
fi
nsenter -t "`$pid" -n sh <<'INNER'
$Script
INNER
"@

  return Invoke-WslCapture -Distro $Distro -Script $wrapped -TimeoutSeconds $TimeoutSeconds
}

function Test-TcpPort {
  param(
    [string]$TargetHost,
    [int]$Port,
    [int]$TimeoutMilliseconds = 3000
  )

  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $result = $client.BeginConnect($TargetHost, $Port, $null, $null)
    $reachable = $result.AsyncWaitHandle.WaitOne($TimeoutMilliseconds, $false)
    if ($reachable) {
      $client.EndConnect($result)
    }
    return [ordered]@{
      host = $TargetHost
      port = $Port
      reachable = $reachable
      timeout_ms = $TimeoutMilliseconds
    }
  } catch {
    return [ordered]@{
      host = $TargetHost
      port = $Port
      reachable = $false
      timeout_ms = $TimeoutMilliseconds
      error = $_.Exception.Message
    }
  } finally {
    $client.Close()
  }
}

function Test-WslTcpPort {
  param(
    [string]$Distro,
    [string]$TargetHost,
    [int]$Port,
    [int]$TimeoutSeconds = 8
  )

  $result = Invoke-WslCapture -Distro $Distro -TimeoutSeconds $TimeoutSeconds -Script @"
if command -v nc >/dev/null 2>&1; then
  nc -vz -w 3 $TargetHost $Port
else
  echo nc-unavailable
  exit 127
fi
"@

  [ordered]@{
    host = $TargetHost
    port = $Port
    reachable = (-not $result.timed_out) -and ($result.exit_code -eq 0)
    exit_code = $result.exit_code
    timed_out = $result.timed_out
    detail = $result.output
  }
}

function Test-WslUdpPort {
  param(
    [string]$Distro,
    [string]$TargetHost,
    [int]$Port,
    [int]$TimeoutSeconds = 8
  )

  $result = Invoke-WslCapture -Distro $Distro -TimeoutSeconds $TimeoutSeconds -Script @"
if command -v nc >/dev/null 2>&1; then
  nc -vzu -w 1 $TargetHost $Port
else
  echo nc-unavailable
  exit 127
fi
"@

  [ordered]@{
    host = $TargetHost
    port = $Port
    attempted = (-not $result.timed_out) -and ($result.exit_code -ne 127)
    exit_code = $result.exit_code
    timed_out = $result.timed_out
    detail = $result.output
  }
}

function Test-DockerDesktopDaemonTcpPort {
  param(
    [string]$Distro,
    [string]$TargetHost,
    [int]$Port,
    [int]$TimeoutSeconds = 8
  )

  $result = Invoke-DockerDesktopDaemonCapture -Distro $Distro -TimeoutSeconds $TimeoutSeconds -Script @"
if command -v nc >/dev/null 2>&1; then
  nc -vz -w 3 $TargetHost $Port
else
  echo nc-unavailable
  exit 127
fi
"@

  [ordered]@{
    host = $TargetHost
    port = $Port
    reachable = (-not $result.timed_out) -and ($result.exit_code -eq 0)
    exit_code = $result.exit_code
    timed_out = $result.timed_out
    detail = $result.output
  }
}

function Test-DockerDesktopDaemonUdpPort {
  param(
    [string]$Distro,
    [string]$TargetHost,
    [int]$Port,
    [int]$TimeoutSeconds = 8
  )

  $result = Invoke-DockerDesktopDaemonCapture -Distro $Distro -TimeoutSeconds $TimeoutSeconds -Script @"
if command -v nc >/dev/null 2>&1; then
  nc -vzu -w 1 $TargetHost $Port
else
  echo nc-unavailable
  exit 127
fi
"@

  [ordered]@{
    host = $TargetHost
    port = $Port
    attempted = (-not $result.timed_out) -and ($result.exit_code -ne 127)
    exit_code = $result.exit_code
    timed_out = $result.timed_out
    detail = $result.output
  }
}

function Ensure-DockerDesktopWireGuardTools {
  param(
    [string]$Distro = "docker-desktop"
  )

  $check = Invoke-WslCapture -Distro $Distro -TimeoutSeconds 12 -Script @'
if command -v wg >/dev/null 2>&1 && command -v ip >/dev/null 2>&1 && command -v nsenter >/dev/null 2>&1; then
  echo ready
else
  echo missing
fi
'@

  if ($check.exit_code -eq 0 -and $check.output -eq "ready") {
    return [ordered]@{
      ready = $true
      installed = $false
      output = $check.output
      exit_code = $check.exit_code
      timed_out = $check.timed_out
    }
  }

  $install = Invoke-WslCapture -Distro $Distro -TimeoutSeconds 120 -Script @'
apk add --no-cache wireguard-tools >/dev/null
'@

  return [ordered]@{
    ready = (-not $install.timed_out) -and ($install.exit_code -eq 0)
    installed = $true
    output = $install.output
    exit_code = $install.exit_code
    timed_out = $install.timed_out
  }
}

function Get-DockerDesktopDaemonWireGuardSample {
  param(
    [string]$Distro = "docker-desktop",
    [string]$InterfaceName = "wg-seller",
    [string]$ManagerWireGuardAddress = "",
    [int[]]$TcpPorts = @(2377, 7946)
  )

  $interfaceResult = Invoke-DockerDesktopDaemonCapture -Distro $Distro -TimeoutSeconds 12 -Script @"
ip -o -4 addr show dev $InterfaceName || true
"@
  $wgResult = Invoke-DockerDesktopDaemonCapture -Distro $Distro -TimeoutSeconds 12 -Script @"
if command -v wg >/dev/null 2>&1; then
  wg show $InterfaceName || true
else
  echo wg-unavailable
fi
"@

  $routeResult = $null
  if ($ManagerWireGuardAddress) {
    $routeResult = Invoke-DockerDesktopDaemonCapture -Distro $Distro -TimeoutSeconds 12 -Script @"
ip route get $ManagerWireGuardAddress || true
"@
  } else {
    $routeResult = [pscustomobject]@{
      output = ""
      exit_code = 0
      timed_out = $false
    }
  }

  $tcpChecks = [ordered]@{}
  foreach ($port in $TcpPorts) {
    $tcpChecks[[string]$port] = Test-DockerDesktopDaemonTcpPort -Distro $Distro -TargetHost $ManagerWireGuardAddress -Port $port
  }

  $allTcpPortsReachable = $true
  foreach ($entry in $tcpChecks.GetEnumerator()) {
    if (-not $entry.Value.reachable) {
      $allTcpPortsReachable = $false
      break
    }
  }

  $addressPresent = $false
  $matchedInterface = $null
  $observedAddress = $null
  if ($interfaceResult.output -match '^\d+:\s+([^ ]+)\s+inet\s+([0-9\.]+/\d+)') {
    $matchedInterface = [string]$Matches[1]
    $observedAddress = [string]$Matches[2]
    $addressPresent = $true
  }

  [ordered]@{
    captured_at = (Get-Date).ToString("o")
    distro = $Distro
    interface_name = $InterfaceName
    address_present = $addressPresent
    observed_address = $observedAddress
    matched_interface = $matchedInterface
    route_get_manager = $routeResult.output
    route_exit_code = $routeResult.exit_code
    route_timed_out = $routeResult.timed_out
    tcp_checks = $tcpChecks
    all_tcp_ports_reachable = $allTcpPortsReachable
    wg_show = $wgResult.output
    wg_exit_code = $wgResult.exit_code
    wg_timed_out = $wgResult.timed_out
  }
}

function Ensure-DockerDesktopDaemonWireGuardInterface {
  param(
    [string]$Distro = "docker-desktop",
    [string]$HostTunnelName = "wg-seller",
    [string]$ManagerWireGuardAddress = "",
    [string]$InterfaceAddressCidr = "",
    [string]$WireGuardConfigPath = "",
    [string]$ProjectRoot = ""
  )

  $beforeSample = Get-DockerDesktopDaemonWireGuardSample `
    -Distro $Distro `
    -InterfaceName $HostTunnelName `
    -ManagerWireGuardAddress $ManagerWireGuardAddress

  if ($beforeSample.address_present -and $beforeSample.all_tcp_ports_reachable) {
    return [ordered]@{
      action = "already_ready"
      changed = $false
      config_path = $null
      interface_address_cidr = if ($InterfaceAddressCidr) { $InterfaceAddressCidr } else { $beforeSample.observed_address }
      tool_install = $null
      apply = $null
      before = $beforeSample
      after = $beforeSample
    }
  }

  $toolInstall = Ensure-DockerDesktopWireGuardTools -Distro $Distro
  if (-not $toolInstall.ready) {
    throw "Unable to ensure WireGuard tooling inside docker-desktop. Output: $($toolInstall.output)"
  }

  $resolvedConfigPath = Resolve-SellerWireGuardConfigPath `
    -HostTunnelName $HostTunnelName `
    -ExplicitPath $WireGuardConfigPath `
    -ProjectRoot $ProjectRoot
  $resolvedAddress = if ($InterfaceAddressCidr) {
    $InterfaceAddressCidr
  } else {
    Get-WireGuardInterfaceAddressFromConfig -ConfigPath $resolvedConfigPath
  }
  if (-not $resolvedAddress) {
    throw "WireGuard config did not contain an Address entry and no explicit InterfaceAddressCidr was provided: $resolvedConfigPath"
  }

  $dockerDesktopConfigPath = Convert-ToDockerDesktopHostPath $resolvedConfigPath
  $applyScript = @'
set -eu
iface="__IFACE__"
config="__CONFIG__"
addr="__ADDR__"
manager="__MANAGER__"
tmp="$(mktemp)"
awk '
  /^[[:space:]]*Address[[:space:]]*=/ { next }
  /^[[:space:]]*(DNS|MTU|Table|PreUp|PostUp|PreDown|PostDown|SaveConfig)[[:space:]]*=/ { next }
  { print }
' "$config" > "$tmp"
pid=$(pidof dockerd | awk '{print $1}')
nsenter -t "$pid" -n ip link del "$iface" 2>/dev/null || true
nsenter -t "$pid" -n ip link add "$iface" type wireguard
nsenter -t "$pid" -n wg setconf "$iface" "$tmp"
nsenter -t "$pid" -n ip address replace "$addr" dev "$iface"
nsenter -t "$pid" -n ip link set "$iface" up
if [ -n "$manager" ]; then
  nsenter -t "$pid" -n ip route replace "$manager" dev "$iface"
fi
rm -f "$tmp"
'@
  $applyScript = $applyScript.Replace("__IFACE__", $HostTunnelName)
  $applyScript = $applyScript.Replace("__CONFIG__", $dockerDesktopConfigPath)
  $applyScript = $applyScript.Replace("__ADDR__", $resolvedAddress)
  $applyScript = $applyScript.Replace("__MANAGER__", $ManagerWireGuardAddress)

  $applyResult = Invoke-WslCapture -Distro $Distro -TimeoutSeconds 60 -Script $applyScript
  if ($applyResult.exit_code -ne 0 -or $applyResult.timed_out) {
    throw "Failed to provision WireGuard inside dockerd netns. Output: $($applyResult.output)"
  }

  $afterSample = Get-DockerDesktopDaemonWireGuardSample `
    -Distro $Distro `
    -InterfaceName $HostTunnelName `
    -ManagerWireGuardAddress $ManagerWireGuardAddress

  return [ordered]@{
    action = "configured"
    changed = $true
    config_path = $resolvedConfigPath
    interface_address_cidr = $resolvedAddress
    tool_install = $toolInstall
    apply = [ordered]@{
      output = $applyResult.output
      exit_code = $applyResult.exit_code
      timed_out = $applyResult.timed_out
    }
    before = $beforeSample
    after = $afterSample
  }
}

function Get-DockerDesktopProbeSample {
  param(
    [string]$Distro,
    [string]$ManagerWireGuardAddress,
    [int[]]$TcpPorts,
    [switch]$IncludeOverlayUdpProbe,
    [int]$OverlayUdpPort = 4789
  )

  $daemonSample = Get-DockerDesktopDaemonWireGuardSample `
    -Distro $Distro `
    -InterfaceName "wg-seller" `
    -ManagerWireGuardAddress $ManagerWireGuardAddress `
    -TcpPorts $TcpPorts

  $routeResult = [pscustomobject]@{
    output = $daemonSample.route_get_manager
    exit_code = $daemonSample.route_exit_code
    timed_out = $daemonSample.route_timed_out
  }

  $tcpChecks = $daemonSample.tcp_checks

  $overlayUdpProbe = $null
  if ($IncludeOverlayUdpProbe) {
    $overlayUdpProbe = Test-DockerDesktopDaemonUdpPort -Distro $Distro -TargetHost $ManagerWireGuardAddress -Port $OverlayUdpPort
  }

  $allTcpPortsReachable = $true
  foreach ($entry in $tcpChecks.GetEnumerator()) {
    if (-not $entry.Value.reachable) {
      $allTcpPortsReachable = $false
      break
    }
  }

  [ordered]@{
    captured_at = (Get-Date).ToString("o")
    probe_scope = "dockerd_netns"
    daemon_interface_name = $daemonSample.interface_name
    daemon_address_present = $daemonSample.address_present
    daemon_observed_address = $daemonSample.observed_address
    route_get_manager = $routeResult.output
    route_exit_code = $routeResult.exit_code
    route_timed_out = $routeResult.timed_out
    tcp_checks = $tcpChecks
    all_tcp_ports_reachable = $allTcpPortsReachable
    overlay_udp_probe = $overlayUdpProbe
  }
}

function Get-DockerDesktopSoakSummary {
  param(
    [string]$Distro,
    [string]$ManagerWireGuardAddress,
    [int]$SampleCount = 15,
    [int]$IntervalSeconds = 2,
    [switch]$IncludeOverlayUdpProbe,
    [int]$OverlayUdpPort = 4789
  )

  $samples = @()
  for ($index = 0; $index -lt $SampleCount; $index++) {
    $samples += Get-DockerDesktopProbeSample `
      -Distro $Distro `
      -ManagerWireGuardAddress $ManagerWireGuardAddress `
      -TcpPorts @(2377, 7946) `
      -IncludeOverlayUdpProbe:$IncludeOverlayUdpProbe `
      -OverlayUdpPort $OverlayUdpPort
    if ($index -lt ($SampleCount - 1) -and $IntervalSeconds -gt 0) {
      Start-Sleep -Seconds $IntervalSeconds
    }
  }

  $allTcpPortsReachable = $true
  foreach ($sample in $samples) {
    if (-not $sample.all_tcp_ports_reachable) {
      $allTcpPortsReachable = $false
      break
    }
  }

  [ordered]@{
    distro = $Distro
    sample_count = $SampleCount
    interval_seconds = $IntervalSeconds
    include_overlay_udp_probe = [bool]$IncludeOverlayUdpProbe
    overlay_udp_port = if ($IncludeOverlayUdpProbe) { $OverlayUdpPort } else { $null }
    all_tcp_ports_reachable = $allTcpPortsReachable
    samples = $samples
  }
}

function Get-WorkflowOutcomeSummary {
  param(
    $SessionPayload,
    $LocalSwarmInfo = $null
  )

  $managerAcceptance = $null
  $managerAcceptanceStatus = $null
  $observedManagerNodeAddr = $null
  $effectiveTargetAddr = $null
  $effectiveTargetSource = $null
  $truthAuthority = $null
  $localSwarmState = $null

  if ($null -ne $SessionPayload) {
    $managerAcceptance = $SessionPayload.manager_acceptance
    $effectiveTargetAddr = [string]$SessionPayload.effective_target_addr
    $effectiveTargetSource = [string]$SessionPayload.effective_target_source
    $truthAuthority = [string]$SessionPayload.truth_authority
  }
  if ($null -ne $LocalSwarmInfo) {
    $localSwarmState = [string]$LocalSwarmInfo.LocalNodeState
  }

  if ($null -ne $managerAcceptance) {
    $managerAcceptanceStatus = [string]$managerAcceptance.status
    $observedManagerNodeAddr = [string]$managerAcceptance.observed_manager_node_addr
  }

  $managerAcceptanceMatched = $managerAcceptanceStatus -eq "matched"
  $rawTargetEstablished = ($managerAcceptanceStatus -eq "matched") -and -not [string]::IsNullOrWhiteSpace($observedManagerNodeAddr)
  $authoritativeTargetEstablished = ($truthAuthority -eq "backend_correction") -and -not [string]::IsNullOrWhiteSpace($effectiveTargetAddr)
  $localSwarmActive = $localSwarmState -eq "active"
  $swarmConnectivityVerified = $localSwarmActive -and $rawTargetEstablished

  $workflowTargetEstablished = $false
  $workflowTargetAddr = $null
  $workflowTargetSource = $null
  if ($rawTargetEstablished) {
    $workflowTargetEstablished = $true
    $workflowTargetAddr = $observedManagerNodeAddr
    $workflowTargetSource = "raw_manager"
  } elseif ($authoritativeTargetEstablished) {
    $workflowTargetEstablished = $true
    $workflowTargetAddr = $effectiveTargetAddr
    $workflowTargetSource = if ([string]::IsNullOrWhiteSpace($effectiveTargetSource)) {
      "backend_correction"
    } else {
      $effectiveTargetSource
    }
  }

  $pathOutcome = "incomplete"
  if ($swarmConnectivityVerified) {
    $pathOutcome = "swarm_manager_verified"
  } elseif ($rawTargetEstablished) {
    $pathOutcome = "manager_matched_local_pending"
  } elseif ($authoritativeTargetEstablished) {
    $pathOutcome = "backend_override_only"
  }

  return [ordered]@{
    success_standard = "docker_swarm_connectivity"
    path_outcome = $pathOutcome
    swarm_connectivity_verified = [bool]$swarmConnectivityVerified
    local_swarm_active = [bool]$localSwarmActive
    manager_acceptance_matched = [bool]$managerAcceptanceMatched
    workflow_target_established = $workflowTargetEstablished
    workflow_target_addr = $workflowTargetAddr
    workflow_target_source = $workflowTargetSource
    raw_manager_target_established = [bool]$rawTargetEstablished
    raw_manager_target_reachable = [bool]$rawTargetEstablished
    authoritative_target_established = [bool]$authoritativeTargetEstablished
    authoritative_target_reachable = [bool]$authoritativeTargetEstablished
    minimum_tcp_reachable = $null
  }
}
