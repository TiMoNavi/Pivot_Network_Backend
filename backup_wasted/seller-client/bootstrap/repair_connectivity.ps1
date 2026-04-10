$ErrorActionPreference = "Continue"

Write-Host "Pivot Seller Client Ubuntu compute connectivity helper"
Write-Host ""

Write-Host "[1/4] Checking Windows support tunnel service..."
Get-Service -Name 'WireGuardTunnel$wg-seller' -ErrorAction SilentlyContinue | Format-Table -AutoSize

Write-Host "[2/4] Checking sshd service..."
Get-Service -Name "sshd" -ErrorAction SilentlyContinue | Format-Table -AutoSize

Write-Host "[3/4] Checking WSL Ubuntu and Ubuntu Docker..."
wsl -l -v
wsl -d Ubuntu -- bash -lc "which docker && docker info --format '{{json .Swarm}}'" 2>$null

Write-Host "[4/4] Helpful next steps"
Write-Host "- Ensure the Windows support tunnel wg-seller is running if remote support is needed"
Write-Host "- Ensure sshd is running if remote assistance is needed"
Write-Host "- Ensure WSL2 and the Ubuntu distribution are installed"
Write-Host "- Ensure Ubuntu docker.io and wireguard-tools are installed"
