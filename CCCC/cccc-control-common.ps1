Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$script:CcccCommonDir = $PSScriptRoot

function Get-CcccPaths {
    $ccccDir = $script:CcccCommonDir
    $projectRoot = Split-Path -Parent $ccccDir
    $runtimeDir = Join-Path $ccccDir "runtime"
    $venvDir = Join-Path $runtimeDir "venv"
    $venvScripts = Join-Path $venvDir "Scripts"
    $controlDir = Join-Path $runtimeDir "control"
    $logDir = Join-Path $runtimeDir "logs"

    return @{
        CcccDir = $ccccDir
        ProjectRoot = $projectRoot
        RuntimeDir = $runtimeDir
        HomeDir = Join-Path $runtimeDir "cccc-home"
        VenvDir = $venvDir
        VenvScripts = $venvScripts
        VenvPython = Join-Path $venvScripts "python.exe"
        VenvPip = Join-Path $venvScripts "pip.exe"
        CcccExe = Join-Path $venvScripts "cccc.exe"
        PythonExe = (Get-Command python -ErrorAction Stop).Source
        ControlDir = $controlDir
        LogDir = $logDir
        GroupIdFile = Join-Path $controlDir "group.id"
        WebPidFile = Join-Path $controlDir "web.pid"
        WebOutLogFile = Join-Path $logDir "web.out.log"
        WebErrLogFile = Join-Path $logDir "web.err.log"
        RunScript = Join-Path $ccccDir "run-cccc.ps1"
        TemplateApplier = Join-Path $ccccDir "apply_group_template.py"
        StartupProbe = Join-Path $ccccDir "startup_probe.py"
        TemplatePath = Join-Path $ccccDir "templates\pivot-backend-build-team.group-template.yaml"
        BinDir = Join-Path $ccccDir "bin"
    }
}

function Ensure-CcccDirectories {
    $paths = Get-CcccPaths
    foreach ($path in @($paths.RuntimeDir, $paths.HomeDir, $paths.ControlDir, $paths.LogDir)) {
        if (-not (Test-Path -LiteralPath $path)) {
            New-Item -ItemType Directory -Path $path -Force | Out-Null
        }
    }
}

function Import-ProjectDotEnv {
    $paths = Get-CcccPaths
    $envFile = Join-Path $paths.ProjectRoot ".env"
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

function Get-InstalledCcccVersion {
    $paths = Get-CcccPaths
    if (-not (Test-Path -LiteralPath $paths.VenvPython)) {
        return $null
    }

    try {
        $version = & $paths.VenvPython -c "import importlib.metadata as m; print(m.version('cccc-pair'))" 2>$null
        return ($version | Out-String).Trim()
    } catch {
        return $null
    }
}

function Ensure-CcccRuntime {
    param(
        [string]$Version = "0.4.7"
    )

    $paths = Get-CcccPaths
    Ensure-CcccDirectories

    $installedVersion = Get-InstalledCcccVersion
    if ((Test-Path -LiteralPath $paths.CcccExe) -and $installedVersion -eq $Version) {
        return $paths
    }

    if (-not (Test-Path -LiteralPath $paths.VenvPython)) {
        & $paths.PythonExe -m venv $paths.VenvDir
    }

    & $paths.VenvPython -m pip install --upgrade pip
    & $paths.VenvPython -m pip install "cccc-pair==$Version"

    if (-not (Test-Path -LiteralPath $paths.CcccExe)) {
        throw "Failed to install cccc-pair==$Version into $($paths.VenvDir)"
    }

    return $paths
}

function Enter-CcccEnvironment {
    param(
        [string]$Version = "0.4.7"
    )

    $paths = Ensure-CcccRuntime -Version $Version
    Import-ProjectDotEnv

    $env:TERM = if ($env:TERM) { $env:TERM } else { "xterm-256color" }
    $env:COLORTERM = if ($env:COLORTERM) { $env:COLORTERM } else { "truecolor" }
    $env:TERM_PROGRAM = if ($env:TERM_PROGRAM) { $env:TERM_PROGRAM } else { "cccc" }
    $env:CLICOLOR = "1"
    $env:CLICOLOR_FORCE = "1"
    $env:FORCE_COLOR = "1"
    $env:CCCC_HOME = $paths.HomeDir
    if (-not $env:CCCC_WEB_HOST) {
        $env:CCCC_WEB_HOST = "127.0.0.1"
    }
    if (-not $env:CCCC_WEB_PORT) {
        $env:CCCC_WEB_PORT = "8848"
    }
    if (-not $env:CCCC_GROUP_TITLE) {
        $env:CCCC_GROUP_TITLE = "Pivot Backend Build Team"
    }
    if (-not $env:CCCC_GROUP_TOPIC) {
        $env:CCCC_GROUP_TOPIC = "Phase 1 - AI-operated Docker Swarm adapter and backend compatibility layer"
    }

    $pathEntries = New-Object System.Collections.Generic.List[string]
    $pathEntries.Add($paths.BinDir)
    $pathEntries.Add($paths.VenvScripts)
    foreach ($entry in ($env:PATH -split ";")) {
        if ($entry) {
            $pathEntries.Add($entry)
        }
    }
    $seen = New-Object System.Collections.Generic.HashSet[string] ([System.StringComparer]::OrdinalIgnoreCase)
    $deduped = foreach ($entry in $pathEntries) {
        $trimmed = $entry.Trim()
        if (-not $trimmed) {
            continue
        }
        if ($seen.Add($trimmed)) {
            $trimmed
        }
    }
    $env:PATH = ($deduped -join ";")

    return $paths
}

function Invoke-Cccc {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $paths = Enter-CcccEnvironment
    & $paths.CcccExe @Arguments
}

function Invoke-CcccJson {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $raw = Invoke-Cccc -Arguments $Arguments | Out-String
    $payload = $raw.Trim()
    if (-not $payload) {
        return $null
    }
    return $payload | ConvertFrom-Json
}

function Invoke-TemplateHelper {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $paths = Enter-CcccEnvironment
    & $paths.VenvPython $paths.TemplateApplier @Arguments
}

function Get-ConfiguredGroupTitle {
    return $env:CCCC_GROUP_TITLE
}

function Get-ConfiguredGroupTopic {
    return $env:CCCC_GROUP_TOPIC
}

function Get-RequiredActors {
    return @("lead", "swarm_cli", "backend_adapter", "verification", "docs_summary")
}

function Get-ActorCommandOverride {
    $paths = Get-CcccPaths
    $wrapper = Join-Path $paths.BinDir "codex.cmd"
    return ('"{0}" -c shell_environment_policy.inherit=all --dangerously-bypass-approvals-and-sandbox --search' -f $wrapper)
}

function Apply-ActorCommandOverrides {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GroupId
    )

    $commandOverride = Get-ActorCommandOverride
    foreach ($actorId in Get-RequiredActors) {
        Invoke-Cccc -Arguments @(
            "actor", "update", $actorId,
            "--group", $GroupId,
            "--command", $commandOverride
        ) | Out-Null
    }
}

function Get-SavedGroupId {
    $paths = Get-CcccPaths
    if (-not (Test-Path -LiteralPath $paths.GroupIdFile)) {
        return $null
    }
    return (Get-Content -LiteralPath $paths.GroupIdFile -Encoding UTF8 | Out-String).Trim()
}

function Save-GroupId {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GroupId
    )

    $paths = Get-CcccPaths
    Set-Content -LiteralPath $paths.GroupIdFile -Value $GroupId -Encoding UTF8
}

function Test-GroupExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GroupId
    )

    $payload = Invoke-CcccJson -Arguments @("groups")
    if (-not $payload) {
        return $false
    }
    return [bool]($payload.result.groups | Where-Object { $_.group_id -eq $GroupId })
}

function Find-GroupByTitle {
    $title = Get-ConfiguredGroupTitle
    $payload = Invoke-CcccJson -Arguments @("groups")
    if (-not $payload) {
        return $null
    }
    $match = $payload.result.groups | Where-Object { $_.title -eq $title } | Select-Object -First 1
    if ($match) {
        return [string]$match.group_id
    }
    return $null
}

function New-GroupFromTemplate {
    $paths = Enter-CcccEnvironment
    $output = Invoke-TemplateHelper -Arguments @(
        "create",
        "--project-root", $paths.ProjectRoot,
        "--template", $paths.TemplatePath,
        "--title", (Get-ConfiguredGroupTitle),
        "--topic", (Get-ConfiguredGroupTopic)
    )
    return ($output | Out-String).Trim()
}

function Resolve-GroupId {
    $saved = Get-SavedGroupId
    if ($saved -and (Test-GroupExists -GroupId $saved)) {
        return $saved
    }

    $existing = Find-GroupByTitle
    if ($existing) {
        return $existing
    }

    return New-GroupFromTemplate
}

function Ensure-GroupActive {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GroupId
    )

    Invoke-Cccc -Arguments @("use", $GroupId) | Out-Null
}

function Ensure-GroupAttached {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GroupId
    )

    $paths = Enter-CcccEnvironment
    Invoke-Cccc -Arguments @("attach", "--group", $GroupId, $paths.ProjectRoot) | Out-Null
}

function Sync-GroupMetadata {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GroupId
    )

    Invoke-Cccc -Arguments @(
        "group", "update",
        "--group", $GroupId,
        "--title", (Get-ConfiguredGroupTitle),
        "--topic", (Get-ConfiguredGroupTopic)
    ) | Out-Null
}

function Apply-GroupTemplate {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GroupId
    )

    $paths = Enter-CcccEnvironment
    Invoke-TemplateHelper -Arguments @(
        "apply",
        "--group-id", $GroupId,
        "--template", $paths.TemplatePath
    ) | Out-Null
}

function Get-ActorList {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GroupId
    )

    $payload = Invoke-CcccJson -Arguments @("actor", "list", "--group", $GroupId)
    if (-not $payload) {
        return @()
    }
    return @($payload.result.actors)
}

function Ensure-RequiredActors {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GroupId
    )

    $actors = Get-ActorList -GroupId $GroupId
    $actorIds = @($actors | ForEach-Object { [string]$_.id })
    foreach ($actorId in Get-RequiredActors) {
        if ($actorIds -notcontains $actorId) {
            throw "Missing required actor $actorId in group $GroupId"
        }
    }
}

function Start-GroupAndActors {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GroupId
    )

    Invoke-Cccc -Arguments @("group", "start", "--group", $GroupId) | Out-Null
    foreach ($actorId in Get-RequiredActors) {
        Invoke-Cccc -Arguments @("actor", "start", $actorId, "--group", $GroupId) | Out-Null
    }
}

function Get-RunningActorIds {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GroupId
    )

    $actors = Get-ActorList -GroupId $GroupId
    return @($actors | Where-Object { $_.running } | ForEach-Object { [string]$_.id })
}

function Get-StartupProbeActorId {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GroupId
    )

    $running = Get-RunningActorIds -GroupId $GroupId
    if ($running -contains "swarm_cli") {
        return "swarm_cli"
    }
    if ($running.Count -gt 0) {
        return [string]$running[0]
    }
    return "swarm_cli"
}

function Test-ActorsHealthy {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GroupId
    )

    $actors = Get-ActorList -GroupId $GroupId
    $required = Get-RequiredActors
    foreach ($actorId in $required) {
        $actor = $actors | Where-Object { $_.id -eq $actorId } | Select-Object -First 1
        if (-not $actor -or -not $actor.running) {
            return $false
        }
    }
    return $true
}

function Wait-ActorsHealthy {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GroupId,
        [int]$TimeoutSeconds = 120
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-ActorsHealthy -GroupId $GroupId) {
            return $true
        }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Get-WebHost {
    return $env:CCCC_WEB_HOST
}

function Get-WebPort {
    return [int]$env:CCCC_WEB_PORT
}

function Test-WebListening {
    $probeHost = Get-WebHost
    if ($probeHost -eq "0.0.0.0" -or $probeHost -eq "::") {
        $probeHost = "127.0.0.1"
    }
    $port = Get-WebPort

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($probeHost, $port, $null, $null)
        $connected = $async.AsyncWaitHandle.WaitOne(500)
        if (-not $connected) {
            return $false
        }
        $client.EndConnect($async)
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Wait-Web {
    param(
        [int]$TimeoutSeconds = 120
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-WebListening) {
            return $true
        }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Start-WebBackground {
    $paths = Enter-CcccEnvironment
    if (Test-WebListening) {
        return
    }

    $arguments = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $paths.RunScript,
        "cccc",
        "web",
        "--host", (Get-WebHost),
        "--port", ([string](Get-WebPort))
    )

    $process = Start-Process -FilePath "powershell.exe" -ArgumentList $arguments -RedirectStandardOutput $paths.WebOutLogFile -RedirectStandardError $paths.WebErrLogFile -WindowStyle Hidden -PassThru
    Set-Content -LiteralPath $paths.WebPidFile -Value ([string]$process.Id) -Encoding UTF8
}

function Stop-ManagedWeb {
    $paths = Get-CcccPaths
    if (-not (Test-Path -LiteralPath $paths.WebPidFile)) {
        return
    }

    $pidText = (Get-Content -LiteralPath $paths.WebPidFile -Encoding UTF8 | Out-String).Trim()
    if ($pidText) {
        try {
            Stop-Process -Id ([int]$pidText) -Force -ErrorAction Stop
        } catch {
        }
    }
    Remove-Item -LiteralPath $paths.WebPidFile -Force -ErrorAction SilentlyContinue
}

function Get-LedgerPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GroupId
    )

    $paths = Get-CcccPaths
    return Join-Path $paths.HomeDir ("groups\" + $GroupId + "\ledger.jsonl")
}

function Read-LedgerEvents {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GroupId
    )

    $ledgerPath = Get-LedgerPath -GroupId $GroupId
    if (-not (Test-Path -LiteralPath $ledgerPath)) {
        return @()
    }

    $events = New-Object System.Collections.Generic.List[object]
    foreach ($line in Get-Content -LiteralPath $ledgerPath -Encoding UTF8) {
        if (-not $line.Trim()) {
            continue
        }
        try {
            $events.Add(($line | ConvertFrom-Json))
        } catch {
        }
    }
    return $events
}

function Wait-ForLedgerEvent {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Predicate,
        [Parameter(Mandatory = $true)]
        [string]$GroupId,
        [int]$TimeoutSeconds = 120
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $events = Read-LedgerEvents -GroupId $GroupId
        foreach ($event in $events) {
            if (& $Predicate $event) {
                return $event
            }
        }
        Start-Sleep -Seconds 2
    }
    return $null
}

function Send-StartupVerificationMessage {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GroupId
    )

    Ensure-GroupActive -GroupId $GroupId
    $nonce = [Guid]::NewGuid().ToString("N").Substring(0, 12)
    $message = "Startup verification $nonce. Reply to user with exactly: CCCC startup OK $nonce."
    Invoke-Cccc -Arguments @("send", $message, "--to", "lead") | Out-Null

    $sendEvent = Wait-ForLedgerEvent -GroupId $GroupId -TimeoutSeconds 30 -Predicate {
        param($event)
        $event.kind -eq "chat.message" -and
        $event.by -eq "user" -and
        $event.data -and
        $event.data.text -eq $message
    }

    if (-not $sendEvent) {
        throw "Startup verification message was not written to the ledger."
    }

    $replyEvent = Wait-ForLedgerEvent -GroupId $GroupId -TimeoutSeconds 180 -Predicate {
        param($event)
        $event.kind -eq "chat.message" -and
        $event.by -ne "user" -and
        $event.by -ne "system" -and
        $event.data -and
        (
            $event.data.reply_to -eq $sendEvent.id -or
            ($event.data.text -like "*$nonce*")
        )
    }

    if (-not $replyEvent) {
        throw "No actor replied to the startup verification message within the timeout."
    }

    return @{
        Nonce = $nonce
        RequestEventId = [string]$sendEvent.id
        ReplyEventId = [string]$replyEvent.id
        ReplyBy = [string]$replyEvent.by
        ReplyText = [string]$replyEvent.data.text
    }
}

function Invoke-StartupProbe {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GroupId,
        [string]$ActorId = ""
    )

    $paths = Enter-CcccEnvironment
    $targetActor = if ($ActorId) { $ActorId } else { Get-StartupProbeActorId -GroupId $GroupId }
    $raw = & $paths.VenvPython $paths.StartupProbe `
        --group-id $GroupId `
        --actor-id $targetActor `
        --project-root $paths.ProjectRoot `
        --cccc-home $paths.HomeDir
    $payload = ($raw | Out-String).Trim()
    if (-not $payload) {
        throw "startup_probe returned an empty payload"
    }
    return $payload | ConvertFrom-Json
}
