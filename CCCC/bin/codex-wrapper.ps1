Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $PSCommandPath
$ccccDir = Split-Path -Parent $scriptDir
$projectRoot = Split-Path -Parent $ccccDir

function Import-DotEnv {
    $envFile = Join-Path $projectRoot ".env"
    if (-not (Test-Path -LiteralPath $envFile)) {
        return
    }

    foreach ($rawLine in Get-Content -LiteralPath $envFile -Encoding UTF8) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            continue
        }
        $parts = $line -split "=", 2
        if ($parts.Count -ne 2) {
            continue
        }
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        if ($value.Length -ge 2) {
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }
        if ($key) {
            [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

function Resolve-RealCodex {
    if ($env:CODEX_REAL_BIN -and (Test-Path -LiteralPath $env:CODEX_REAL_BIN)) {
        $resolved = (Resolve-Path -LiteralPath $env:CODEX_REAL_BIN).Path
        if ($resolved -ne (Resolve-Path -LiteralPath $PSCommandPath).Path) {
            return $resolved
        }
    }

    $selfDir = (Resolve-Path -LiteralPath $scriptDir).Path
    $candidates = New-Object System.Collections.Generic.List[string]
    foreach ($name in @("codex.exe", "codex.cmd", "codex.ps1", "codex")) {
        try {
            foreach ($cmd in Get-Command $name -All -ErrorAction Stop) {
                if ($cmd.Source) {
                    $candidates.Add($cmd.Source)
                }
            }
        } catch {
        }
    }

    $vscodeCandidates = Get-ChildItem -Path (Join-Path $env:USERPROFILE ".vscode\extensions") -Filter codex.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
    foreach ($candidate in $vscodeCandidates) {
        $candidates.Add($candidate)
    }
    foreach ($candidate in @(
        (Join-Path $env:APPDATA "npm\codex.cmd"),
        (Join-Path $env:APPDATA "npm\codex"),
        (Join-Path $env:APPDATA "npm\codex.ps1")
    )) {
        $candidates.Add($candidate)
    }

    $seen = New-Object System.Collections.Generic.HashSet[string] ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($candidate in $candidates) {
        if (-not $candidate) {
            continue
        }
        if (-not (Test-Path -LiteralPath $candidate)) {
            continue
        }
        $resolved = (Resolve-Path -LiteralPath $candidate).Path
        if (-not $seen.Add($resolved)) {
            continue
        }
        if ($resolved.StartsWith($selfDir, [System.StringComparison]::OrdinalIgnoreCase)) {
            continue
        }
        return $resolved
    }

    throw "Could not find the real codex binary outside $selfDir"
}

Import-DotEnv

$env:TERM = if ($env:TERM) { $env:TERM } else { "xterm-256color" }
$env:COLORTERM = if ($env:COLORTERM) { $env:COLORTERM } else { "truecolor" }
$env:TERM_PROGRAM = if ($env:TERM_PROGRAM) { $env:TERM_PROGRAM } else { "cccc" }
$env:CLICOLOR = "1"
$env:CLICOLOR_FORCE = "1"
$env:FORCE_COLOR = "1"
$env:HOME = $projectRoot
$env:CODEX_HOME = Join-Path $projectRoot ".codex"

$realCodex = Resolve-RealCodex
$env:CODEX_REAL_BIN = $realCodex

& $realCodex @args
exit $LASTEXITCODE
