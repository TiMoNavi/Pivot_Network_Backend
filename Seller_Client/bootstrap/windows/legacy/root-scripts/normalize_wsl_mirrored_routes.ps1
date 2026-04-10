param(
    [string]$Distro = "Ubuntu",
    [string]$ManagerIp = "81.70.52.75",
    [string]$PreferredHostIp,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

function Get-PreferredHostAdapter {
    param(
        [string]$PreferredIp
    )

    $excludedPatterns = @(
        "Meta",
        "Radmin",
        "ZeroTier",
        "VMware",
        "vEthernet",
        "Bluetooth",
        "Loopback",
        "WireGuard",
        "pc-pico-remote",
        "pivot-buyer",
        "natpierce"
    )

    $profiles = @{}
    foreach ($profile in Get-NetConnectionProfile -ErrorAction SilentlyContinue) {
        $profiles[$profile.InterfaceAlias] = $profile
    }

    $adapters = Get-NetAdapter -ErrorAction SilentlyContinue | Group-Object -Property Name -AsHashTable -AsString
    $ipIfs = Get-NetIPInterface -AddressFamily IPv4 -ErrorAction SilentlyContinue | Group-Object -Property InterfaceAlias -AsHashTable -AsString

    $candidates = foreach ($ip in Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue) {
        if (-not $ip.IPAddress) { continue }
        if ($ip.IPAddress -like "169.254.*" -or $ip.IPAddress -eq "127.0.0.1") { continue }

        $alias = [string]$ip.InterfaceAlias
        $adapter = $adapters[$alias]
        if (-not $adapter -or $adapter.Status -ne "Up") { continue }

        $excluded = $false
        foreach ($pattern in $excludedPatterns) {
            if ($alias -like "*$pattern*" -or $adapter.InterfaceDescription -like "*$pattern*") {
                $excluded = $true
                break
            }
        }
        if ($excluded) { continue }

        $profile = $profiles[$alias]
        $ipIf = $ipIfs[$alias]
        $score = 0
        if ($PreferredIp -and $ip.IPAddress -eq $PreferredIp) { $score += 1000 }
        if ($profile -and $profile.NetworkCategory -eq "Private") { $score += 100 }
        if ($profile -and $profile.IPv4Connectivity -eq "Internet") { $score += 50 }
        if ($ipIf -and $ipIf.ConnectionState -eq "Connected") { $score += 25 }
        if ($ipIf -and $ipIf.InterfaceMetric -is [int]) { $score += [Math]::Max(0, 50 - $ipIf.InterfaceMetric) }

        [PSCustomObject]@{
            InterfaceAlias = $alias
            InterfaceDescription = [string]$adapter.InterfaceDescription
            IPAddress = [string]$ip.IPAddress
            PrefixLength = [int]$ip.PrefixLength
            NetworkCategory = if ($profile) { [string]$profile.NetworkCategory } else { "" }
            IPv4Connectivity = if ($profile) { [string]$profile.IPv4Connectivity } else { "" }
            InterfaceMetric = if ($ipIf) { [int]$ipIf.InterfaceMetric } else { 0 }
            Score = $score
        }
    }

    $winner = $candidates | Sort-Object -Property Score, InterfaceMetric -Descending | Select-Object -First 1
    if (-not $winner) {
        throw "Unable to determine a preferred Windows host adapter for mirrored WSL egress."
    }

    [PSCustomObject]@{
        preferred = $winner
        candidates = @($candidates | Sort-Object -Property Score, InterfaceMetric -Descending)
    }
}

function Invoke-Wsl {
    param(
        [string]$Command
    )

    & wsl.exe -d $Distro -- bash -lc $Command
}

$selection = Get-PreferredHostAdapter -PreferredIp $PreferredHostIp
$preferred = $selection.preferred

$preferredWslDev = (Invoke-Wsl "ip -br -4 addr show scope global | grep -F '$($preferred.IPAddress)/' | sed -n '1s/[[:space:]].*//p'").Trim()
if (-not $preferredWslDev) {
    throw "Unable to map Windows host IP $($preferred.IPAddress) into a mirrored WSL interface."
}

$beforeDefaultRoutes = @(Invoke-Wsl "ip route show default")
$collisionRoutes = @(Invoke-Wsl "ip -br -4 addr show scope global | grep -E '^([^ ]+) +UP +10\\.66\\.66\\.' | grep -v '^wg-seller ' || true")
$managerRouteBefore = @(Invoke-Wsl "ip route get $ManagerIp")

$plannedDeletes = @()
$preferredGateway = $null
foreach ($route in $beforeDefaultRoutes) {
    if ($route -match '^default via (\S+) dev (\S+)') {
        $gateway = [string]$Matches[1]
        $dev = [string]$Matches[2]
        if ($dev -eq $preferredWslDev -and -not $preferredGateway) {
            $preferredGateway = $gateway
        }
        if ($dev -ne $preferredWslDev) {
            $plannedDeletes += [PSCustomObject]@{
                gateway = $gateway
                dev = $dev
            }
        }
    }
}

if (-not $preferredGateway) {
    throw "Unable to determine the preferred mirrored gateway for device $preferredWslDev."
}

$result = [ordered]@{
    preferred_host_interface = $preferred
    mirrored_wsl_interface = $preferredWslDev
    preferred_gateway = $preferredGateway
    default_routes_before = $beforeDefaultRoutes
    manager_route_before = $managerRouteBefore
    mirrored_overlay_conflicts = $collisionRoutes
    planned_default_route_deletes = $plannedDeletes
}

if (-not $WhatIf) {
    Invoke-Wsl "sudo ip route replace $ManagerIp via $preferredGateway dev $preferredWslDev" | Out-Null
    Invoke-Wsl "sudo ip route flush cache" | Out-Null
    $result.manager_host_route_after = @(Invoke-Wsl "ip route show $ManagerIp/32 || true")
    $result.default_routes_after = @(Invoke-Wsl "ip route show default")
    $result.manager_route_after = @(Invoke-Wsl "ip route get $ManagerIp")
}

$result | ConvertTo-Json -Depth 6
