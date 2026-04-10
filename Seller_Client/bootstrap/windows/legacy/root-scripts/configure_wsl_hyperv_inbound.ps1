param(
    [switch]$Rollback
)

$ErrorActionPreference = "Stop"
$ruleName = "Pivot-WSL-Inbound-Allow-All"
$ruleDisplayName = "Pivot WSL Inbound Allow All"

function Test-IsAdmin {
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    throw "Administrator privileges are required to change WSL Hyper-V firewall settings."
}

$settings = @(Get-NetFirewallHyperVVMSetting)
if ($settings.Count -eq 0) {
    throw "No WSL Hyper-V VM firewall settings were found on this machine."
}

$before = @($settings | Select-Object Name, Enabled, DefaultInboundAction, DefaultOutboundAction, LoopbackEnabled, AllowHostPolicyMerge)

foreach ($setting in $settings) {
    if ($Rollback) {
        Get-NetFirewallHyperVRule -Name $ruleName -ErrorAction SilentlyContinue | Remove-NetFirewallHyperVRule -ErrorAction SilentlyContinue
        Set-NetFirewallHyperVVMSetting -Name $setting.Name `
            -Enabled NotConfigured `
            -DefaultInboundAction NotConfigured `
            -DefaultOutboundAction NotConfigured `
            -LoopbackEnabled NotConfigured `
            -AllowHostPolicyMerge NotConfigured | Out-Null
    } else {
        Set-NetFirewallHyperVVMSetting -Name $setting.Name `
            -Enabled True `
            -DefaultInboundAction Allow `
            -DefaultOutboundAction Allow `
            -LoopbackEnabled True `
            -AllowHostPolicyMerge True | Out-Null

        if (-not (Get-NetFirewallHyperVRule -Name $ruleName -ErrorAction SilentlyContinue)) {
            New-NetFirewallHyperVRule `
                -Name $ruleName `
                -DisplayName $ruleDisplayName `
                -Direction Inbound `
                -VMCreatorId $setting.Name `
                -Protocol Any `
                -Action Allow `
                -Enabled True `
                -Profiles Any | Out-Null
        }
    }
}

$after = @(Get-NetFirewallHyperVVMSetting | Select-Object Name, Enabled, DefaultInboundAction, DefaultOutboundAction, LoopbackEnabled, AllowHostPolicyMerge)
$rulesAfter = @(Get-NetFirewallHyperVRule -Name $ruleName -ErrorAction SilentlyContinue | Select-Object Name, DisplayName, Enabled, Direction, Action, Profiles, VMCreatorId)

[PSCustomObject]@{
    rollback = [bool]$Rollback
    before = $before
    after = $after
    rule_name = $ruleName
    rules_after = $rulesAfter
} | ConvertTo-Json -Depth 5
