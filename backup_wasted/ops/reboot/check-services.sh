#!/usr/bin/env bash

set -u

echo "==> systemd units"
for unit in \
  wg-quick@wg0.service \
  wg-iptables.service \
  cccc-wg-proxy.service \
  docker.service \
  pivot-swarm-adapter.service \
  site_total.service \
  php-fpm.service \
  sshd.service \
  postfix.service
do
  printf '%-32s active=%s enabled=%s\n' \
    "${unit}" \
    "$(systemctl is-active "${unit}" 2>/dev/null || true)" \
    "$(systemctl is-enabled "${unit}" 2>/dev/null || true)"
done

echo
echo "==> BT panel"
bt status || true

echo
echo "==> BT MySQL / PHP 8.0 / Nginx processes"
pgrep -fa '/www/server/mysql/bin/mysqld|php-fpm: master process \(/www/server/php/80/etc/php-fpm.conf\)|/www/server/nginx/sbin/nginx' || true

echo
echo "==> WireGuard"
wg show || true

echo
echo "==> Docker stack"
docker stack services portainer || true

echo
echo "==> Listening ports"
ss -lntup | rg ':(22|2222|80|443|888|24746|3306|8010|8848|9443|45182)\b' || true

echo
echo "==> Failed units"
systemctl --failed --no-pager --no-legend || true

