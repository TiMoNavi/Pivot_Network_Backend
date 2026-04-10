$ErrorActionPreference = 'Stop'
$wslConfig = Join-Path $HOME '.wslconfig'
$stamp = Get-Date -Format 'yyyyMMddHHmmss'
$backup = Join-Path $HOME ".wslconfig.runtime-backup-$stamp"

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

Copy-Item $wslConfig $backup -Force
@"
[wsl2]
memory=4GB
swap=1GB
networkingMode=mirrored
firewall=false

[experimental]
hostAddressLoopback=true
"@ | Set-Content -Path $wslConfig -Encoding ASCII
$dockerDesktopStopped = Stop-DockerDesktopForWslRestart
wsl.exe --shutdown
Start-Sleep -Seconds 3
[PSCustomObject]@{ backup_path = $backup; docker_desktop_stopped = $dockerDesktopStopped; current = (Get-Content -Raw $wslConfig) } | ConvertTo-Json -Compress
