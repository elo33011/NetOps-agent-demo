#!/usr/bin/env python3
"""wanlab troubleshooting agent (read-only), Ollama version.

Run from the wan-lab folder:  python3 agent_ollama.py
Needs: pip install ollama pyyaml, Ollama running, and a tool-capable model pulled
(e.g. ollama pull qwen3:14b), or a cloud model after 'ollama signin'.
Cloud without a local install: export OLLAMA_API_KEY=... and use a plain name like gpt-oss:120b.
Set OLLAMA_MODEL to choose the model, e.g. OLLAMA_MODEL=gpt-oss:120b-cloud.
"""
import datetime
import json
import os

import ollama

from tools import lab_cli

MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:14b")
MAX_STEPS = 12          # hard cap on tool-use rounds per question
MAX_OUTPUT = int(os.environ.get("MAX_OUTPUT", "4000"))   # local: keep small; cloud models can take more
AUDIT_LOG = "agent_audit.log"

# Direct cloud mode: set OLLAMA_API_KEY and no local Ollama install is needed.
# Optional OLLAMA_HOST overrides the endpoint (default https://ollama.com in cloud mode).
API_KEY = os.environ.get("OLLAMA_API_KEY")
if API_KEY:
    client = ollama.Client(
        host=os.environ.get("OLLAMA_HOST", "https://ollama.com"),
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
else:
    client = ollama.Client()        # local daemon on localhost:11434

INTENT = open("intent.yml").read()

SYSTEM = f"""You are a network troubleshooting assistant for a lab WAN built on FRRouting (BGP).

Intended design (source of truth):
{INTENT}

Method:
1. Decide whether the problem is control plane (BGP sessions, routes) or data plane (loss, latency).
2. Start with 'show bgp summary' on the affected router and compare it with the intended design.
3. Gather evidence with tools before concluding. Call one tool at a time.
4. Finish with: root cause, the evidence you observed, and the exact fix commands.

Rules:
- Only use router and host names that appear in the tool descriptions.
- Never claim something you did not observe with a tool.
- You are read-only. Propose changes; do not claim to have applied them.
- If a tool returns an error, say so and try another approach.
"""

# Ollama uses the OpenAI-style function schema.
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "show",
            "description": "Run a read-only FRR 'show' command on a lab router, e.g. 'show bgp summary'. "
                           f"Valid nodes: {lab_cli.ROUTERS}",
            "parameters": {
                "type": "object",
                "properties": {
                    "node": {"type": "string", "enum": lab_cli.ROUTERS},
                    "command": {"type": "string", "description": "A plain 'show ...' command"},
                },
                "required": ["node", "command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ping",
            "description": "Ping an IPv4 address from a site host to test end-to-end reachability. "
                           f"Valid hosts: {lab_cli.HOSTS}",
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {"type": "string", "enum": lab_cli.HOSTS},
                    "target": {"type": "string", "description": "IPv4 address, e.g. 10.4.0.10"},
                },
                "required": ["host", "target"],
            },
        },
    },
]

DISPATCH = {
    "show": lambda a: lab_cli.show(a["node"], a["command"]),
    "ping": lambda a: lab_cli.ping(a["host"], a["target"]),
}


# ---------------------------------------------------------------------------
# Provider-specific layer: the only function that knows about Ollama.
# ---------------------------------------------------------------------------
def call_model(messages: list):
    """Return (text, tool_calls) where tool_calls is a list of (name, args_dict)."""
    r = client.chat(model=MODEL, messages=messages, tools=TOOLS)
    msg = r.message
    calls = []
    for tc in msg.tool_calls or []:
        args = tc.function.arguments
        if isinstance(args, str):              # some models return JSON text
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        calls.append((tc.function.name, args))
    return msg, (msg.content or ""), calls


def audit(entry: dict) -> None:
    entry["time"] = datetime.datetime.now().isoformat(timespec="seconds")
    with open(AUDIT_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def run_tool(name: str, args: dict) -> str:
    """Execute one tool call safely and log it."""
    try:
        out = DISPATCH[name](args)
    except KeyError as e:
        out = f"ERROR: unknown tool or missing argument: {e}"
    except Exception as e:                      # never let a tool crash the agent
        out = f"ERROR: {e}"
    if len(out) > MAX_OUTPUT:
        out = out[:MAX_OUTPUT] + "\n...[output truncated]"
    audit({"tool": name, "args": args, "output": out})
    return out


def chat(messages: list) -> str:
    """One user question: loop until the model stops asking for tools."""
    for _ in range(MAX_STEPS):
        try:
            msg, text, calls = call_model(messages)
        except ollama.ResponseError as e:      # not signed in, rate limit, quota, model not found
            return f"Ollama error {e.status_code}: {e.error}"
        except Exception as e:                 # daemon not running, network down
            return f"Could not reach the model: {e}"
        messages.append(msg)

        if not calls:
            return text

        for name, args in calls:
            print(f"  [tool] {name} {args}")
            messages.append({"role": "tool", "tool_name": name, "content": run_tool(name, args)})

    return "Stopped: reached the step limit without a conclusion."


if __name__ == "__main__":
    messages = [{"role": "system", "content": SYSTEM}]
    print(f"wanlab agent ready (model: {MODEL}). Type 'quit' to exit.")
    while True:
        q = input("\nyou> ").strip()
        if q.lower() in ("quit", "exit"):
            break
        if not q:
            continue
        messages.append({"role": "user", "content": q})
        print("\n" + chat(messages))
