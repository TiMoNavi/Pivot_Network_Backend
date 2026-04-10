$ErrorActionPreference = 'Stop'
$sessionPath = 'D:\AI\Pivot_Client\seller_client\sessions\join_session_0421b90ccabe39e2\session.json'
$session = Get-Content -Raw $sessionPath | ConvertFrom-Json
$jm = $session.onboarding_session.swarm_join_material
$target = "$($jm.manager_addr):$($jm.manager_port)"
docker swarm join --token $jm.join_token --advertise-addr 10.66.66.10 --data-path-addr 10.66.66.10 $target
if ($LASTEXITCODE -ne 0) { throw "docker swarm join failed with exit code $LASTEXITCODE" }
docker info --format '{{json .Swarm}}'
