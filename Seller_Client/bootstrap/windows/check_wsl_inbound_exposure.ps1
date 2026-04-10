param(
  [string]$UbuntuDistro = "Ubuntu",
  [string]$BindAddress = "10.66.66.2",
  [int]$Port = 37946
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$startCommand = @'
pkill -f 'http.server $Port' || true
nohup python3 -m http.server $Port --bind $BindAddress >/tmp/http-$Port.log 2>&1 &
sleep 1
printf 'listener_port=%s\n' '$Port'
printf 'bind_address=%s\n' '$BindAddress'
'@

$probeCommand = @'
printf 'docker=%s\n' "$(systemctl is-active docker || true)"
printf 'wg=%s\n' "$(systemctl is-active wg-quick@wg-seller || true)"
echo ---
ip route get 10.66.66.1 || true
echo ---
ss -ltnp | grep ':$Port ' || true
echo ---
wg show || true
'@

$startCommand = $startCommand.Replace('$Port', [string]$Port).Replace('$BindAddress', $BindAddress)
$probeCommand = $probeCommand.Replace('$Port', [string]$Port)

[PSCustomObject]@{
  route = "Historical WSL substrate diagnostics"
  distro = $UbuntuDistro
  bind_address = $BindAddress
  port = $Port
  listener = (wsl.exe -d $UbuntuDistro sh -lc $startCommand | Out-String).Trim()
  substrate_probe = (wsl.exe -d $UbuntuDistro sh -lc $probeCommand | Out-String).Trim()
} | ConvertTo-Json -Depth 6
