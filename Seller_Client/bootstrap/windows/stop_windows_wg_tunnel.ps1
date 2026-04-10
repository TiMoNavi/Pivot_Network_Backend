param(
  [string]$HostTunnelName = "wg-seller",
  [switch]$DisableStartup
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$serviceName = 'WireGuardTunnel$' + $HostTunnelName
$service = Get-Service $serviceName -ErrorAction SilentlyContinue
if ($null -eq $service) {
  throw "Windows WireGuard service $serviceName not found."
}

if ($service.Status -ne "Stopped") {
  Stop-Service -Name $serviceName -Force -ErrorAction Stop
}

if ($DisableStartup) {
  Set-Service -Name $serviceName -StartupType Disabled -ErrorAction Stop
}

$service = Get-Service -Name $serviceName
$serviceConfig = Get-CimInstance Win32_Service -Filter "Name='$serviceName'"

[PSCustomObject]@{
  status = [string]$service.Status
  name = $service.Name
  display_name = $service.DisplayName
  start_mode = if ($null -ne $serviceConfig) { [string]$serviceConfig.StartMode } else { $null }
  state = if ($null -ne $serviceConfig) { [string]$serviceConfig.State } else { $null }
} | ConvertTo-Json -Depth 4
