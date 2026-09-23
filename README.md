# NetOps Agent Demo

This is a simple show case of a Network Operation Agent supporting a network topology. By using a chat prompt, you ask the agent to check the health of the network and perform troubleshooting if there is any issue. Treat it like an network engineer.

## Concept

Any agent, inclulding this one, is a loop: User prompt → model thinks → asks help via tools → feed result back → repeat until it answers → response back to User. 
Guardrail (safety, memory, UI) is layered on that loop.

```
User (chat) ─▶ agent loop ─▶ Model API ◀─ system prompt + intent.yml
                 │  ▲
        tool call│  │result
                 ▼  │
           tools/lab_cli.py ─▶ docker exec ─▶ vtysh on FRR nodes (containered network devices)
```

## Network Topology

A simple network topology consisting of four sites (HQ, DC, Branch 1, Branch 2), each with an FRR edge router and a test host, connect via eBGP to two ISP routers (AS65000, iBGP between them). HQ and DC are dual-homed to both ISPs, preferring ISP1. Branch 1 uses ISP1 only, Branch 2 uses ISP2 only. No site provides transit.

<div style="flex: 1;">
  <img src="wanlab_topology.png" width="800">
</div>
  
Routing setup: each edge runs eBGP to the ISP (AS65000). ISPs peer iBGP with next-hop-self.
Dual-homed sites prefer isp1 (local-pref 200) and only advertise their own LAN
(no transit). Hosts sit at 10.X.0.10.

## How the Demo works ?

- The network topology was built on container lab. All simulated device (FRR node) are running healthy
- Devices are asseessbile via cli (docker exec) both manually or by the agent
- The agent prompt runs in parallel and ready for you to query the status of the network topology
- We then inject a changes to break the network, causing some kind of issues.
- As the agent prompt to perform troubleshooting of the issues, and find out the root case, suggest the fix
- The following faults can be injested.

| Fault | What breaks | Symptom |
|---|---|---|
| `uplink-down` | HQ's link to ISP1 goes down | HQ fails over to ISP2 as its exit |
| `wrong-asn` | Branch 1's neighbor `remote-as` is changed to 65099 (should be 65000) | BGP session to ISP1 stuck `Idle`; Branch 1 isolated from every other site |
| `missing-network` | Branch 2's LAN prefix is withdrawn from BGP | BGP session stays `Established`, but Branch 2's LAN is unreachable from everywhere |
| `latency` | 200 ms delay and 20% loss added to DC's ISP1 link | DC traffic is slow and lossy, but BGP sessions look fine |

# How to Run it

## Step 1: Install docker & containerlab in your shell environment
Once it is done, confirm this is in place.
```bash
docker run hello-world          # Docker works in WSL2
containerlab version            # Containerlab works
```

## Step 2: Build the network topology
Get the files. Unzip `wan-lab.zip` your home folder:
```bash
   cd ~
   unzip wan-lab.zip            # sudo apt install -y unzip, if needed
   cd wan-lab
   ```
Deploy the network topology:
```bash
   sudo containerlab deploy -t wanlab.clab.yml
   ```
Check it's healthy:
```bash
   ./scripts/verify.sh
   ```

Expect 6 BGP sessions `Established` and 12 host pairs `OK`. BGP can take up to 30 seconds to come up after deploy.

## Step 3: Python environment
Create and activate a venv:
```bash
   sudo apt install -y python3-venv     # only if the next line errors
   python3 -m venv .venv
   source .venv/bin/activate
   ```
Install the packages:
```bash
   pip install ollama pyyaml
   ```

## Step 4: Setup the agent

Create an Ollama API key in your Ollama account settings (ollama.com/settings/keys) and copy it.
Set your environment variables:
```bash
   export OLLAMA_API_KEY="your-key"
   export OLLAMA_MODEL=gpt-oss:20b
   export MAX_OUTPUT=8000
   ```
See which models your account can use, and change `OLLAMA_MODEL` if `gpt-oss:20b` isn't listed:
```bash
   curl -H "Authorization: Bearer $OLLAMA_API_KEY" https://ollama.com/api/tags
   ```

## Step 5: Run the Demo via two terminals

Terminal 1: inject a fault.

```bash
    cd ~/wan-lab
    ./scripts/faults.sh inject wrong-asn
```

Terminal 2: start the agent and ask.

```bash
    cd ~/wan-lab && source .venv/bin/activate
    # re-export the three variables from step 8 here
    python3 agent_ollama.py
```

At `you>`, type: `hq -> br1 fail, can you tell me why?`

Terminal 1: review and heal.

```bash
    cat agent_audit.log
    ./scripts/faults.sh heal wrong-asn
```

```bash
    cd ~/wan-lab
    ./scripts/faults.sh heals wrong-asn
```

## Repository Content

| File | What it does | Do you need it? |
|---|---|---|
| `wanlab.clab.yml` | The lab topology for Containerlab | Yes |
| `configs/` | FRR configs for each router | Yes |
| `intent.yml` | Intended design; the agent reads it | Yes |
| `generate.py` | Rebuilds the topology and configs from `intent.yml` | Only if you change the design |
| `scripts/verify.sh` | Health check: BGP sessions and host reachability | Yes |
| `scripts/faults.sh` | Injects and heals faults | Yes |
| `tools/lab_cli.py` | Read-only `show`, `ping` and `traceroute` that the agent uses | Yes |
| `agent_ollama.py` | The chat agent based on Ollama supplied models | Yes |
| `agent_audit.log` | Created by the agent; every command it ran | Created automatically |
