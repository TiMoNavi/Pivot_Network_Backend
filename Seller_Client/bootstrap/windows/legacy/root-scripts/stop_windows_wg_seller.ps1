$ErrorActionPreference = 'Stop'
$service = Get-Service | Where-Object { $_.Name -eq 'WireGuardTunnel$wg-seller' }
if ($null -eq $service) {
  throw 'WireGuardTunnel$wg-seller service not found'
}
if ($service.Status -ne 'Stopped') {
  Stop-Service -Name $service.Name -Force -ErrorAction Stop
}
Get-Service -Name $service.Name | Select-Object Status,Name,DisplayName | ConvertTo-Json -Compress
