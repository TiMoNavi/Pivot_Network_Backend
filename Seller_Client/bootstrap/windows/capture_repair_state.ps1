param(
  [string]$OutputRoot = "D:\AI\Pivot_Client\seller_client\rollback",
  [string]$HostTunnelName = "wg-seller",
  [string]$UbuntuDistro = "Ubuntu"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$PSNativeCommandUseErrorActionPreference = $false
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "swarm_runtime_common.ps1")

$stamp = Get-Date -Format "yyyyMMddHHmmss"
$outputDir = Join-Path $OutputRoot $stamp
New-Item -ItemType Directory -Force $outputDir | Out-Null

$hostTunnelService = 'WireGuardTunnel$' + $HostTunnelName
$dockerDesktopNetworkPath = Join-Path $outputDir "docker-desktop-network.txt"
$ubuntuNetworkPath = Join-Path $outputDir "ubuntu-network.txt"
$dockerCli = $null
try {
  $dockerCli = Get-DockerCliPath
} catch {
  $dockerCli = $null
}

function Capture-CommandOutput {
  param(
    [string]$Path,
    [scriptblock]$Command
  )

  try {
    (& $Command 2>&1 | Out-String) | Set-Content -Path $Path -Encoding UTF8
  } catch {
    ($_ | Out-String) | Set-Content -Path $Path -Encoding UTF8
  }
}

function Capture-WireGuardConfigArtifact {
  param(
    [string]$ConfigPath,
    [string]$ErrorPath,
    [string]$TunnelName
  )

  try {
    $raw = (& wg showconf $TunnelName 2>&1 | Out-String)
    $trimmed = $raw.Trim()
    $isValid = [bool](
      $trimmed -and
      $trimmed -match '(?m)^\[Interface\]\s*$' -and
      $trimmed -match '(?m)^\s*Address\s*=' -and
      $trimmed -match '(?m)^\s*PrivateKey\s*=' -and
      $trimmed -match '(?m)^\[Peer\]\s*$'
    )

    if ($isValid) {
      $raw | Set-Content -Path $ConfigPath -Encoding ASCII
      return
    }

    $raw | Set-Content -Path $ErrorPath -Encoding UTF8
  } catch {
    ($_ | Out-String) | Set-Content -Path $ErrorPath -Encoding UTF8
  }
}

Capture-WireGuardConfigArtifact -ConfigPath (Join-Path $outputDir "$HostTunnelName.conf") -ErrorPath (Join-Path $outputDir "$HostTunnelName.showconf-error.txt") -TunnelName $HostTunnelName
Capture-CommandOutput -Path (Join-Path $outputDir "wg-show.txt") -Command { wg show }
Capture-CommandOutput -Path (Join-Path $outputDir "docker-contexts.jsonl") -Command {
  if ($dockerCli) {
    & $dockerCli context ls --format "{{json .}}"
  } else {
    throw "docker.exe was not found on PATH or in the standard Docker Desktop install directory."
  }
}
Capture-CommandOutput -Path (Join-Path $outputDir "docker-desktop-swarm.json") -Command {
  if ($dockerCli) {
    & $dockerCli info --format "{{json .Swarm}}"
  } else {
    throw "docker.exe was not found on PATH or in the standard Docker Desktop install directory."
  }
}
wsl.exe -l -v | Set-Content -Path (Join-Path $outputDir "wsl-list.txt") -Encoding UTF8
Capture-CommandOutput -Path $dockerDesktopNetworkPath -Command { wsl.exe -d docker-desktop sh -lc "ip addr; echo ---; ip route" }
Capture-CommandOutput -Path $ubuntuNetworkPath -Command { wsl.exe -d $UbuntuDistro sh -lc "ip addr; echo ---; ip route" }
Get-NetIPAddress | Where-Object { $_.IPAddress -like "10.66.66.*" } |
  Select-Object InterfaceAlias, IPAddress, PrefixLength, AddressFamily |
  ConvertTo-Json -Depth 4 |
  Set-Content -Path (Join-Path $outputDir "windows-addresses.json") -Encoding UTF8
Get-Service com.docker.service, $hostTunnelService -ErrorAction SilentlyContinue |
  Select-Object Status, Name, DisplayName |
  ConvertTo-Json -Depth 4 |
  Set-Content -Path (Join-Path $outputDir "windows-services.json") -Encoding UTF8

[PSCustomObject]@{
  output_dir = $outputDir
  host_tunnel_name = $HostTunnelName
  ubuntu_distro = $UbuntuDistro
  current_default_route = "Windows seller agent + overlay identity + local runtime"
  historical_wsl_route = "Historical WSL substrate diagnostics"
  artifacts = @(
    "$HostTunnelName.conf",
    "$HostTunnelName.showconf-error.txt",
    "wg-show.txt",
    "docker-contexts.jsonl",
    "docker-desktop-swarm.json",
    "wsl-list.txt",
    "docker-desktop-network.txt",
    "ubuntu-network.txt",
    "windows-addresses.json",
    "windows-services.json"
  )
} | ConvertTo-Json -Depth 4
