#!/usr/bin/env python3
"""Generate wanlab.clab.yml + FRR configs from intent.yml."""
import ipaddress as ip, pathlib, yaml

root = pathlib.Path(__file__).parent
d = yaml.safe_load((root / "intent.yml").read_text())
cfg = root / "configs"
name, isp_asn = d["lab_name"], d["isp"]["asn"]

nodes, links = {}, []          # nodes[n] = {"kind","ifaces":{eth:ip/len},"frr":str|None,"routes":[]}
rid = iter(range(1, 100))

def node(n, kind):
    nodes[n] = {"kind": kind, "ifaces": {}, "frr": None, "cmds": []}

def conf_bgp(asn, rid_, neighbors, nets=(), extra=""):
    s = f"router bgp {asn}\n bgp router-id 1.1.1.{rid_}\n no bgp ebgp-requires-policy\n"
    for n in neighbors:
        s += f" neighbor {n['ip']} remote-as {n['asn']}\n neighbor {n['ip']} description {n['desc']}\n"
    s += " !\n address-family ipv4 unicast\n"
    for x in nets:
        s += f"  network {x}\n"
    for n in neighbors:
        for line in n.get("af", []):
            s += f"  neighbor {n['ip']} {line}\n"
    s += " exit-address-family\n!\n"
    return s

hdr = lambda h: f"frr defaults traditional\nhostname {h}\nlog stdout informational\nservice integrated-vtysh-config\n!\n"

# --- ISP routers -----------------------------------------------------------
core = ip.ip_network(d["isp"]["core_link"]); c1, c2 = list(core.hosts())[:2]
for r in ("isp1", "isp2"):
    node(r, "router")
nodes["isp1"]["ifaces"]["eth1"] = f"{c1}/{core.prefixlen}"
nodes["isp2"]["ifaces"]["eth1"] = f"{c2}/{core.prefixlen}"
links.append(("isp1:eth1", "isp2:eth1"))
isp_nb = {"isp1": [{"ip": str(c2), "asn": isp_asn, "desc": "isp2-ibgp", "af": ["next-hop-self"]}],
          "isp2": [{"ip": str(c1), "asn": isp_asn, "desc": "isp1-ibgp", "af": ["next-hop-self"]}]}
isp_if = {"isp1": 2, "isp2": 2}

# --- Sites -----------------------------------------------------------------
for s in d["sites"]:
    e, h = f"{s['name']}-edge", f"{s['name']}-host"
    node(e, "router"); node(h, "host")
    lan = ip.ip_network(s["lan"]); gw, hostip = lan.network_address + 1, lan.network_address + 10
    nbs, pfx = [], f"ip prefix-list OWN-LAN seq 5 permit {lan}\n!\nroute-map TO-ISP permit 10\n match ip address prefix-list OWN-LAN\n!\n" \
                   "route-map FROM-ISP-PRIMARY permit 10\n set local-preference 200\n!\nroute-map FROM-ISP permit 10\n!\n"
    for i, u in enumerate(s["uplinks"], start=1):
        sub = ip.ip_network(u["subnet"]); a, b = list(sub.hosts())[:2]   # a=isp, b=edge
        eth = f"eth{i}"; ieth = f"eth{isp_if[u['isp']]}"; isp_if[u["isp"]] += 1
        nodes[e]["ifaces"][eth] = f"{b}/{sub.prefixlen}"
        nodes[u["isp"]]["ifaces"][ieth] = f"{a}/{sub.prefixlen}"
        links.append((f"{e}:{eth}", f"{u['isp']}:{ieth}"))
        rm = "FROM-ISP-PRIMARY" if u.get("primary") else "FROM-ISP"
        nbs.append({"ip": str(a), "asn": isp_asn, "desc": u["isp"], "af": [f"route-map {rm} in", "route-map TO-ISP out"]})
        isp_nb[u["isp"]].append({"ip": str(b), "asn": s["asn"], "desc": e})
    lan_eth = f"eth{len(s['uplinks']) + 1}"
    nodes[e]["ifaces"][lan_eth] = f"{gw}/{lan.prefixlen}"
    nodes[h]["ifaces"]["eth1"] = f"{hostip}/{lan.prefixlen}"
    nodes[h]["cmds"] = [f"ip route replace default via {gw}"]
    links.append((f"{e}:{lan_eth}", f"{h}:eth1"))
    nodes[e]["frr"] = hdr(e) + pfx + conf_bgp(s["asn"], next(rid), nbs, [lan])

for r in ("isp1", "isp2"):
    nodes[r]["frr"] = hdr(r) + conf_bgp(isp_asn, next(rid), isp_nb[r])

# --- Write files -----------------------------------------------------------
cfg.mkdir(exist_ok=True)
(cfg / "daemons").write_text("bgpd=yes\nospfd=no\nospf6d=no\nripd=no\nripngd=no\nisisd=no\npimd=no\nldpd=no\nnhrpd=no\neigrpd=no\nbabeld=no\nsharpd=no\npbrd=no\nbfdd=no\nfabricd=no\nvrrpd=no\npathd=no\nvtysh_enable=yes\nzebra_options=\"  -A 127.0.0.1 -s 90000000\"\nbgpd_options=\"   -A 127.0.0.1\"\nstaticd_options=\"-A 127.0.0.1\"\n")
out = f"name: {name}\n\nmgmt:\n  network: {name}-mgmt\n  ipv4-subnet: {d['mgmt_subnet']}\n\ntopology:\n  nodes:\n"
for n, v in nodes.items():
    if v["kind"] == "router":
        (cfg / n).mkdir(exist_ok=True); (cfg / n / "frr.conf").write_text(v["frr"])
        out += f"    {n}:\n      kind: linux\n      image: {d['frr_image']}\n      binds:\n        - configs/{n}/frr.conf:/etc/frr/frr.conf\n        - configs/daemons:/etc/frr/daemons\n"
    else:
        out += f"    {n}:\n      kind: linux\n      image: {d['host_image']}\n"
    cmds = [f"ip addr add {a} dev {e}" for e, a in v["ifaces"].items()] + v["cmds"]
    out += "      exec:\n" + "".join(f"        - {c}\n" for c in cmds)
out += "\n  links:\n" + "".join(f"    - endpoints: [\"{a}\", \"{b}\"]\n" for a, b in links)
(root / f"{name}.clab.yml").write_text(out)
print("generated", f"{name}.clab.yml", "and", sum(1 for v in nodes.values() if v['frr']), "FRR configs")
