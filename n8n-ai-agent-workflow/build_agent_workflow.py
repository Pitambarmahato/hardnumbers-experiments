#!/usr/bin/env python3
"""Build and (optionally) run the n8n AI Agent demo workflow end to end.

Replaces the manual docker exec / n8n CLI dance from the tutorial
("Build an AI Agent Workflow in n8n With Ollama") with one script. It
creates the Ollama credential, builds the workflow (trigger -> Set ->
AI Agent, with an Ollama Chat Model and a Calculator tool attached to the
Agent's model/tool sockets), imports both into a running n8n container via
`docker cp` + `n8n import:*`, and can execute it immediately.

Prerequisites (see the tutorial for the full walkthrough and the gotchas):
  - An n8n container already running, e.g.:
      docker run -d --name n8n-agent-test -p 5678:5678 \\
        -e N8N_SECURE_COOKIE=false -e N8N_RUNNERS_ENABLED=true \\
        -v n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n:latest
  - Its one-time owner setup completed in the browser (http://127.0.0.1:5678)
  - Ollama running on the host with the target model pulled

Usage:
    python3 build_agent_workflow.py                        # build + import, don't run
    python3 build_agent_workflow.py --run                   # build, import, execute, print result
    python3 build_agent_workflow.py --model qwen2.5:7b --run   # reproduce the failing case
    python3 build_agent_workflow.py --message "..." --run   # custom prompt

Idempotent: re-running with the same --workflow-id / --credential-id
overwrites the existing workflow / credential in place (n8n's importer
upserts by id), so changing --model and re-running is the normal workflow.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_MESSAGE = (
    "A customer's order total was $128.40 and we're issuing a 37% refund "
    "for a damaged item. Tell me the exact refund amount in dollars."
)

SYSTEM_MESSAGE = (
    "You are a support-ops assistant. Use the calculator tool for any "
    "arithmetic instead of computing it yourself. Reply with the final "
    "dollar amount only, rounded to 2 decimals."
)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    print("$", " ".join(cmd))
    return subprocess.run(cmd, check=True, **kw)


def credential_json(credential_id: str, ollama_url: str) -> list[dict]:
    return [
        {
            "id": credential_id,
            "name": "Ollama local (host.docker.internal)",
            "type": "ollamaApi",
            "data": {"baseUrl": ollama_url},
        }
    ]


def workflow_json(workflow_id: str, credential_id: str, model: str, message: str) -> dict:
    return {
        "id": workflow_id,
        "name": "[demo] ai-agent-refund-calc",
        "nodes": [
            {
                "id": "trigger0",
                "name": "When called manually",
                "type": "n8n-nodes-base.executeWorkflowTrigger",
                "typeVersion": 1,
                "position": [240, 120],
                "parameters": {},
            },
            {
                "id": "trigger1",
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 1,
                "position": [240, 300],
                "webhookId": "demo-ai-agent-refund-calc",
                "parameters": {
                    "httpMethod": "POST",
                    "path": "demo-ai-agent-refund-calc",
                    "responseMode": "responseNode",
                    "options": {},
                },
            },
            {
                "id": "set1",
                "name": "Customer message",
                "type": "n8n-nodes-base.set",
                "typeVersion": 3.4,
                "position": [460, 300],
                "parameters": {
                    "assignments": {
                        "assignments": [
                            {
                                "id": "a1",
                                "name": "message",
                                "type": "string",
                                "value": (
                                    "={{ $json.chatInput || $json.body?.message || "
                                    + json.dumps(message)
                                    + " }}"
                                ),
                            }
                        ]
                    },
                    "options": {},
                },
            },
            {
                "id": "agent1",
                "name": "AI Agent",
                "type": "@n8n/n8n-nodes-langchain.agent",
                "typeVersion": 2,
                "position": [680, 300],
                "parameters": {
                    "promptType": "define",
                    "text": "={{ $json.message }}",
                    "options": {"systemMessage": SYSTEM_MESSAGE},
                },
            },
            {
                "id": "respond1",
                "name": "Respond",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1,
                "position": [900, 300],
                "parameters": {
                    "respondWith": "json",
                    "responseBody": (
                        "={{ JSON.stringify({ output: $json.output, "
                        "message: $('Customer message').item.json.message }) }}"
                    ),
                    "options": {},
                },
            },
            {
                "id": "llm1",
                "name": "Ollama Chat Model",
                "type": "@n8n/n8n-nodes-langchain.lmChatOllama",
                "typeVersion": 1,
                "position": [620, 520],
                "parameters": {"model": model, "options": {}},
                "credentials": {
                    "ollamaApi": {"id": credential_id, "name": "Ollama local (host.docker.internal)"}
                },
            },
            {
                "id": "tool1",
                "name": "Calculator",
                "type": "@n8n/n8n-nodes-langchain.toolCalculator",
                "typeVersion": 1,
                "position": [780, 520],
                "parameters": {},
            },
        ],
        "connections": {
            "When called manually": {"main": [[{"node": "Customer message", "type": "main", "index": 0}]]},
            "Webhook": {"main": [[{"node": "Customer message", "type": "main", "index": 0}]]},
            "Customer message": {"main": [[{"node": "AI Agent", "type": "main", "index": 0}]]},
            "AI Agent": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
            "Ollama Chat Model": {
                "ai_languageModel": [[{"node": "AI Agent", "type": "ai_languageModel", "index": 0}]]
            },
            "Calculator": {"ai_tool": [[{"node": "AI Agent", "type": "ai_tool", "index": 0}]]},
        },
        "settings": {},
    }


def docker_cp_and_run(container: str, local_path: Path, remote_path: str, *cli_args: str) -> None:
    run(["docker", "cp", str(local_path), f"{container}:{remote_path}"])
    run(["docker", "exec", container, "n8n", *cli_args])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--container", default="n8n-agent-test", help="running n8n container name")
    ap.add_argument("--model", default="qwen2.5:14b", help="Ollama model tag (e.g. qwen2.5:7b to reproduce the failure)")
    ap.add_argument("--ollama-url", default="http://host.docker.internal:11434")
    ap.add_argument("--message", default=DEFAULT_MESSAGE, help="prompt sent to the agent")
    ap.add_argument("--workflow-id", default="aiAgentDemo0001")
    ap.add_argument("--credential-id", default="SIzKYVklpuvzC4GN")
    ap.add_argument("--project-id", default=None, help="omit for a single-project instance; required if you have several")
    ap.add_argument("--broker-port", type=int, default=5680, help="port for the throwaway execute process (avoids the 5679 collision, see the tutorial)")
    ap.add_argument("--run", action="store_true", help="execute the workflow after importing it")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cred_path = tmp_path / "cred.json"
        wf_path = tmp_path / "workflow.json"
        cred_path.write_text(json.dumps(credential_json(args.credential_id, args.ollama_url), indent=2))
        wf_path.write_text(json.dumps(workflow_json(args.workflow_id, args.credential_id, args.model, args.message), indent=2))

        proj_flag = ["--projectId", args.project_id] if args.project_id else []

        print("\n== importing credential ==")
        docker_cp_and_run(args.container, cred_path, "/tmp/cred.json", "import:credentials", "--input=/tmp/cred.json", *proj_flag)

        print("\n== importing workflow ==")
        docker_cp_and_run(args.container, wf_path, "/tmp/workflow.json", "import:workflow", "--input=/tmp/workflow.json", *proj_flag)

    if not args.run:
        print(f"\nImported. Open http://127.0.0.1:5678, find '[demo] ai-agent-refund-calc', and click "
              f"'Test workflow' -- or re-run this script with --run.")
        return

    print(f"\n== executing (model={args.model}) ==")
    result = subprocess.run(
        [
            "docker", "exec", "-e", f"N8N_RUNNERS_BROKER_PORT={args.broker_port}",
            args.container, "n8n", "execute", f"--id={args.workflow_id}", "--rawOutput",
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        sys.exit(f"execution failed (exit {result.returncode})")

    try:
        # n8n writes log/status lines to stdout even with --rawOutput; the
        # pretty-printed JSON result is everything from the first line that
        # is exactly "{" to the end.
        lines = result.stdout.splitlines()
        start = next(i for i, l in enumerate(lines) if l.strip() == "{")
        data = json.loads("\n".join(lines[start:]))["data"]
        run_data = data["resultData"]["runData"]
        agent_out = run_data.get("AI Agent", [{}])[0].get("data", {}).get("main", [[{}]])[0][0].get("json", {})
        n_llm = len(run_data.get("Ollama Chat Model", []))
        n_calc = len(run_data.get("Calculator", []))
        print(f"\nLLM calls: {n_llm}  Calculator calls: {n_calc}")
        print(f"Output: {json.dumps(agent_out)}")
    except Exception:  # noqa: BLE001 - fall back to raw output if the shape ever changes
        print(result.stdout)


if __name__ == "__main__":
    main()
