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
  [int]$TaskProbeTimeoutSeconds = 60,
  [int]$TaskProbeIntervalSeconds = 3,
  [string]$ProbeImage = "busybox:1.36.1"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$PSNativeCommandUseErrorActionPreference = $false

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$monitorScript = Join-Path $ScriptDir "monitor_swarm_manager_truth.ps1"
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
    $ComputeNodeId = [string]$(if ($joinCompleteComputeNodeId) { $joinCompleteComputeNodeId } else { $onboarding.requested_compute_node_id })
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
    $NodeRef = [string]$(if ($joinCompleteNodeRef) { $joinCompleteNodeRef } else { $managerAcceptanceNodeRef })
  }
  if (-not $ExpectedWireGuardAddress) {
    $ExpectedWireGuardAddress = [string]$onboarding.expected_wireguard_ip
  }
}

$managerKeyWslPath = Convert-ToWslPath $ManagerSshKeyPath

function Parse-JsonText {
  param([string]$Text)

  if (-not $Text) {
    return $null
  }

  $trimmed = $Text.Trim()
  $trimmed = $trimmed -replace "`0", ""
  $candidates = New-Object System.Collections.Generic.List[string]
  $candidates.Add($trimmed)

  $firstObject = $trimmed.IndexOf("{")
  $lastObject = $trimmed.LastIndexOf("}")
  if ($firstObject -ge 0 -and $lastObject -gt $firstObject) {
    $candidates.Add($trimmed.Substring($firstObject, $lastObject - $firstObject + 1))
  }

  $firstArray = $trimmed.IndexOf("[")
  $lastArray = $trimmed.LastIndexOf("]")
  if ($firstArray -ge 0 -and $lastArray -gt $firstArray) {
    $candidates.Add($trimmed.Substring($firstArray, $lastArray - $firstArray + 1))
  }

  foreach ($candidate in ($candidates | Select-Object -Unique)) {
    if (-not $candidate) {
      continue
    }
    try {
      return $candidate | ConvertFrom-Json
    } catch {
      continue
    }
  }

  return $null
}

function Invoke-ManagerSshCapture {
  param(
    [string]$RemoteScript,
    [int]$TimeoutSeconds = 30
  )

  $remoteKeyPath = "/tmp/swarm-manager-task-" + [guid]::NewGuid().ToString("N") + ".pem"
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

function Convert-JsonLines {
  param([string]$Text)

  $items = @()
  foreach ($line in ($Text -split "`r?`n")) {
    $trimmed = $line.Trim()
    if (-not $trimmed) {
      continue
    }
    try {
      $items += ($trimmed | ConvertFrom-Json)
    } catch {
      $items += [PSCustomObject]@{ raw = $trimmed }
    }
  }
  return @($items)
}

function Convert-KeyValueBlock {
  param([string]$Text)

  $map = @{}
  foreach ($line in ($Text -split "`r?`n")) {
    if (-not $line.Contains("=")) {
      continue
    }
    $parts = $line.Split("=", 2)
    $map[$parts[0].Trim()] = $parts[1].Trim()
  }
  return $map
}

$monitorArgs = @(
  "-SessionFilePath", $SessionFilePath,
  "-HostNameHint", $HostNameHint,
  "-ManagerHostName", $ManagerHostName,
  "-ManagerUser", $ManagerUser,
  "-ManagerSshPort", [string]$ManagerSshPort,
  "-ManagerSshKeyPath", $ManagerSshKeyPath,
  "-UbuntuDistro", $UbuntuDistro,
  "-ProbeCount", "1",
  "-ProbeIntervalSeconds", "0"
)
if ($ComputeNodeId) {
  $monitorArgs += @("-ComputeNodeId", $ComputeNodeId)
}
if ($NodeRef) {
  $monitorArgs += @("-NodeRef", $NodeRef)
}
if ($ExpectedWireGuardAddress) {
  $monitorArgs += @("-ExpectedWireGuardAddress", $ExpectedWireGuardAddress)
}

$monitorRaw = (& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $monitorScript @monitorArgs 2>&1 | Out-String).Trim()
$monitorPayload = Parse-JsonText -Text $monitorRaw
$selectedCandidate = $null
if ($null -ne $monitorPayload -and $null -ne $monitorPayload.latest_sample) {
  $selectedCandidate = $monitorPayload.latest_sample.selected_candidate
}

if ($null -eq $selectedCandidate) {
  [PSCustomObject]@{
    completion_standard = "manager_task_execution"
    task_execution_verified = $false
    status = "manager_candidate_missing"
    selected_candidate = $null
    proof_source = "none"
    existing_running_tasks = @()
    probe_tasks = @()
    monitor = $monitorPayload
    monitor_raw = $monitorRaw
  } | ConvertTo-Json -Depth 8
  exit 0
}

$selectedNodeId = [string]$selectedCandidate.id
$selectedNodeState = [string]$selectedCandidate.status_state
$selectedNodeAddr = [string]$selectedCandidate.status_addr
if ($selectedNodeState -ne "ready" -or ($ExpectedWireGuardAddress -and $selectedNodeAddr -ne $ExpectedWireGuardAddress)) {
  [PSCustomObject]@{
    completion_standard = "manager_task_execution"
    task_execution_verified = $false
    status = "selected_candidate_not_ready"
    selected_candidate = $selectedCandidate
    proof_source = "none"
    existing_running_tasks = @()
    probe_tasks = @()
    monitor = $monitorPayload
    monitor_raw = $monitorRaw
  } | ConvertTo-Json -Depth 8
  exit 0
}

$serviceName = "seller-task-probe-" + ([guid]::NewGuid().ToString("N").Substring(0, 12))
$remoteScript = @"
set -eu
node_id='$selectedNodeId'
service_name='$serviceName'
probe_image='$ProbeImage'
probe_timeout='$TaskProbeTimeoutSeconds'
probe_interval='$TaskProbeIntervalSeconds'
existing_count=0
proof_source='none'
created_probe_service=0
current_state=''
create_exit=0
create_output=''
echo "__NODE_TASKS_START__"
existing_tasks="`$(docker node ps "`$node_id" --filter desired-state=running --no-trunc --format '{{json .}}' || true)"
if [ -n "`$existing_tasks" ]; then
  printf '%s\n' "`$existing_tasks"
  existing_count="`$(printf '%s\n' "`$existing_tasks" | grep -c . || true)"
fi
echo "__NODE_TASKS_END__"
if [ "`$existing_count" -gt 0 ]; then
  proof_source='existing_running_task'
else
  created_probe_service=1
  create_output="`$(docker service create --detach=true --name "`$service_name" --constraint "node.id==`$node_id" --restart-condition none "`$probe_image" sh -c 'sleep 45' 2>&1)" || create_exit=`$?
  create_output="`$(printf '%s' "`$create_output" | tr '\n' ' ')"
  if [ "`$create_exit" -eq 0 ]; then
    deadline=`$(( `$(date +%s) + probe_timeout ))
    while [ `$(date +%s) -lt "`$deadline" ]; do
      current_state="`$(docker service ps "`$service_name" --no-trunc --format '{{.CurrentState}}' | head -n 1 || true)"
      case "`$current_state" in
        Running*)
          proof_source='probe_service_running'
          break
          ;;
        Rejected*|Failed*|Complete*|Shutdown*|Remove*|Orphaned*)
          break
          ;;
      esac
      sleep "`$probe_interval"
    done
  fi
fi
echo "__PROBE_TASKS_START__"
if [ "`$created_probe_service" -eq 1 ]; then
  docker service ps "`$service_name" --no-trunc --format '{{json .}}' || true
fi
echo "__PROBE_TASKS_END__"
echo "__RESULT_START__"
printf 'service_name=%s\n' "`$service_name"
printf 'probe_image=%s\n' "`$probe_image"
printf 'existing_running_task_count=%s\n' "`$existing_count"
printf 'created_probe_service=%s\n' "`$created_probe_service"
printf 'create_exit=%s\n' "`$create_exit"
printf 'create_output=%s\n' "`$create_output"
printf 'current_state=%s\n' "`$current_state"
printf 'proof_source=%s\n' "`$proof_source"
printf 'task_execution_verified=%s\n' "`$(if [ "`$proof_source" != 'none' ]; then echo 1; else echo 0; fi)"
echo "__RESULT_END__"
if [ "`$created_probe_service" -eq 1 ]; then
  docker service rm "`$service_name" >/dev/null 2>&1 || true
fi
"@

$capture = Invoke-ManagerSshCapture -RemoteScript $remoteScript -TimeoutSeconds ([Math]::Max(60, $TaskProbeTimeoutSeconds + 20))
$existingTasksText = Get-DelimitedBlockText -Text $capture.output -StartMarker "__NODE_TASKS_START__" -EndMarker "__NODE_TASKS_END__"
$probeTasksText = Get-DelimitedBlockText -Text $capture.output -StartMarker "__PROBE_TASKS_START__" -EndMarker "__PROBE_TASKS_END__"
$resultText = Get-DelimitedBlockText -Text $capture.output -StartMarker "__RESULT_START__" -EndMarker "__RESULT_END__"
$resultMap = Convert-KeyValueBlock -Text $resultText
$existingTasks = Convert-JsonLines -Text $existingTasksText
$probeTasks = Convert-JsonLines -Text $probeTasksText
$taskExecutionVerified = [bool]($capture.exit_code -eq 0 -and [string]$resultMap["task_execution_verified"] -eq "1")

[PSCustomObject]@{
  completion_standard = "manager_task_execution"
  task_execution_verified = $taskExecutionVerified
  status = if ($taskExecutionVerified) { "verified" } elseif ($capture.timed_out) { "ssh_timed_out" } elseif ($capture.exit_code -ne 0) { "ssh_failed" } else { "task_not_verified" }
  proof_source = [string]$resultMap["proof_source"]
  selected_candidate = $selectedCandidate
  existing_running_tasks = $existingTasks
  probe_tasks = $probeTasks
  probe_service = [PSCustomObject]@{
    name = [string]$resultMap["service_name"]
    image = [string]$resultMap["probe_image"]
    created = ([string]$resultMap["created_probe_service"] -eq "1")
    existing_running_task_count = if ($resultMap.ContainsKey("existing_running_task_count")) { [int]$resultMap["existing_running_task_count"] } else { 0 }
    current_state = [string]$resultMap["current_state"]
    create_exit = if ($resultMap.ContainsKey("create_exit")) { [int]$resultMap["create_exit"] } else { $null }
    create_output = [string]$resultMap["create_output"]
  }
  ssh_capture = [PSCustomObject]@{
    exit_code = $capture.exit_code
    timed_out = $capture.timed_out
    output = $capture.output
  }
  monitor = $monitorPayload
  monitor_raw = $monitorRaw
} | ConvertTo-Json -Depth 8
