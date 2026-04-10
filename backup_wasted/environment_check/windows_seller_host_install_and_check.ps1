param(
  [ValidateSet("check", "install", "all")]
  [string]$Mode = "all",

  [string]$BackendHealthUrl = "https://pivotcompute.store/api/v1/health",

  [string]$UbuntuDistribution = "Ubuntu",

  [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$SwarmManagerHost = "10.66.66.1"
$SwarmManagerPort = 2377
$UbuntuWorkspaceRoot = "/opt/pivot/workspace"

if (-not $OutputPath) {
  $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $OutputPath = Join-Path $ScriptRoot "seller-windows-host-check-$timestamp.json"
}

function New-CheckResult {
  param(
    [string]$Name,
    [string]$Title,
    [string]$Category,
    [string]$Status,
    [bool]$Blocking,
    [string]$Detail,
    [string]$Hint,
    [hashtable]$Data = @{}
  )

  return [ordered]@{
    name = $Name
    title = $Title
    category = $Category
    status = $Status
    blocking = $Blocking
    detail = $Detail
    hint = $Hint
    data = $Data
  }
}

function Invoke-CheckedCommand {
  param(
    [string]$FilePath,
    [string[]]$Arguments = @()
  )

  try {
    $global:LASTEXITCODE = 0
    $output = & $FilePath @Arguments 2>&1
    $text = (($output | Out-String) -replace "`0", "").Trim()
    return [ordered]@{
      ok = ($LASTEXITCODE -eq 0 -or $null -eq $LASTEXITCODE)
      output = $text
    }
  }
  catch {
    return [ordered]@{
      ok = $false
      output = $_.Exception.Message
    }
  }
}

function Invoke-UbuntuCommand {
  param(
    [string]$DistributionName,
    [string]$Command,
    [string]$User = ""
  )

  $arguments = @("-d", $DistributionName)
  if ($User) {
    $arguments += @("--user", $User)
  }
  $arguments += @("--", "bash", "-lc", $Command)
  return Invoke-CheckedCommand -FilePath "wsl.exe" -Arguments $arguments
}

function Get-CommandPath {
  param([string[]]$Candidates)

  foreach ($candidate in $Candidates) {
    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($command) {
      return $command.Source
    }
  }
  return $null
}

function Test-IsAdmin {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-Python311 {
  $pythonPath = Get-CommandPath -Candidates @("python", "py")
  if (-not $pythonPath) {
    return [ordered]@{
      ok = $false
      detail = "Python was not found on PATH."
      data = @{}
    }
  }

  $pythonVersionResult = Invoke-CheckedCommand -FilePath $pythonPath -Arguments @("--version")
  $versionText = $pythonVersionResult.output

  if ($pythonPath.ToLower().EndsWith("py.exe")) {
    $pythonVersionResult = Invoke-CheckedCommand -FilePath $pythonPath -Arguments @("-3.11", "--version")
    $versionText = $pythonVersionResult.output
  }

  if (-not $pythonVersionResult.ok) {
    return [ordered]@{
      ok = $false
      detail = $versionText
      data = @{ command = $pythonPath }
    }
  }

  if ($versionText -match "Python 3\.(\d+)") {
    $minor = [int]$Matches[1]
    if ($minor -ge 11) {
      return [ordered]@{
        ok = $true
        detail = $versionText
        data = @{ command = $pythonPath }
      }
    }
  }

  return [ordered]@{
    ok = $false
    detail = "Python 3.11+ is required. Detected: $versionText"
    data = @{ command = $pythonPath }
  }
}

function Get-WslList {
  return Invoke-CheckedCommand -FilePath "wsl.exe" -Arguments @("-l", "-v")
}

function Test-UbuntuDistribution {
  param([string]$DistributionName)

  $wslList = Get-WslList
  if (-not $wslList.ok) {
    return [ordered]@{
      ok = $false
      detail = $wslList.output
      data = @{}
    }
  }

  $present = $false
  foreach ($line in ($wslList.output -split "`r?`n")) {
    if ($line -match [regex]::Escape($DistributionName)) {
      $present = $true
      break
    }
  }

  return [ordered]@{
    ok = $present
    detail = if ($present) { "Detected WSL distribution: $DistributionName" } else { "WSL distribution '$DistributionName' is missing." }
    data = @{ distributions = $wslList.output }
  }
}

function Test-BackendHealth {
  param([string]$Url)

  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -Method Get -TimeoutSec 10
    return [ordered]@{
      ok = ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300)
      detail = "Backend health endpoint reachable: $Url"
      data = @{ status_code = $response.StatusCode }
    }
  }
  catch {
    return [ordered]@{
      ok = $false
      detail = "Backend health endpoint unreachable: $($_.Exception.Message)"
      data = @{ url = $Url }
    }
  }
}

function Test-ServiceState {
  param([string]$ServiceName)

  try {
    $service = Get-Service -Name $ServiceName -ErrorAction Stop
    return [ordered]@{
      found = $true
      status = $service.Status.ToString()
    }
  }
  catch {
    return [ordered]@{
      found = $false
      status = "missing"
    }
  }
}

function Test-UbuntuDependency {
  param(
    [string]$DistributionName,
    [string]$Name,
    [string]$Title,
    [string]$Command,
    [string]$SuccessDetail,
    [string]$Hint,
    [bool]$Blocking = $true,
    [string]$Category = "ubuntu_compute"
  )

  $result = Invoke-UbuntuCommand -DistributionName $DistributionName -Command $Command
  return New-CheckResult `
    -Name $Name `
    -Title $Title `
    -Category $Category `
    -Status $(if ($result.ok) { "pass" } else { "fail" }) `
    -Blocking $Blocking `
    -Detail $(if ($result.ok) { $SuccessDetail } else { $result.output }) `
    -Hint $Hint
}

function Test-UbuntuNetwork {
  param(
    [string]$DistributionName,
    [string]$Name,
    [string]$Title,
    [string]$Command,
    [string]$SuccessDetail,
    [string]$Hint
  )

  $result = Invoke-UbuntuCommand -DistributionName $DistributionName -Command $Command
  return New-CheckResult `
    -Name $Name `
    -Title $Title `
    -Category "network" `
    -Status $(if ($result.ok) { "pass" } else { "warn" }) `
    -Blocking $false `
    -Detail $(if ($result.ok) { $SuccessDetail } else { $result.output }) `
    -Hint $Hint
}

function Get-CheckResults {
  param(
    [string]$HealthUrl,
    [string]$DistributionName
  )

  $windowsHostChecks = @()
  $ubuntuComputeChecks = @()
  $networkChecks = @()
  $platformChecks = @()
  $assistantChecks = @()

  $isAdmin = Test-IsAdmin
  $windowsHostChecks += New-CheckResult `
    -Name "windows_admin" `
    -Title "Administrator Privilege" `
    -Category "windows_host" `
    -Status $(if ($isAdmin) { "pass" } else { "fail" }) `
    -Blocking $true `
    -Detail $(if ($isAdmin) { "Administrator privilege detected." } else { "Please rerun this script from an elevated PowerShell session." }) `
    -Hint "Seller host install/bootstrap requires an elevated PowerShell session."

  $windowsHostChecks += New-CheckResult `
    -Name "powershell" `
    -Title "PowerShell" `
    -Category "windows_host" `
    -Status "pass" `
    -Blocking $true `
    -Detail "Running on PowerShell $($PSVersionTable.PSVersion)" `
    -Hint "PowerShell is the official Windows host automation shell."

  $python = Test-Python311
  $windowsHostChecks += New-CheckResult `
    -Name "python311" `
    -Title "Python 3.11+" `
    -Category "windows_host" `
    -Status $(if ($python.ok) { "pass" } else { "fail" }) `
    -Blocking $true `
    -Detail $python.detail `
    -Hint "Install Python 3.11+ before launching the seller console." `
    -Data $python.data

  $wslList = Get-WslList
  $windowsHostChecks += New-CheckResult `
    -Name "wsl2" `
    -Title "WSL2" `
    -Category "windows_host" `
    -Status $(if ($wslList.ok) { "pass" } else { "fail" }) `
    -Blocking $true `
    -Detail $(if ($wslList.ok) { "WSL is available.`n$($wslList.output)" } else { $wslList.output }) `
    -Hint "Seller compute requires WSL2 and a dedicated Ubuntu distribution." `
    -Data @{ distributions = $wslList.output }

  $ubuntu = Test-UbuntuDistribution -DistributionName $DistributionName
  $windowsHostChecks += New-CheckResult `
    -Name "ubuntu_distribution" `
    -Title "Ubuntu Distribution" `
    -Category "windows_host" `
    -Status $(if ($ubuntu.ok) { "pass" } else { "fail" }) `
    -Blocking $true `
    -Detail $ubuntu.detail `
    -Hint "Install or register the Ubuntu WSL distribution used for seller compute." `
    -Data $ubuntu.data

  $backend = Test-BackendHealth -Url $HealthUrl
  $platformChecks += New-CheckResult `
    -Name "backend_reachability" `
    -Title "Backend Health Reachability" `
    -Category "platform" `
    -Status $(if ($backend.ok) { "pass" } else { "fail" }) `
    -Blocking $true `
    -Detail $backend.detail `
    -Hint "Seller onboarding requires the public Backend control plane to be reachable." `
    -Data $backend.data

  $codexPath = Get-CommandPath -Candidates @("codex", "codex.cmd", "codex.ps1")
  $assistantChecks += New-CheckResult `
    -Name "codex_cli" `
    -Title "Codex CLI" `
    -Category "assistant" `
    -Status $(if ($codexPath) { "pass" } else { "fail" }) `
    -Blocking $true `
    -Detail $(if ($codexPath) { "Detected Codex CLI at $codexPath" } else { "Codex CLI was not found on PATH." }) `
    -Hint "Session-scoped seller assistance depends on Codex CLI." `
    -Data @{ command = $codexPath }

  if ($ubuntu.ok) {
    $ubuntuComputeChecks += Test-UbuntuDependency -DistributionName $DistributionName -Name "ubuntu_python3" -Title "Ubuntu Python 3" -Command "which python3" -SuccessDetail "python3 is available in Ubuntu." -Hint "Ubuntu compute requires python3 for validation helpers."
    $ubuntuComputeChecks += Test-UbuntuDependency -DistributionName $DistributionName -Name "ubuntu_venv" -Title "Ubuntu venv" -Command "python3 -m venv /tmp/pivot-check-venv && test -d /tmp/pivot-check-venv" -SuccessDetail "python3 -m venv is available in Ubuntu." -Hint "Ubuntu compute requires python3-venv."
    $ubuntuComputeChecks += Test-UbuntuDependency -DistributionName $DistributionName -Name "ubuntu_docker_cli" -Title "Ubuntu Docker CLI" -Command "which docker" -SuccessDetail "docker CLI is available in Ubuntu." -Hint "Ubuntu compute must use native Docker CLI."
    $ubuntuComputeChecks += Test-UbuntuDependency -DistributionName $DistributionName -Name "ubuntu_dockerd" -Title "Ubuntu dockerd" -Command "which dockerd" -SuccessDetail "dockerd is available in Ubuntu." -Hint "Ubuntu compute must have native dockerd."
    $ubuntuComputeChecks += Test-UbuntuDependency -DistributionName $DistributionName -Name "ubuntu_wireguard" -Title "Ubuntu WireGuard" -Command "which wg" -SuccessDetail "WireGuard tools are available in Ubuntu." -Hint "Ubuntu compute requires wireguard-tools."
    $ubuntuComputeChecks += Test-UbuntuDependency -DistributionName $DistributionName -Name "ubuntu_workspace_root" -Title "Ubuntu Workspace Root" -Command "mkdir -p $UbuntuWorkspaceRoot && test -d $UbuntuWorkspaceRoot" -SuccessDetail "Ubuntu workspace root is writable." -Hint "Ubuntu compute needs a stable workspace root."

    $networkChecks += Test-UbuntuNetwork -DistributionName $DistributionName -Name "ubuntu_wireguard_interface" -Title "Ubuntu WireGuard Interface" -Command "ip addr show wg-compute" -SuccessDetail "Ubuntu WireGuard interface wg-compute is present." -Hint "If this is missing after bootstrap, WireGuard compute setup has not completed yet."
    $networkChecks += Test-UbuntuNetwork -DistributionName $DistributionName -Name "ubuntu_manager_ssh" -Title "Ubuntu -> Manager SSH" -Command "timeout 10 bash -lc 'cat < /dev/null > /dev/tcp/$SwarmManagerHost/22'" -SuccessDetail "Ubuntu can reach the manager/support host over TCP 22." -Hint "Useful for support path verification."
    $networkChecks += Test-UbuntuNetwork -DistributionName $DistributionName -Name "ubuntu_swarm_manager" -Title "Ubuntu -> Swarm Manager" -Command "timeout 10 bash -lc 'cat < /dev/null > /dev/tcp/$SwarmManagerHost/$SwarmManagerPort'" -SuccessDetail "Ubuntu can reach the Swarm manager port." -Hint "The seller host must reach the Swarm manager over the intended network path."
  }

  $allChecks = @($windowsHostChecks + $ubuntuComputeChecks + $networkChecks + $platformChecks + $assistantChecks)
  $blockingFailures = @($allChecks | Where-Object { $_.blocking -and $_.status -eq "fail" } | ForEach-Object { $_.name })

  return [ordered]@{
    generated_at = (Get-Date).ToString("o")
    mode = $Mode
    backend_health_url = $HealthUrl
    ubuntu_distribution = $DistributionName
    summary = [ordered]@{
      total = $allChecks.Count
      passed = @($allChecks | Where-Object { $_.status -eq "pass" }).Count
      warned = @($allChecks | Where-Object { $_.status -eq "warn" }).Count
      failed = @($allChecks | Where-Object { $_.status -eq "fail" }).Count
      blocking_failures = $blockingFailures
      overall_status = if ($blockingFailures.Count -gt 0) { "fail" } elseif (@($allChecks | Where-Object { $_.status -eq "warn" }).Count -gt 0) { "warn" } else { "pass" }
    }
    windows_host_checks = $windowsHostChecks
    ubuntu_compute_checks = $ubuntuComputeChecks
    network_checks = $networkChecks
    platform_checks = $platformChecks
    assistant_checks = $assistantChecks
    checks = $allChecks
  }
}

function Install-Python311 {
  $winget = Get-CommandPath -Candidates @("winget")
  if (-not $winget) {
    Write-Warning "winget not found. Python 3.11+ must be installed manually."
    return
  }

  Write-Host "[install] attempting Python 3.11 install via winget"
  & $winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
}

function Install-WSLAndUbuntu {
  param([string]$DistributionName)

  Write-Host "[install] attempting WSL install"
  & wsl.exe --install --no-launch

  Write-Host "[install] attempting Ubuntu distribution install: $DistributionName"
  & wsl.exe --install -d $DistributionName --no-launch
}

function Install-CodexCli {
  $npm = Get-CommandPath -Candidates @("npm")
  if (-not $npm) {
    Write-Warning "npm not found. Codex CLI must be installed manually."
    return
  }

  Write-Host "[install] attempting Codex CLI install via npm"
  & $npm install -g @openai/codex
}

function Install-UbuntuBaseDependencies {
  param([string]$DistributionName)

  Write-Host "[install] attempting Ubuntu base dependency install"
  Invoke-UbuntuCommand -DistributionName $DistributionName -User "root" -Command "apt-get update && apt-get install -y python3 python3-venv docker.io wireguard-tools iproute2 iptables" | Out-Null
  Invoke-UbuntuCommand -DistributionName $DistributionName -User "root" -Command "mkdir -p /opt/pivot/workspace /opt/pivot/compute /opt/pivot/logs" | Out-Null
}

function Invoke-InstallPass {
  param(
    [hashtable]$Report,
    [string]$DistributionName
  )

  $failures = @($Report.windows_host_checks + $Report.platform_checks + $Report.assistant_checks + $Report.ubuntu_compute_checks | Where-Object { $_.status -eq "fail" })
  if ($failures.Count -eq 0) {
    Write-Host "[install] no blocking failures detected"
    return
  }

  foreach ($failure in $failures) {
    switch ($failure.name) {
      "python311" { Install-Python311 }
      "wsl2" { Install-WSLAndUbuntu -DistributionName $DistributionName }
      "ubuntu_distribution" { Install-WSLAndUbuntu -DistributionName $DistributionName }
      "codex_cli" { Install-CodexCli }
      "ubuntu_python3" { Install-UbuntuBaseDependencies -DistributionName $DistributionName }
      "ubuntu_venv" { Install-UbuntuBaseDependencies -DistributionName $DistributionName }
      "ubuntu_docker_cli" { Install-UbuntuBaseDependencies -DistributionName $DistributionName }
      "ubuntu_dockerd" { Install-UbuntuBaseDependencies -DistributionName $DistributionName }
      "ubuntu_wireguard" { Install-UbuntuBaseDependencies -DistributionName $DistributionName }
      "ubuntu_workspace_root" { Install-UbuntuBaseDependencies -DistributionName $DistributionName }
      default {
        Write-Warning "[install] no automated remediation for $($failure.name): $($failure.hint)"
      }
    }
  }
}

function Write-CheckTable {
  param(
    [string]$Title,
    [object[]]$Items
  )

  Write-Host ""
  Write-Host "== $Title =="
  $Items |
    Select-Object title, category, status, blocking, detail |
    Format-Table -Wrap -AutoSize
}

function Write-Report {
  param([hashtable]$Report)

  $json = $Report | ConvertTo-Json -Depth 8
  Set-Content -Path $OutputPath -Value $json -Encoding UTF8

  Write-CheckTable -Title "Windows Host Checks" -Items $Report.windows_host_checks
  Write-CheckTable -Title "Ubuntu Compute Checks" -Items $Report.ubuntu_compute_checks
  Write-CheckTable -Title "Network Checks" -Items $Report.network_checks
  Write-CheckTable -Title "Platform Checks" -Items $Report.platform_checks
  Write-CheckTable -Title "Assistant Checks" -Items $Report.assistant_checks

  Write-Host ""
  Write-Host "Overall status: $($Report.summary.overall_status)"
  Write-Host "Blocking failures: $($Report.summary.blocking_failures -join ', ')"
  Write-Host "JSON report: $OutputPath"
}

$initialReport = Get-CheckResults -HealthUrl $BackendHealthUrl -DistributionName $UbuntuDistribution

switch ($Mode) {
  "check" {
    Write-Report -Report $initialReport
  }
  "install" {
    Invoke-InstallPass -Report $initialReport -DistributionName $UbuntuDistribution
    $finalReport = Get-CheckResults -HealthUrl $BackendHealthUrl -DistributionName $UbuntuDistribution
    Write-Report -Report $finalReport
  }
  "all" {
    Write-Report -Report $initialReport
    Invoke-InstallPass -Report $initialReport -DistributionName $UbuntuDistribution
    $finalReport = Get-CheckResults -HealthUrl $BackendHealthUrl -DistributionName $UbuntuDistribution
    Write-Report -Report $finalReport
  }
}
