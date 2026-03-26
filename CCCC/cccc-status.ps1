Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "cccc-control-common.ps1")

$paths = Enter-CcccEnvironment
$groupId = Get-SavedGroupId
if (-not $groupId) {
    $groupId = Find-GroupByTitle
}

if (-not $groupId) {
    throw "Group is not initialized."
}

Save-GroupId -GroupId $groupId
Ensure-GroupActive -GroupId $groupId

if (-not (Test-WebListening)) {
    throw "Web is not listening on $($env:CCCC_WEB_HOST):$($env:CCCC_WEB_PORT)."
}

$runningActors = @(Get-RunningActorIds -GroupId $groupId)
if ($runningActors.Count -eq 0) {
    throw "No actors are currently running for group $groupId."
}

Write-Output ("healthy: group={0} web={1}:{2} running={3}" -f $groupId, $env:CCCC_WEB_HOST, $env:CCCC_WEB_PORT, ($runningActors -join ","))
