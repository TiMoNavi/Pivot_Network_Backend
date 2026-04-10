param(
  [string]$HostTunnelName = "wg-seller",
  [string]$UbuntuDistro = "Ubuntu",
  [string]$AddressCidr = "10.66.66.10/32",
  [string]$OutputDir = "D:\AI\Pivot_Client\seller_client"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$hostTunnelService = 'WireGuardTunnel$' + $HostTunnelName
$hostConfigPath = Join-Path $OutputDir "ubuntu-$HostTunnelName.conf"
$linuxConfigPath = "/etc/wireguard/$HostTunnelName.conf"
$drive = $OutputDir.Substring(0, 1).ToLowerInvariant()
$tail = $OutputDir.Substring(2).Replace('\', '/')
$linuxSourceDir = "/mnt/$drive$tail"
$linuxSourcePath = "$linuxSourceDir/ubuntu-$HostTunnelName.conf"

$hostConfig = wg showconf $HostTunnelName
$lines = $hostConfig -split "`r?`n"
$rendered = New-Object System.Collections.Generic.List[string]
$addressInserted = $false
foreach ($line in $lines) {
  $rendered.Add($line)
  if (-not $addressInserted -and $line -eq "[Interface]") {
    $rendered.Add("Address = $AddressCidr")
    $addressInserted = $true
  }
}
$rendered -join "`r`n" | Set-Content -Path $hostConfigPath -Encoding ASCII

wsl.exe -d $UbuntuDistro sh -lc "mkdir -p /etc/wireguard && install -m 600 $linuxSourcePath $linuxConfigPath"

$service = Get-Service $hostTunnelService -ErrorAction SilentlyContinue
if ($null -eq $service) {
  throw "Windows WireGuard service $hostTunnelService not found."
}
if ($service.Status -ne "Stopped") {
  Stop-Service -Name $hostTunnelService -Force -ErrorAction Stop
}

wsl.exe -d $UbuntuDistro sh -lc "systemctl enable --now wg-quick@$HostTunnelName && sleep 2 && wg show && echo --- && ip addr show $HostTunnelName"

[PSCustomObject]@{
  host_tunnel_name = $HostTunnelName
  host_service = $hostTunnelService
  windows_service_status = (Get-Service $hostTunnelService).Status
  host_config_path = $hostConfigPath
  linux_source_path = $linuxSourcePath
  linux_config_path = $linuxConfigPath
  ubuntu_distro = $UbuntuDistro
  address_cidr = $AddressCidr
} | ConvertTo-Json -Depth 4
