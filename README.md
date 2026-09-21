# NetOps-agent-demo
# wanlab: multi-site WAN on Containerlab + FRR

```
        hq-host ─ hq-edge ═╦═ isp1 ══════ isp2 ═╦═ ...
        dc-host ─ dc-edge ═╣   │ (iBGP, AS65000) │
       br1-host ─ br1-edge ─╝   │                 └─ br2-edge ─ br2-host
                                └─ (hq, dc dual-homed; br1 on isp1; br2 on isp2)
```

| Site | ASN   | LAN         | Uplinks                    |
|------|-------|-------------|----------------------------|
| hq   | 65001 | 10.1.0.0/24 | isp1 (primary), isp2       |
| dc   | 65002 | 10.2.0.0/24 | isp1 (primary), isp2       |
| br1  | 65003 | 10.3.0.0/24 | isp1                       |
| br2  | 65004 | 10.4.0.0/24 | isp2                       |

Routing: each edge runs eBGP to the ISP (AS65000). ISPs peer iBGP with next-hop-self.
Dual-homed sites prefer isp1 (local-pref 200) and only advertise their own LAN
(no transit). Hosts sit at 10.X.0.10.

## Run it (in your WSL2 shell, in ~/labs, not /mnt/c)
```bash
cd wan-lab
sudo containerlab deploy -t wanlab.clab.yml
./scripts/verify.sh                       # all BGP Established, all hosts OK
docker exec -it clab-wanlab-hq-edge vtysh # interactive CLI
sudo containerlab destroy -t wanlab.clab.yml --cleanup
```
Change the design: edit `intent.yml`, run `python3 generate.py` (needs `pip install pyyaml`), redeploy.

## Break things (practice + agent test cases)
```bash
./scripts/faults.sh inject uplink-down      # hq loses primary exit; expect failover to isp2
./scripts/faults.sh inject wrong-asn        # br1 BGP session stuck
./scripts/faults.sh inject missing-network  # br2 LAN vanishes from the WAN
./scripts/faults.sh inject latency          # dc uplink slow/lossy (may need apk add iproute2-tc)
./scripts/faults.sh heal <fault>
```

## Layout
- `intent.yml` source of truth; `generate.py` builds the topology + configs
- `tools/lab_cli.py` read-only access layer (`show`, `ping`, `traceroute`), the agent's future tools
- `docs/BUILD_THE_AGENT.md` step-by-step guide to build the chat agent

Note: generated and syntax-checked, but not deployed by me (no Docker in my sandbox). If a
first deploy shows a problem, paste the error back and I'll fix it.