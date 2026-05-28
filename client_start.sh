#!/bin/bash

SERVER_IP=$(getent hosts server_service | awk '{print $1}')
echo "Server IP: $SERVER_IP"

python vpn_client.py &

sleep 2

ip addr show tun0 2>&1
echo "tun0 check done"

ethtool -K tun0 tx off rx off 2>&1 || true
echo "tun0 offload disabled"

ip route add $SERVER_IP via $(ip route | grep default | awk '{print $3}') 2>&1
echo "Route add done"

ip route replace default via 10.0.0.1 dev tun0 2>&1
echo "Route replace done"

ip route show
echo "Final routes"

wait
