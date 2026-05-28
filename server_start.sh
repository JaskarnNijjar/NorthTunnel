#!/bin/bash
set -e

if [ "$(cat /proc/sys/net/ipv4/ip_forward)" != "1" ]; then
  echo "ERROR: net.ipv4.ip_forward is not 1 — set it via docker-compose sysctls" >&2
  exit 1
fi

iptables -t nat -A POSTROUTING -s 10.0.0.0/24 -o eth0 -j MASQUERADE
iptables -A FORWARD -i tun0 -o eth0 -j ACCEPT
iptables -A FORWARD -i eth0 -o tun0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT

python vpn_server.py &
PY_PID=$!

for i in 1 2 3 4 5; do
  if ip link show tun0 >/dev/null 2>&1; then
    ethtool -K tun0 tx off rx off || true
    break
  fi
  sleep 1
done

wait $PY_PID