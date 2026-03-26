Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "cccc-control-common.ps1")

$paths = Enter-CcccEnvironment

Invoke-Cccc -Arguments @("daemon", "start") | Out-Null

$groupId = Resolve-GroupId
if (-not $groupId) {
    throw "Failed to resolve or create a CCCC group."
}

Save-GroupId -GroupId $groupId
Ensure-GroupActive -GroupId $groupId
Ensure-GroupAttached -GroupId $groupId
Sync-GroupMetadata -GroupId $groupId
Apply-GroupTemplate -GroupId $groupId
Apply-ActorCommandOverrides -GroupId $groupId
Ensure-RequiredActors -GroupId $groupId
Start-GroupAndActors -GroupId $groupId
Start-WebBackground

if (-not (Wait-Web -TimeoutSeconds 180)) {
    throw "Web did not become healthy on $($env:CCCC_WEB_HOST):$($env:CCCC_WEB_PORT)."
}

$reply = Invoke-StartupProbe -GroupId $groupId

$runningActors = @(Get-RunningActorIds -GroupId $groupId)
$runningSummary = if ($runningActors.Count -gt 0) { ($runningActors -join ",") } else { "(none)" }
Write-Output ("healthy: group={0} web={1}:{2} probe_actor={3} running={4} reply_by={5} reply=""{6}""" -f $groupId, $env:CCCC_WEB_HOST, $env:CCCC_WEB_PORT, $reply.actor_id, $runningSummary, $reply.reply_by, $reply.reply_text)
