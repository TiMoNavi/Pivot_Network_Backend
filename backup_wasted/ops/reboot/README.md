# Server Reboot Recovery Record

Recorded at: `2026-04-05T03:47:53+08:00`
Host: `VM-0-3-opencloudos`
Private IP: `10.2.0.3/22`
Repo root: `/root/Pivot_network`

Scope:
- This file records restart-relevant services and commands observed running before the reboot.
- It intentionally skips generic kernel processes and most vendor/cloud agents.

## Recovery Order

1. Bring up WireGuard: `systemctl start wg-quick@wg0.service`
2. Restore extra iptables rules: `systemctl start wg-iptables.service`
3. Start the TCP proxy on `8848`: `systemctl start cccc-wg-proxy.service`
4. Start Docker: `systemctl start docker.service`
5. Reconcile the Portainer Swarm stack: `/root/Pivot_network/Docker_Swarm/scripts/deploy-portainer.sh`
6. Start the Pivot adapter: `systemctl start pivot-swarm-adapter.service`
7. Start site-total and system PHP: `systemctl start site_total.service php-fpm.service`
8. Start BT panel: `bt start`
9. Start BT MySQL: `/etc/rc.d/init.d/mysqld start`
10. Start BT PHP 8.0: `/etc/rc.d/init.d/php-fpm-80 start`
11. Start BT Nginx: `/etc/rc.d/init.d/nginx start`

## Current Runtime Inventory

### WireGuard

- Unit: `wg-quick@wg0.service`
- State when recorded: `active (exited)` and `enabled`
- Runtime process: `wireguard-go wg0`
- Startup command: `/usr/bin/wg-quick up wg0`
- Config file: `/etc/wireguard/wg0.conf`
- Verify: `wg show`
- Notes:
  - `wg0.conf` sets `ListenPort = 45182`
  - `wg0.conf` also adds `iptables` rules for `45182/udp` in `PostUp`

### Extra WireGuard iptables helper

- Unit: `wg-iptables.service`
- State when recorded: `active (exited)` and `enabled`
- Startup commands:
  - `/usr/sbin/iptables -w 5 -t nat -A POSTROUTING -s 10.7.0.0/24 ! -d 10.7.0.0/24 -j MASQUERADE`
  - `/usr/sbin/iptables -w 5 -I INPUT -p udp --dport 51820 -j ACCEPT`
  - `/usr/sbin/iptables -w 5 -I FORWARD -s 10.7.0.0/24 -j ACCEPT`
  - `/usr/sbin/iptables -w 5 -I FORWARD -m state --state RELATED,ESTABLISHED -j ACCEPT`
- Notes:
  - This helper still inserts `51820/udp`, while `wg0` itself listens on `45182/udp`
  - Current host firewall already exposes `45182/udp`, so the tunnel is working now

### WireGuard TCP proxy

- Unit: `cccc-wg-proxy.service`
- State when recorded: `active (running)` and `enabled`
- Startup command: `/usr/bin/python3 /usr/local/bin/cccc-wg-proxy.py`
- Script path: `/usr/local/bin/cccc-wg-proxy.py`
- Listening port: `8848/tcp`
- Proxy target: `10.7.1.2:8848`
- Verify: `ss -lntup | rg ':8848\\b'`

### Docker and Swarm

- Unit: `docker.service`
- State when recorded: `active (running)` and `enabled`
- Startup command: `/usr/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock`
- Swarm state when recorded: `active`
- Manager address: `81.70.52.75:2377`
- Verify:
  - `docker info --format '{{.Swarm.LocalNodeState}}'`
  - `docker service ls`

### Portainer stack

- Runtime shape when recorded:
  - `portainer_agent` global service, `1/1`
  - `portainer_portainer` replicated service, `1/1`, publishing `9443/tcp`
- Preferred recovery command:
  - `/root/Pivot_network/Docker_Swarm/scripts/deploy-portainer.sh`
- Equivalent direct command:
  - `docker stack deploy --compose-file /root/Pivot_network/Docker_Swarm/stack/portainer-agent-stack.yml portainer`
- Compose file:
  - `/root/Pivot_network/Docker_Swarm/stack/portainer-agent-stack.yml`
- Env file used by the deploy script:
  - `/root/Pivot_network/Docker_Swarm/env/swarm.env`
- Verify:
  - `docker stack services portainer`
  - `ss -lntup | rg ':9443\\b'`

### Pivot Docker Swarm Adapter

- Unit: `pivot-swarm-adapter.service`
- State when recorded: `active (running)` and `enabled`
- Working directory: `/root/Pivot_network/Docker_Swarm/Docker_Swarm_Adapter`
- Environment file: `/root/Pivot_network/Docker_Swarm/Docker_Swarm_Adapter/.env`
- Startup command:
  - `/root/Pivot_network/Docker_Swarm/Docker_Swarm_Adapter/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8010`
- Listening port: `8010/tcp`
- Verify: `ss -lntup | rg ':8010\\b'`

### Site Total

- Unit: `site_total.service`
- State when recorded: `active (running)` and `enabled`
- Working directory: `/www/server/site_total`
- Startup command: `/www/server/site_total/site_total`

### System PHP-FPM

- Unit: `php-fpm.service`
- State when recorded: `active (running)` and `enabled`
- Startup command: `/usr/sbin/php-fpm --nodaemonize`
- Notes:
  - This is separate from BT PHP 8.0 below

### BT panel

- Init script: `/etc/rc.d/init.d/bt`
- Friendly command: `bt start`
- State when recorded: `BT-Panel` and `BT-Task` both running
- Current process commands:
  - `/www/server/panel/pyenv/bin/python3 /www/server/panel/BT-Panel`
  - `/www/server/panel/pyenv/bin/python3 /www/server/panel/BT-Task`
- Panel listening port: `24746/tcp`
- Boot status:
  - `chkconfig` shows runlevels `2,3,4,5` as `on`
  - `bt.service` exists only as a generated SysV wrapper
- Verify:
  - `bt status`
  - `ss -lntup | rg ':24746\\b'`

### BT MySQL

- Init script: `/etc/rc.d/init.d/mysqld`
- Friendly command: `/etc/rc.d/init.d/mysqld start`
- State when recorded: running
- Current process commands:
  - `/bin/sh /www/server/mysql/bin/mysqld_safe --defaults-file=/etc/my.cnf --datadir=/www/server/data --pid-file=/www/server/data/VM-0-3-opencloudos.pid`
  - `/www/server/mysql/bin/mysqld --defaults-file=/etc/my.cnf --basedir=/www/server/mysql --datadir=/www/server/data --plugin-dir=/www/server/mysql/lib/plugin --user=mysql --log-error=VM-0-3-opencloudos.err --open-files-limit=65535 --pid-file=/www/server/data/VM-0-3-opencloudos.pid --socket=/tmp/mysql.sock --port=3306`
- Listening port: `3306/tcp`
- Boot status:
  - `chkconfig` shows runlevels `2,3,4,5` as `on`
- Important note:
  - `systemctl --failed` currently shows `mysqld.service` and `mariadb.service` as failed aliases, even though the BT MySQL process is running
  - Prefer the BT init script and process checks over `systemctl status mysqld.service`

### BT PHP 8.0

- Init script: `/etc/rc.d/init.d/php-fpm-80`
- Friendly command: `/etc/rc.d/init.d/php-fpm-80 start`
- State when recorded: running
- Current master process:
  - `php-fpm: master process (/www/server/php/80/etc/php-fpm.conf)`
- Boot status:
  - `chkconfig` shows runlevels `2,3,4,5` as `on`

### BT Nginx

- Init script: `/etc/rc.d/init.d/nginx`
- Friendly command: `/etc/rc.d/init.d/nginx start`
- State when recorded: running
- Current master process command:
  - `/www/server/nginx/sbin/nginx -c /www/server/nginx/conf/nginx.conf`
- Listening ports when recorded:
  - `80/tcp`
  - `443/tcp`
  - `443/udp`
  - `888/tcp`
- Boot status:
  - `chkconfig --list nginx` shows all runlevels `off`
  - `/etc/rc.d/rc3.d` has `K25nginx` but no `S*nginx` start link
- Important note:
  - This is the main service to watch after reboot because it is not currently configured to auto-start at runlevel 3

## Quick Verification Commands

- Full post-reboot check:
  - `/root/Pivot_network/ops/reboot/check-services.sh`
- Targeted port check:
  - `ss -lntup | rg ':(22|2222|80|443|888|24746|3306|8010|8848|9443|45182)\\b'`
- Failed units:
  - `systemctl --failed --no-pager --no-legend`

