param(
  [ValidateSet("mirrored", "nat")]
  [string]$NetworkingMode = "mirrored",
  [switch]$DisableFirewall,
  [switch]$SkipShutdown
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$wslConfigPath = Join-Path $HOME ".wslconfig"
$stamp = Get-Date -Format "yyyyMMddHHmmss"
$backupPath = Join-Path $HOME ".wslconfig.runtime-backup-$stamp"

if (Test-Path $wslConfigPath) {
  Copy-Item $wslConfigPath $backupPath -Force
}

$content = @(
  "[wsl2]",
  "memory=4GB",
  "swap=1GB",
  "networkingMode=$NetworkingMode"
)

if ($DisableFirewall) {
  $content += "firewall=false"
}

$content -join "`r`n" | Set-Content -Path $wslConfigPath -Encoding ASCII

if (-not $SkipShutdown) {
  wsl.exe --shutdown
  Start-Sleep -Seconds 3
}

[PSCustomObject]@{
  wslconfig_path = $wslConfigPath
  backup_path = if (Test-Path $backupPath) { $backupPath } else { $null }
  networking_mode = $NetworkingMode
  firewall_disabled = [bool]$DisableFirewall
  current_content = Get-Content -Raw $wslConfigPath
} | ConvertTo-Json -Depth 4
