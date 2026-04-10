$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)

wsl -d Ubuntu -- bash -lc "chmod +x '$ProjectRoot/bootstrap/ubuntu/bootstrap_ubuntu_compute.sh' && '$ProjectRoot/bootstrap/ubuntu/bootstrap_ubuntu_compute.sh'"
