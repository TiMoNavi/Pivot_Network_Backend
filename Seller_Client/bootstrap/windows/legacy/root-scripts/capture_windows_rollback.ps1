$ErrorActionPreference = 'Stop'
$stamp = Get-Date -Format 'yyyyMMddHHmmss'
$dir = "D:\AI\Pivot_Client\seller_client\rollback\$stamp"
New-Item -ItemType Directory -Force $dir | Out-Null
wg showconf wg-seller | Set-Content -Path (Join-Path $dir 'wg-seller.conf') -Encoding ASCII
docker info --format '{{json .Swarm}}' | Set-Content -Path (Join-Path $dir 'docker-desktop-swarm.json') -Encoding UTF8
wsl.exe -l -v | Set-Content -Path (Join-Path $dir 'wsl-list.txt') -Encoding UTF8
wsl.exe -d docker-desktop sh -lc 'ip addr; echo ---; ip route' | Set-Content -Path (Join-Path $dir 'docker-desktop-network.txt') -Encoding UTF8
[PSCustomObject]@{ rollback_dir = $dir } | ConvertTo-Json -Compress
