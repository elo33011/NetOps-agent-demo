# Build the chat agent: step-by-step

An agent is a loop: **model thinks → asks for a tool → you run it → feed result back → repeat
until it answers.** Everything else (safety, memory, UI) is layered on that loop.

```
you (chat) ─▶ agent loop ─▶ Claude API ◀─ system prompt + intent.yml
                 │  ▲
        tool call│  │result
                 ▼  │
           tools/lab_cli.py ─▶ docker exec ─▶ vtysh on FRR nodes
```

## Phase 0: Prerequisites
`pip install anthropic pyyaml`, `export ANTHROPIC_API_KEY=...`, lab deployed and `verify.sh` green.

## Phase 1: Learn the tool layer by hand (30 min)
Before any AI, do the troubleshooting yourself with `python tools/lab_cli.py`. Inject each fault
and write down the *exact* commands you ran to diagnose it. That list is your agent's playbook.
Typical: `show bgp summary` → `show ip route <prefix>` → `show bgp ipv4 unicast <prefix>` →
`show running-config` → ping/traceroute from hosts.

## Phase 2: Define tools as JSON schemas
The model only knows tools you describe. Keep them few, narrow and read-only first.

```python
TOOLS = [
 {"name": "show", "description": "Run a read-only FRR 'show' command on a lab router.",
  "input_schema": {"type": "object", "properties": {
     "node": {"type": "string", "enum": ["hq-edge","dc-edge","br1-edge","br2-edge","isp1","isp2"]},
     "command": {"type": "string", "description": "e.g. 'show bgp summary'"}},
   "required": ["node","command"]}},
 {"name": "ping", "description": "Ping an IPv4 address from a site host.",
  "input_schema": {"type": "object", "properties": {
     "host": {"type": "string", "enum": ["hq-host","dc-host","br1-host","br2-host"]},
     "target": {"type": "string"}}, "required": ["host","target"]}},
]
```
Enums matter: they stop the model inventing node names. `lab_cli.py` re-validates anyway.
Never trust the model's output as safe input; the guardrails live in *your* code.

## Phase 3: The agent loop
```python
import anthropic, yaml
from tools import lab_cli

client = anthropic.Anthropic()
INTENT = open("intent.yml").read()
SYSTEM = f"""You are a network troubleshooting assistant for a lab WAN (FRR, BGP).
Intended design (source of truth):
{INTENT}
Method: state a hypothesis, gather evidence with tools, compare actual vs intended,
then give root cause + fix commands. Never claim something you did not observe.
You are read-only: propose changes, do not apply them."""

DISPATCH = {"show": lambda a: lab_cli.show(a["node"], a["command"]),
            "ping": lambda a: lab_cli.ping(a["host"], a["target"])}

def chat(history):
    while True:
        r = client.messages.create(model="claude-sonnet-5", max_tokens=2000,
                                   system=SYSTEM, tools=TOOLS, messages=history)
        history.append({"role": "assistant", "content": r.content})
        if r.stop_reason != "tool_use":
            return "".join(b.text for b in r.content if b.type == "text")
        results = [{"type": "tool_result", "tool_use_id": b.id,
                    "content": DISPATCH[b.name](b.input)}
                   for b in r.content if b.type == "tool_use"]
        history.append({"role": "user", "content": results})

history = []
while True:
    history.append({"role": "user", "content": input("you> ")})
    print(chat(history))
```
That's the whole core, about 30 lines. Try: inject `wrong-asn`, then ask *"br1 can't reach hq, why?"*

## Phase 4: Make it good
1. **Playbook in the prompt.** Paste your Phase 1 command sequence as a checklist.
2. **Intent vs actual.** The `intent.yml` in the prompt lets it spot drift (wrong ASN, missing prefix).
3. **Output control.** Truncate huge outputs in `_run`; long `show` output burns context.
4. **Log every tool call** (node, command, output) to a file: your audit trail and debugging aid.

## Phase 5: Configuration with human approval
Add a `propose_change(node, commands[])` tool that does **not** apply anything: it prints the
commands and a diff and waits for you to type `yes`. Only then run `vtysh -c "conf t" -c ...`.
Add: snapshot `show running-config` before, verify after, auto-rollback if `verify.sh` fails.
Rule of thumb: the model proposes, deterministic code disposes.

## Phase 6: Test it like software
Build a loop: inject fault → ask the agent → check its diagnosis names the right node and cause →
heal. Four faults in `faults.sh` = four regression tests. Score: correct root cause, number of
tool calls, no hallucinated facts. Rerun after every prompt change.

## Phase 7: Extensions
- Swap FRR for real NX-OS/cEOS behind the same `lab_cli` interface (only the tool layer changes)
- Wrap the loop in a web UI (Streamlit/FastAPI) or Slack bot
- Add NetBox/Ansible tools so config generation flows from a real source of truth
- Move to MCP: expose `lab_cli` as an MCP server so any client can use it

## Common pitfalls
- Giving the model a raw shell tool: use allowlisted, validated functions instead
- No approval gate on writes
- Skipping evals, so you can't tell whether a prompt tweak helped
