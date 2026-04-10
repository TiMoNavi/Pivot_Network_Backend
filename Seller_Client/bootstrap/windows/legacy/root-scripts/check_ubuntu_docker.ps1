$ErrorActionPreference = 'Stop'
wsl.exe -d Ubuntu sh -lc 'systemctl is-active docker; echo ---; docker version 2>/dev/null | sed -n "1,20p"; echo ---; docker info 2>/dev/null | sed -n "1,60p"'
