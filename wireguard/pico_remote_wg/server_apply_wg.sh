#!/usr/bin/env bash
set -euo pipefail

WG_CONF_SRC="${1:-./server-wg0.conf}"
WG_CONF_DST="/etc/wireguard/wg0.conf"

if command -v apt-get >/dev/null 2>&1; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y wireguard iptables
elif command -v dnf >/dev/null 2>&1; then
  dnf install -y wireguard-tools iptables
elif command -v yum >/dev/null 2>&1; then
  yum install -y epel-release || true
  yum install -y wireguard-tools iptables
else
  echo "Unsupported package manager. Install wireguard manually." >&2
  exit 1
fi

install -d -m 700 /etc/wireguard
install -m 600 "$WG_CONF_SRC" "$WG_CONF_DST"
sysctl -w net.ipv4.ip_forward=1
grep -q '^net.ipv4.ip_forward=1$' /etc/sysctl.conf || echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf

if command -v systemctl >/dev/null 2>&1; then
  systemctl enable wg-quick@wg0
  systemctl restart wg-quick@wg0
  systemctl --no-pager --full status wg-quick@wg0 || true
else
  wg-quick down wg0 || true
  wg-quick up wg0
fi

ss -lunp | grep 45182 || true
wg show || true
