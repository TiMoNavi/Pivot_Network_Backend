#!/usr/bin/env bash
set -euo pipefail
ss -lnt '( sport = :22220 )'
ssh -o BatchMode=yes win-local-via-reverse-ssh whoami
ssh -o BatchMode=yes win-local-via-reverse-ssh 'cmd /c "cd /d D:\\AI\\Pivot_Client && cd"'
