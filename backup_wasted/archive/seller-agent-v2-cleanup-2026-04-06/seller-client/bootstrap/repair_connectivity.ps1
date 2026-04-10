$ErrorActionPreference = "Continue"

Write-Host "Pivot Seller Client connectivity repair helper"
Write-Host ""

Write-Host "[1/4] Checking WireGuard tunnel service..."
Get-Service -Name "WireGuardTunnel$wg-seller" -ErrorAction SilentlyContinue | Format-Table -AutoSize

Write-Host "[2/4] Checking sshd service..."
Get-Service -Name "sshd" -ErrorAction SilentlyContinue | Format-Table -AutoSize

Write-Host "[3/4] Checking Docker Desktop service..."
Get-Service -Name "com.docker.service" -ErrorAction SilentlyContinue | Format-Table -AutoSize

Write-Host "[4/4] Helpful next steps"
Write-Host "- Ensure WireGuard tunnel wg-seller is running"
Write-Host "- Ensure sshd is running if remote assistance is needed"
Write-Host "- Ensure Docker Desktop is started"
Write-Host "- If WSL2 is missing, run: wsl --install"
