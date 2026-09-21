#!/usr/bin/env bash
# Fault injector for the wanlab. Usage: faults.sh <inject|heal> <fault>
# Faults: uplink-down | wrong-asn | missing-network | latency
set -euo pipefail
L=clab-wanlab
v() { docker exec "$L-$1" vtysh "${@:2}"; }

case "${1:-}/${2:-}" in
  inject/uplink-down)      docker exec $L-hq-edge ip link set eth1 down ;;
  heal/uplink-down)        docker exec $L-hq-edge ip link set eth1 up ;;
  inject/wrong-asn)        v br1-edge -c "conf t" -c "router bgp 65003" -c "no neighbor 172.16.5.1 remote-as 65000" -c "neighbor 172.16.5.1 remote-as 65099" ;;
  heal/wrong-asn)          v br1-edge -c "conf t" -c "router bgp 65003" -c "no neighbor 172.16.5.1 remote-as 65099" -c "neighbor 172.16.5.1 remote-as 65000" ;;
  inject/missing-network)  v br2-edge -c "conf t" -c "router bgp 65004" -c "address-family ipv4 unicast" -c "no network 10.4.0.0/24" ;;
  heal/missing-network)    v br2-edge -c "conf t" -c "router bgp 65004" -c "address-family ipv4 unicast" -c "network 10.4.0.0/24" ;;
  inject/latency)          docker exec $L-dc-edge tc qdisc add dev eth1 root netem delay 200ms loss 20% \
                             || echo "tc missing: docker exec $L-dc-edge apk add iproute2-tc  (then retry)" ;;
  heal/latency)            docker exec $L-dc-edge tc qdisc del dev eth1 root ;;
  *) sed -n 2,3p "$0"; exit 1 ;;
esac
echo "$1 $2: done"
