# Windows SSH Notes

Updated: 2026-04-11

Preferred entry:

```bash
ssh win-local-via-reverse-ssh
```

Start local sshd on Windows:

```powershell
Set-Service -Name sshd -StartupType Automatic
Start-Service sshd
Get-Service sshd
Get-NetTCPConnection -LocalPort 22 -State Listen
```

Start reverse tunnel on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File "D:\AI\Pivot_backend_build_team\scripts\run_reverse_ssh_tunnel.ps1"
```

Workspace after login:

```cmd
cd /d D:\AI\Pivot_Client
```
