Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "cccc-control-common.ps1")

$paths = Enter-CcccEnvironment

Stop-ManagedWeb

$groupId = Get-SavedGroupId
if (-not $groupId) {
    $groupId = Find-GroupByTitle
}

if ($groupId) {
    try {
        Invoke-Cccc -Arguments @("group", "stop", "--group", $groupId) | Out-Null
    } catch {
    }
}

try {
    Invoke-Cccc -Arguments @("daemon", "stop") | Out-Null
} catch {
}

Write-Output "stopped"
