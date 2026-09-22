# NetOps Agent Demo

This is a show case of a Network Operation Agent supporting a network topology. Why it helps


- Network Ops Agent is a chat agent
- Ask questions about the network health
- Request sent to the model (We use Ollama free cloud model here)
- Model request to use the tool and find out the answer

Any agent, inclulding this one, is a loop: User prompt → model thinks → asks help via tools → feed result back → repeat until it answers → response back to User. 
Guardrail (safety, memory, UI) is layered on that loop, which is harness

```
User (chat) ─▶ agent loop ─▶ Model API ◀─ system prompt + intent.yml
                 │  ▲
        tool call│  │result
                 ▼  │
           tools/lab_cli.py ─▶ docker exec ─▶ vtysh on FRR nodes (containered network devices)
```

# Network Topology

<div style="flex: 1;">
  <img src="wanlab_topology.png" width="800">
</div>
  
Routing: each edge runs eBGP to the ISP (AS65000). ISPs peer iBGP with next-hop-self.
Dual-homed sites prefer isp1 (local-pref 200) and only advertise their own LAN
(no transit). Hosts sit at 10.X.0.10.

# How to Run it

Part 1: Prerequisites (done once)
You already have these, so just confirm:
```bash
docker run hello-world          # Docker works in WSL2
containerlab version            # Containerlab works
```
Part 2: The lab
Get the files. Unzip `wan-lab.zip` (the latest version, which includes the `vtysh.conf` fix) into your WSL home folder:
```bash
   cd ~
   unzip wan-lab.zip            # sudo apt install -y unzip, if needed
   cd wan-lab
   ```
Deploy the lab:
```bash
   sudo containerlab deploy -t wanlab.clab.yml
   ```
Check it's healthy:
```bash
   ./scripts/verify.sh
   ```
Expect 6 BGP sessions `Established` and 12 host pairs `OK`. BGP can take up to 30 seconds to come up after deploy.
Part 3: Python environment
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
Part 4: The agent
Copy the latest `agent_ollama.py` into `~/wan-lab/`, next to `tools/` and `intent.yml`. It is not in the zip. Confirm it's the right version:
```bash
   grep OLLAMA_API_KEY agent_ollama.py
   ```
Create an Ollama API key in your Ollama account settings (ollama.com/settings/keys) and copy it.
Set your environment variables. Repeat this in every new terminal:
```bash
   export OLLAMA_API_KEY="your-key"
   export OLLAMA_MODEL=gpt-oss:20b
   export MAX_OUTPUT=8000
   ```
See which models your account can use, and change `OLLAMA_MODEL` if `gpt-oss:20b` isn't listed:
```bash
   curl -H "Authorization: Bearer $OLLAMA_API_KEY" https://ollama.com/api/tags
   ```
Part 5: First test (two terminals)
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
Not needed on this path
Installing Ollama in WSL
`ollama serve`
`ollama signin`
`agent.py` and `agent_openai.py`
If you deployed the lab from the older zip
Your running lab still prints `vtysh.conf` warnings. Either redeploy from the new zip, or run this once:
```bash
for n in hq-edge dc-edge br1-edge br2-edge isp1 isp2; do
  docker exec clab-wanlab-$n touch /etc/frr/vtysh.conf
done
```


## Scripts in `~/wan-lab`

| File | What it does | Do you need it? |
|---|---|---|
| `wanlab.clab.yml` | The lab topology for Containerlab | Yes |
| `configs/` | FRR configs for each router | Yes |
| `intent.yml` | Intended design; the agent reads it | Yes |
| `generate.py` | Rebuilds the topology and configs from `intent.yml` | Only if you change the design |
| `scripts/verify.sh` | Health check: BGP sessions and host reachability | Yes |
| `scripts/faults.sh` | Injects and heals faults | Yes |
| `tools/lab_cli.py` | Read-only `show`, `ping` and `traceroute` that the agent uses | Yes |
| `agent_ollama.py` | The chat agent for Ollama (latest version) | Yes |
| `agent_audit.log` | Created by the agent; every command it ran | Created automatically |
