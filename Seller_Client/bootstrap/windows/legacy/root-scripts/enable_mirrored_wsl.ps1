$ErrorActionPreference = 'Stop'
$homeDir = $HOME
$wslConfig = Join-Path $homeDir '.wslconfig'
$stamp = Get-Date -Format 'yyyyMMddHHmmss'
$backup = Join-Path $homeDir ".wslconfig.runtime-backup-$stamp"

function Stop-DockerDesktopForWslRestart {
  $processNames = @(
    'Docker Desktop',
    'com.docker.backend',
    'com.docker.build',
    'com.docker.dev-envs',
    'docker'
  )
  $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $processNames -contains $_.ProcessName })
  if ($running.Count -eq 0) {
    return $false
  }

  Write-Host 'Stopping Docker Desktop before restarting WSL...'
  foreach ($name in $processNames) {
    Get-Process -Name $name -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
  }
  foreach ($distro in @('docker-desktop', 'docker-desktop-data')) {
    wsl.exe --terminate $distro 2>$null | Out-Null
  }
  Start-Sleep -Seconds 2
  return $true
}

if (Test-Path $wslConfig) {
  Copy-Item $wslConfig $backup -Force
  $current = Get-Content -Raw $wslConfig
} else {
  $current = ''
}
$newContent = @"
[wsl2]
memory=4GB
swap=1GB
networkingMode=mirrored

[experimental]
hostAddressLoopback=true
"@
Set-Content -Path $wslConfig -Value $newContent -Encoding ASCII
$dockerDesktopStopped = Stop-DockerDesktopForWslRestart
wsl.exe --shutdown
Start-Sleep -Seconds 3
[PSCustomObject]@{
  wslconfig_path = $wslConfig
  backup_path = $backup
  docker_desktop_stopped = $dockerDesktopStopped
  previous_content = $current
  current_content = (Get-Content -Raw $wslConfig)
} | ConvertTo-Json -Compress
