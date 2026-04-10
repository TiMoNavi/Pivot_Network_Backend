#!/usr/bin/env bash

set -euo pipefail

REPO_ROOT="/root/Pivot_network"

start_unit() {
  local unit="$1"
  echo "==> systemctl start ${unit}"
  systemctl start "${unit}"
}

wait_for_docker() {
  local i
  for i in $(seq 1 30); do
    if docker info >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done

  echo "Docker did not become ready within 30 seconds" >&2
  return 1
}

echo "==> bringing up WireGuard and related rules"
start_unit "wg-quick@wg0.service"
start_unit "wg-iptables.service"
start_unit "cccc-wg-proxy.service"

echo "==> bringing up Docker and Swarm-managed services"
start_unit "docker.service"
wait_for_docker
bash "${REPO_ROOT}/Docker_Swarm/scripts/deploy-portainer.sh"

echo "==> bringing up repo services"
start_unit "pivot-swarm-adapter.service"
start_unit "site_total.service"
start_unit "php-fpm.service"

echo "==> bringing up BT-managed services"
bt start

if pgrep -x mysqld >/dev/null 2>&1; then
  echo "==> BT MySQL already running"
else
  /etc/rc.d/init.d/mysqld start
fi

if pgrep -fa '/www/server/php/80/.*/php-fpm|php-fpm: master process \(/www/server/php/80/etc/php-fpm.conf\)' >/dev/null 2>&1; then
  echo "==> BT PHP 8.0 already running"
else
  /etc/rc.d/init.d/php-fpm-80 start
fi

if pgrep -fa '/www/server/nginx/sbin/nginx' >/dev/null 2>&1; then
  echo "==> BT Nginx already running"
else
  /etc/rc.d/init.d/nginx start
fi

echo "==> recovery sequence finished"
echo "==> run ${REPO_ROOT}/ops/reboot/check-services.sh for verification"

