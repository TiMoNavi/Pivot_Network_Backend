param(
  [string]$UbuntuDistro = "Ubuntu",
  [string]$TunnelName = "wg-seller",
  [string]$ManagerIp = "10.66.66.1"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$command = @'
printf 'docker=%s\n' "\$(systemctl is-active docker || true)"
printf 'wg=%s\n' "\$(systemctl is-active wg-quick@$TunnelName || true)"
echo ---
docker version 2>/dev/null | sed -n '1,20p'
echo ---
docker info 2>/dev/null | sed -n '1,60p'
echo ---
ip route get $ManagerIp || true
echo ---
wg show || true
'@

$command = $command.Replace('$TunnelName', $TunnelName).Replace('$ManagerIp', $ManagerIp)

wsl.exe -d $UbuntuDistro sh -lc $command
