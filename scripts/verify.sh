#!/usr/bin/env bash
# Quick health check: BGP sessions + full-mesh host reachability.
L=clab-wanlab
for n in hq-edge dc-edge br1-edge br2-edge isp1 isp2; do
  echo "== $n"; docker exec $L-$n vtysh -c "show bgp summary" | grep -E "^[0-9]" || true
done
echo; echo "== host reachability"
for s in hq:10.1 dc:10.2 br1:10.3 br2:10.4; do
  for d in hq:10.1 dc:10.2 br1:10.3 br2:10.4; do
    [ "${s%%:*}" = "${d%%:*}" ] && continue
    docker exec $L-${s%%:*}-host ping -c1 -W1 ${d##*:}.0.10 >/dev/null 2>&1 \
      && echo "OK   ${s%%:*} -> ${d%%:*}" || echo "FAIL ${s%%:*} -> ${d%%:*}"
  done
done
