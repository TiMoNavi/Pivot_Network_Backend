param(
  [string]$HostTunnelName = "wg-seller",
  [int]$LocalAppPort = 8901,
  [string]$ManagerWireGuardAddress = "10.66.66.1",
  [string]$ManagerPublicAddress = "81.70.52.75",
  [int]$ManagerSshPort = 22,
  [int]$ManagerSwarmPort = 2377,
  [int]$SwarmGossipPort = 7946,
  [int]$SwarmOverlayPort = 4789,
  [string]$UbuntuDistro = "Ubuntu",
  [int]$DockerDesktopSoakSampleCount = 15,
  [int]$DockerDesktopSoakIntervalSeconds = 2,
  [switch]$IncludeOverlayUdpProbe
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$PSNativeCommandUseErrorActionPreference = $false

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "swarm_runtime_common.ps1")

$serviceName = 'WireGuardTunnel$' + $HostTunnelName
$dockerService = Get-Service com.docker.service -ErrorAction SilentlyContinue
$wireguardService = Get-Service $serviceName -ErrorAction SilentlyContinue
$appListener = Get-NetTCPConnection -LocalPort $LocalAppPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1

function Capture-Text {
  param([scriptblock]$Command)
  try {
    return (& $Command 2>&1 | Out-String).Trim()
  } catch {
    return ($_ | Out-String).Trim()
  }
}

$managerPorts = @(
  (Test-TcpPort -TargetHost $ManagerWireGuardAddress -Port $ManagerSshPort),
  (Test-TcpPort -TargetHost $ManagerWireGuardAddress -Port $ManagerSwarmPort),
  (Test-TcpPort -TargetHost $ManagerWireGuardAddress -Port $SwarmGossipPort)
)

$routePrefix = "$ManagerWireGuardAddress/32"
$managerRoutes = Get-NetRoute -DestinationPrefix $routePrefix -ErrorAction SilentlyContinue |
  Select-Object ifIndex, InterfaceAlias, DestinationPrefix, NextHop, RouteMetric

$windowsOverlayAddresses = Get-NetIPAddress -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -like "10.66.66.*" } |
  Select-Object InterfaceAlias, IPAddress, PrefixLength, AddressFamily

$rootStatus = $null
try {
  $rootResponse = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$LocalAppPort/"
  $rootStatus = [ordered]@{
    status_code = [int]$rootResponse.StatusCode
    has_shell = $rootResponse.Content.Contains("卖家接入本地外壳")
  }
} catch {
  $rootStatus = [ordered]@{
    status_code = $null
    has_shell = $false
    error = $_.Exception.Message
  }
}

$dockerContexts = Invoke-CmdCapture -Command 'docker context ls --format "{{json .}}"' -TimeoutSeconds 6
$dockerSwarm = Invoke-CmdCapture -Command 'docker info --format "{{json .Swarm}}"' -TimeoutSeconds 8
$dockerDesktopListeners = Invoke-WslCapture -Distro "docker-desktop" -TimeoutSeconds 10 -Script "(command -v ss >/dev/null && ss -lntup) || (command -v netstat >/dev/null && netstat -lntup) || true"
$dockerDesktopPublicRoute = Invoke-WslCapture -Distro "docker-desktop" -TimeoutSeconds 10 -Script "ip route get $ManagerPublicAddress || true"
$dockerDesktopSoak = Get-DockerDesktopSoakSummary `
  -Distro "docker-desktop" `
  -ManagerWireGuardAddress $ManagerWireGuardAddress `
  -SampleCount $DockerDesktopSoakSampleCount `
  -IntervalSeconds $DockerDesktopSoakIntervalSeconds `
  -IncludeOverlayUdpProbe:$IncludeOverlayUdpProbe `
  -OverlayUdpPort $SwarmOverlayPort

$latestDockerDesktopSample = $null
if ($dockerDesktopSoak.samples.Count -gt 0) {
  $latestDockerDesktopSample = $dockerDesktopSoak.samples[-1]
}

$ubuntuManagerRoute = Invoke-WslCapture -Distro $UbuntuDistro -TimeoutSeconds 10 -Script "ip route get $ManagerWireGuardAddress || true"
$ubuntuManagerSsh = Invoke-WslCapture -Distro $UbuntuDistro -TimeoutSeconds 10 -Script "(command -v nc >/dev/null && nc -vz -w 3 $ManagerWireGuardAddress $ManagerSshPort) || true"

[PSCustomObject]@{
  route = "Windows seller agent + overlay identity + local runtime"
  docker_service = if ($dockerService) {
    [ordered]@{ status = [string]$dockerService.Status; name = $dockerService.Name }
  } else {
    $null
  }
  wireguard_service = if ($wireguardService) {
    [ordered]@{ status = [string]$wireguardService.Status; name = $wireguardService.Name }
  } else {
    $null
  }
  windows_overlay = [ordered]@{
    manager_wireguard_address = $ManagerWireGuardAddress
    manager_public_address = $ManagerPublicAddress
    manager_routes = $managerRoutes
    overlay_addresses = $windowsOverlayAddresses
    manager_port_checks = $managerPorts
  }
  local_app = [ordered]@{
    port = $LocalAppPort
    listening = [bool]$appListener
    root = $rootStatus
  }
  docker_contexts = $dockerContexts
  docker_swarm = $dockerSwarm
  docker_desktop = [ordered]@{
    route_get_manager = if ($latestDockerDesktopSample) { $latestDockerDesktopSample.route_get_manager } else { $null }
    route_get_public_manager = $dockerDesktopPublicRoute.output
    listeners = $dockerDesktopListeners.output
    manager_connectivity = if ($latestDockerDesktopSample) { $latestDockerDesktopSample.tcp_checks } else { $null }
    soak_summary = $dockerDesktopSoak
  }
  ubuntu_advanced_mode = [ordered]@{
    distro = $UbuntuDistro
    route_get_manager = $ubuntuManagerRoute.output
    manager_ssh = $ubuntuManagerSsh.output
  }
  windows_wireguard = Capture-Text { wg show }
  wsl_distros = (wsl.exe -l -v | Out-String).Trim()
} | ConvertTo-Json -Depth 8
