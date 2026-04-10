param(
  [string]$UbuntuDistro = "Ubuntu"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$packages = "docker.io wireguard-tools netcat-openbsd"
$command = @"
apt-get update &&
DEBIAN_FRONTEND=noninteractive apt-get install -y $packages &&
systemctl enable --now docker &&
printf 'docker=%s\n' "\$(systemctl is-active docker)" &&
printf 'docker_bin=%s\n' "\$(command -v docker || true)" &&
printf 'dockerd_bin=%s\n' "\$(command -v dockerd || true)" &&
printf 'wg_bin=%s\n' "\$(command -v wg || true)" &&
printf 'wg_quick_bin=%s\n' "\$(command -v wg-quick || true)"
"@

wsl.exe -d $UbuntuDistro sh -lc $command
