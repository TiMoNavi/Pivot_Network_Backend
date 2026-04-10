param(
  [string]$HostTunnelName = "wg-seller",
  [string]$WireGuardConfigPath = "",
  [string]$AuthorizedKeysPath = "C:\ProgramData\ssh\administrators_authorized_keys",
  [string]$ServerPublicKey = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMxgehB7YXdfgkapPJqo6HOKJob2vZM0Ae0UKcpLNUWH root@tencent-to-win-10.66.66.10",
  [string]$RollbackRoot = "D:\AI\Pivot_Client\seller_client\rollback",
  [switch]$SkipRollbackCapture,
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$PSNativeCommandUseErrorActionPreference = $false

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$wgExe = "C:\Program Files\WireGuard\wireguard.exe"
$serviceName = 'WireGuardTunnel$' + $HostTunnelName

function Test-IsAdmin {
  $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Resolve-WireGuardConfigPath {
  param([string]$Candidate)

  $candidates = @()
  if ($Candidate) {
    $candidates += $Candidate
  }
  if ($env:SELLER_CLIENT_WG_CONFIG_PATH) {
    $candidates += $env:SELLER_CLIENT_WG_CONFIG_PATH
  }
  $candidates += (Join-Path $ProjectRoot ".cache\seller-zero-flow\wireguard\$HostTunnelName.conf")

  foreach ($path in $candidates) {
    if ($path -and (Test-Path $path)) {
      return $path
    }
  }

  throw "WireGuard config not found. Pass -WireGuardConfigPath or set SELLER_CLIENT_WG_CONFIG_PATH."
}

function Get-WireGuardConfigCandidates {
  param([string]$Candidate)

  $candidates = @()
  if ($Candidate) {
    $candidates += $Candidate
  }
  if ($env:SELLER_CLIENT_WG_CONFIG_PATH) {
    $candidates += $env:SELLER_CLIENT_WG_CONFIG_PATH
  }
  $candidates += (Join-Path $ProjectRoot ".cache\seller-zero-flow\wireguard\$HostTunnelName.conf")
  return $candidates | Where-Object { $_ } | Select-Object -Unique
}

$captureScript = Join-Path $ScriptDir "capture_repair_state.ps1"
$rollbackOutput = $null
$configCandidates = Get-WireGuardConfigCandidates -Candidate $WireGuardConfigPath
$existingConfig = $null
foreach ($candidate in $configCandidates) {
  if (Test-Path $candidate) {
    $existingConfig = $candidate
    break
  }
}

if (-not $SkipRollbackCapture -and (Test-Path $captureScript)) {
  try {
    $rollbackJson = & $captureScript -OutputRoot $RollbackRoot -HostTunnelName $HostTunnelName
    $rollbackOutput = ($rollbackJson | Out-String).Trim()
  } catch {
    $rollbackOutput = "rollback_capture_failed: $($_.Exception.Message)"
  }
}

if ($DryRun) {
  [PSCustomObject]@{
    host_tunnel_name = $HostTunnelName
    project_root = $ProjectRoot
    wireguard_exe = $wgExe
    wireguard_exe_exists = (Test-Path $wgExe)
    wireguard_config_path = $existingConfig
    wireguard_config_candidates = $configCandidates
    wireguard_config_exists = [bool]$existingConfig
    authorized_keys_path = $AuthorizedKeysPath
    rollback_capture = $rollbackOutput
  } | ConvertTo-Json -Depth 5
  exit 0
}

if (-not (Test-IsAdmin)) {
  throw "Administrator privileges are required."
}

$effectiveConfigPath = Resolve-WireGuardConfigPath -Candidate $WireGuardConfigPath

if (-not (Test-Path $wgExe)) {
  throw "WireGuard not found: $wgExe"
}

Set-Service -Name sshd -StartupType Automatic
Start-Service sshd

if ($ServerPublicKey) {
  New-Item -ItemType File -Force -Path $AuthorizedKeysPath | Out-Null
  $existingLines = @()
  if (Test-Path $AuthorizedKeysPath) {
    $existingLines = @(Get-Content -Path $AuthorizedKeysPath -ErrorAction SilentlyContinue)
  }
  if ($existingLines -notcontains $ServerPublicKey) {
    $existingLines += $ServerPublicKey
  }
  Set-Content -Path $AuthorizedKeysPath -Value $existingLines -Encoding ascii
  icacls $AuthorizedKeysPath /inheritance:r | Out-Null
  icacls $AuthorizedKeysPath /grant:r "Administrators:F" "SYSTEM:F" | Out-Null
}

$existingTunnel = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($existingTunnel) {
  & $wgExe /uninstalltunnelservice $HostTunnelName | Out-Null
  Start-Sleep -Seconds 2
}

& $wgExe /installtunnelservice $effectiveConfigPath | Out-Null

$deadline = (Get-Date).AddSeconds(20)
$wgAddress = $null
do {
  $wgAddress = Get-NetIPAddress -InterfaceAlias $HostTunnelName -AddressFamily IPv4 -ErrorAction SilentlyContinue
  if ($wgAddress) {
    break
  }
  Start-Sleep -Seconds 1
} while ((Get-Date) -lt $deadline)

[PSCustomObject]@{
  host_tunnel_name = $HostTunnelName
  wireguard_config_path = $effectiveConfigPath
  rollback_capture = $rollbackOutput
  services = Get-Service -Name sshd, $serviceName -ErrorAction SilentlyContinue |
    Select-Object Name, Status, StartType
  wg_address = if ($wgAddress) {
    $wgAddress | Select-Object InterfaceAlias, IPAddress, PrefixLength
  } else {
    $null
  }
} | ConvertTo-Json -Depth 6
