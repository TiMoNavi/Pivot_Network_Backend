param(
  [string]$SessionFilePath = $env:SELLER_CLIENT_SESSION_FILE,
  [string]$ComputeNodeId,
  [string]$NodeRef,
  [string]$ExpectedWireGuardAddress,
  [string]$HostNameHint = "docker-desktop",
  [string]$ManagerHostName = "81.70.52.75",
  [string]$ManagerUser = "root",
  [int]$ManagerSshPort = 22,
  [string]$ManagerSshKeyPath = "",
  [string]$UbuntuDistro = "Ubuntu",
  [int]$ProbeCount = 12,
  [int]$ProbeIntervalSeconds = 5,
  [switch]$RemoveStaleDownNodes
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$PSNativeCommandUseErrorActionPreference = $false

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
. (Join-Path $ScriptDir "swarm_runtime_common.ps1")
$ManagerSshKeyPath = Resolve-ManagerSshKeyPath -ExplicitPath $ManagerSshKeyPath -ProjectRoot $ProjectRoot

if ($SessionFilePath -and (Test-Path $SessionFilePath)) {
  $session = Get-Content -Raw -Encoding UTF8 $SessionFilePath | ConvertFrom-Json
  $onboarding = $session.onboarding_session
  if (-not $ComputeNodeId) {
    $joinCompleteComputeNodeId = $null
    if ($null -ne $onboarding.last_join_complete) {
      $joinCompleteComputeNodeId = $onboarding.last_join_complete.compute_node_id
    }
    $ComputeNodeId = [string]($(if ($joinCompleteComputeNodeId) { $joinCompleteComputeNodeId } else { $onboarding.requested_compute_node_id }))
  }
  if (-not $NodeRef) {
    $joinCompleteNodeRef = $null
    $managerAcceptanceNodeRef = $null
    if ($null -ne $onboarding.last_join_complete) {
      $joinCompleteNodeRef = $onboarding.last_join_complete.node_ref
    }
    if ($null -ne $onboarding.manager_acceptance) {
      $managerAcceptanceNodeRef = $onboarding.manager_acceptance.node_ref
    }
    $NodeRef = [string]($(if ($joinCompleteNodeRef) { $joinCompleteNodeRef } else { $managerAcceptanceNodeRef }))
  }
  if (-not $ExpectedWireGuardAddress) {
    $ExpectedWireGuardAddress = [string]($onboarding.expected_wireguard_ip)
  }
}

if (-not $ComputeNodeId -and -not $NodeRef -and -not $HostNameHint) {
  throw "Need at least one locator: ComputeNodeId, NodeRef, or HostNameHint."
}

$managerKeyWslPath = Convert-ToWslPath $ManagerSshKeyPath

function Invoke-ManagerSshCapture {
  param(
    [string]$RemoteScript,
    [int]$TimeoutSeconds = 30
  )

  $remoteKeyPath = "/tmp/swarm-manager-monitor-" + [guid]::NewGuid().ToString("N") + ".pem"
$script = @"
set -eu
remote_key='$remoteKeyPath'
cp '$managerKeyWslPath' "`$remote_key"
chmod 600 "`$remote_key"
cleanup() {
  rm -f "`$remote_key"
}
trap cleanup EXIT
ssh -o LogLevel=ERROR -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "`$remote_key" -p $ManagerSshPort $ManagerUser@$ManagerHostName 'sh -s' <<'REMOTE'
$RemoteScript
REMOTE
"@
  return Invoke-WslCapture -Distro $UbuntuDistro -TimeoutSeconds $TimeoutSeconds -Script $script
}

function Get-DelimitedBlockText {
  param(
    [string]$Text,
    [string]$StartMarker,
    [string]$EndMarker
  )

  $capture = $false
  $lines = @()
  foreach ($line in ($Text -split "`r?`n")) {
    if ($line -eq $StartMarker) {
      $capture = $true
      continue
    }
    if ($line -eq $EndMarker) {
      break
    }
    if ($capture) {
      $lines += $line
    }
  }
  return ($lines -join "`n").Trim()
}

function Convert-ManagerNodeSummary {
  param(
    [pscustomobject]$Node
  )

  $labels = @{}
  $spec = $Node.Spec
  $description = $Node.Description
  $status = $Node.Status
  $rawLabels = $null
  if ($null -ne $spec -and $spec.PSObject.Properties.Match("Labels").Count -gt 0) {
    $rawLabels = $spec.Labels
  }
  if ($null -ne $rawLabels) {
    foreach ($property in $rawLabels.PSObject.Properties) {
      $labels[$property.Name] = [string]$property.Value
    }
  }

  $nodeId = [string]$Node.ID
  $hostname = if ($null -ne $description -and $description.PSObject.Properties.Match("Hostname").Count -gt 0) { [string]$description.Hostname } else { "" }
  $statusState = if ($null -ne $status -and $status.PSObject.Properties.Match("State").Count -gt 0) { [string]$status.State } else { "" }
  $statusAddr = if ($null -ne $status -and $status.PSObject.Properties.Match("Addr").Count -gt 0) { [string]$status.Addr } else { "" }
  $statusMessage = if ($null -ne $status -and $status.PSObject.Properties.Match("Message").Count -gt 0) { [string]$status.Message } else { "" }
  $role = if ($null -ne $spec -and $spec.PSObject.Properties.Match("Role").Count -gt 0) { [string]$spec.Role } else { "" }
  $availability = if ($null -ne $spec -and $spec.PSObject.Properties.Match("Availability").Count -gt 0) { [string]$spec.Availability } else { "" }

  [PSCustomObject]@{
    id = $nodeId
    hostname = $hostname
    role = $role
    availability = $availability
    status_state = $statusState
    status_addr = $statusAddr
    status_message = $statusMessage
    compute_node_id = [string]$labels["platform.compute_node_id"]
    seller_user_id = [string]$labels["platform.seller_user_id"]
    accelerator = [string]$labels["platform.accelerator"]
    labels = $labels
    matches_node_ref = [bool]($NodeRef -and $nodeId -and ($nodeId -eq $NodeRef -or $nodeId.StartsWith($NodeRef)))
    matches_compute_node_id = [bool]($ComputeNodeId -and $labels.ContainsKey("platform.compute_node_id") -and $labels["platform.compute_node_id"] -eq $ComputeNodeId)
    matches_hostname = [bool]($HostNameHint -and $hostname -and $hostname -eq $HostNameHint)
    matches_expected_wireguard_addr = [bool]($ExpectedWireGuardAddress -and $statusAddr -eq $ExpectedWireGuardAddress)
  }
}

function Select-ManagerCandidate {
  param(
    [object[]]$Candidates
  )

  if (-not $Candidates -or $Candidates.Count -eq 0) {
    return $null
  }

  return $Candidates | Sort-Object `
    @{ Expression = { if ($ExpectedWireGuardAddress -and $_.status_addr -eq $ExpectedWireGuardAddress) { 1 } else { 0 } }; Descending = $true }, `
    @{ Expression = { if ($_.status_state -eq "ready") { 1 } else { 0 } }; Descending = $true }, `
    @{ Expression = { if ($_.matches_node_ref) { 1 } else { 0 } }; Descending = $true }, `
    @{ Expression = { if ($_.matches_compute_node_id) { 1 } else { 0 } }; Descending = $true }, `
    @{ Expression = { if ($_.matches_hostname) { 1 } else { 0 } }; Descending = $true }, `
    @{ Expression = { $_.id }; Descending = $false } |
    Select-Object -First 1
}

function Get-ManagerTruthSample {
  $remoteScript = @'
set -eu
echo "__NODE_LS_START__"
docker node ls --format '{{json .}}' || true
echo "__NODE_LS_END__"
echo "__NODE_INSPECT_START__"
node_ids="$(docker node ls -q || true)"
if [ -n "$node_ids" ]; then
  docker node inspect $node_ids || true
else
  echo "[]"
fi
echo "__NODE_INSPECT_END__"
'@

  $capture = Invoke-ManagerSshCapture -RemoteScript $remoteScript -TimeoutSeconds 40
  $output = $capture.output
  $nodeLsText = Get-DelimitedBlockText -Text $output -StartMarker "__NODE_LS_START__" -EndMarker "__NODE_LS_END__"
  $nodeInspectText = Get-DelimitedBlockText -Text $output -StartMarker "__NODE_INSPECT_START__" -EndMarker "__NODE_INSPECT_END__"

  $nodeLs = @()
  if ($nodeLsText) {
    foreach ($line in ($nodeLsText -split "`r?`n")) {
      if ($line.Trim()) {
        $nodeLs += ($line | ConvertFrom-Json)
      }
    }
  }

  $nodeInspect = @()
  if ($nodeInspectText) {
    $parsedInspect = $nodeInspectText | ConvertFrom-Json
    if ($parsedInspect -is [System.Array]) {
      $nodeInspect = @($parsedInspect)
    } elseif ($null -ne $parsedInspect) {
      $nodeInspect = @($parsedInspect)
    }
  }

  $candidateNodes = @(
    $nodeInspect |
      ForEach-Object { Convert-ManagerNodeSummary -Node $_ } |
      Where-Object {
        $_.matches_node_ref -or
        $_.matches_compute_node_id -or
        $_.matches_hostname -or
        $_.matches_expected_wireguard_addr
      }
  )
  $selectedCandidate = Select-ManagerCandidate -Candidates $candidateNodes

  [PSCustomObject]@{
    captured_at = (Get-Date).ToString("o")
    ssh_exit_code = $capture.exit_code
    ssh_timed_out = $capture.timed_out
    node_ls = $nodeLs
    candidate_nodes = $candidateNodes
    selected_candidate = $selectedCandidate
    raw_success = [bool](
      $selectedCandidate -and
      $ExpectedWireGuardAddress -and
      $selectedCandidate.status_state -eq "ready" -and
      $selectedCandidate.status_addr -eq $ExpectedWireGuardAddress
    )
  }
}

function Remove-StaleDownNodes {
  param(
    [object[]]$CandidateNodes,
    [string]$SelectedNodeId
  )

  $staleIds = @(
    $CandidateNodes |
      Where-Object {
        $_.status_state -eq "down" -and
        $_.id -and
        $_.id -ne $SelectedNodeId
      } |
      Select-Object -ExpandProperty id -Unique
  )
  if (-not $staleIds -or $staleIds.Count -eq 0) {
    return [PSCustomObject]@{
      removed_node_ids = @()
      remove_exit_code = 0
      remove_output = ""
    }
  }

  $remoteScript = "docker node rm --force " + ($staleIds -join " ")
  $capture = Invoke-ManagerSshCapture -RemoteScript $remoteScript -TimeoutSeconds 30
  return [PSCustomObject]@{
    removed_node_ids = $staleIds
    remove_exit_code = $capture.exit_code
    remove_output = $capture.output
  }
}

$samples = @()
for ($index = 0; $index -lt $ProbeCount; $index++) {
  $samples += Get-ManagerTruthSample
  if ($index -lt ($ProbeCount - 1) -and $ProbeIntervalSeconds -gt 0) {
    Start-Sleep -Seconds $ProbeIntervalSeconds
  }
}

$latestSample = if ($samples.Count -gt 0) { $samples[-1] } else { $null }
$selectedNodeId = if ($null -ne $latestSample.selected_candidate) { [string]$latestSample.selected_candidate.id } else { "" }
$cleanupResult = $null
if ($RemoveStaleDownNodes -and $null -ne $latestSample) {
  $cleanupResult = Remove-StaleDownNodes -CandidateNodes $latestSample.candidate_nodes -SelectedNodeId $selectedNodeId
}

[PSCustomObject]@{
  manager_host = $ManagerHostName
  manager_user = $ManagerUser
  manager_port = $ManagerSshPort
  ubuntu_distro = $UbuntuDistro
  compute_node_id = $ComputeNodeId
  node_ref = $NodeRef
  expected_wireguard_address = $ExpectedWireGuardAddress
  host_name_hint = $HostNameHint
  probe_count = $ProbeCount
  probe_interval_seconds = $ProbeIntervalSeconds
  raw_success = [bool]($samples | Where-Object { $_.raw_success } | Select-Object -First 1)
  latest_sample = $latestSample
  samples = $samples
  cleanup = $cleanupResult
} | ConvertTo-Json -Depth 8
