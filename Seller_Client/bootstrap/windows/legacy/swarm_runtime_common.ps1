$script:LinuxEnginePipe = "\\.\pipe\dockerDesktopLinuxEngine"

function Convert-ToWslPath {
  param([string]$WindowsPath)

  $fullPath = [System.IO.Path]::GetFullPath($WindowsPath)
  $drive = $fullPath.Substring(0, 1).ToLowerInvariant()
  $rest = $fullPath.Substring(2).Replace("\", "/")
  return "/mnt/$drive$rest"
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

function Get-DockerDesktopProbeSample {
  param(
    [string]$Distro,
    [string]$ManagerWireGuardAddress,
    [int[]]$TcpPorts,
    [switch]$IncludeOverlayUdpProbe,
    [int]$OverlayUdpPort = 4789
  )

  $routeResult = Invoke-WslCapture -Distro $Distro -TimeoutSeconds 10 -Script @"
ip route get $ManagerWireGuardAddress || true
"@

  $tcpChecks = [ordered]@{}
  foreach ($port in $TcpPorts) {
    $tcpChecks[[string]$port] = Test-WslTcpPort -Distro $Distro -TargetHost $ManagerWireGuardAddress -Port $port
  }

  $overlayUdpProbe = $null
  if ($IncludeOverlayUdpProbe) {
    $overlayUdpProbe = Test-WslUdpPort -Distro $Distro -TargetHost $ManagerWireGuardAddress -Port $OverlayUdpPort
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
