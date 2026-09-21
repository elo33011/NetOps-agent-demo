#!/usr/bin/env python3
"""Lab access layer: the ONLY thing the future agent touches.
Read-only by design. Run: python tools/lab_cli.py hq-edge "show bgp summary"
"""
import subprocess, sys

LAB = "clab-wanlab"
ROUTERS = ["hq-edge", "dc-edge", "br1-edge", "br2-edge", "isp1", "isp2"]
HOSTS = ["hq-host", "dc-host", "br1-host", "br2-host"]

def _run(argv, timeout=15):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return (p.stdout + p.stderr).strip()

def show(node: str, command: str) -> str:
    """Run a read-only FRR 'show' command on a router."""
    if node not in ROUTERS:
        return f"ERROR: unknown router '{node}'. Valid: {ROUTERS}"
    if not command.strip().startswith("show ") or any(c in command for c in ";|&`$"):
        return "ERROR: only plain 'show ...' commands are allowed"
    return _run(["docker", "exec", f"{LAB}-{node}", "vtysh", "-c", command])

def ping(host: str, target: str, count: int = 3) -> str:
    """Ping from a lab host to an IP address."""
    if host not in HOSTS:
        return f"ERROR: unknown host '{host}'. Valid: {HOSTS}"
    if not target.replace(".", "").isdigit():
        return "ERROR: target must be an IPv4 address"
    return _run(["docker", "exec", f"{LAB}-{host}", "ping", "-c", str(count), "-W", "1", target])

def traceroute(host: str, target: str) -> str:
    if host not in HOSTS or not target.replace(".", "").isdigit():
        return "ERROR: bad host or target"
    return _run(["docker", "exec", f"{LAB}-{host}", "traceroute", "-n", "-w", "1", target], timeout=30)

if __name__ == "__main__":
    print(show(sys.argv[1], sys.argv[2]))
