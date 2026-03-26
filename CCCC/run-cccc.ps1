param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "cccc-control-common.ps1")

$paths = Enter-CcccEnvironment

$resolvedArgs = @($CliArgs)
if ($resolvedArgs.Count -gt 0 -and $resolvedArgs[0] -eq "cccc") {
    if ($resolvedArgs.Count -eq 1) {
        $resolvedArgs = @()
    } else {
        $resolvedArgs = $resolvedArgs[1..($resolvedArgs.Count - 1)]
    }
}

if ($resolvedArgs.Count -eq 0) {
    & $paths.CcccExe
    exit $LASTEXITCODE
}

& $paths.CcccExe @resolvedArgs
exit $LASTEXITCODE
