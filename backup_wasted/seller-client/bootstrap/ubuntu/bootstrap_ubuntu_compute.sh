#!/usr/bin/env bash

set -euo pipefail

echo "[pivot] bootstrap Ubuntu compute environment"
echo "[pivot] this script is intended to run inside WSL Ubuntu"

sudo apt-get update
sudo apt-get install -y docker.io wireguard-tools iproute2 iptables

sudo mkdir -p /opt/pivot/compute /opt/pivot/workspace /opt/pivot/logs

echo "[pivot] docker.io and wireguard-tools installed"
echo "[pivot] write compute peer config to /etc/wireguard/wg-compute.conf"
echo "[pivot] then join swarm with the bootstrap payload returned by Backend"
