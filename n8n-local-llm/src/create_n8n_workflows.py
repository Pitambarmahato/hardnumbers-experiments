#!/usr/bin/env python3
"""
Create 5 n8n workflows via API for the local-LLM benchmark.

v2: each workflow = Webhook -> Function (build Ollama body) -> HTTP Request (call Ollama) -> Respond
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import requests

N8N = "http://127.0.0.1:5678"
COOKIE_JAR = "/tmp/n8n-cookies.txt"
DATA = Path(__file__).resolve().parent.parent / "data" / "test_workflows.json"


def build_workflow(workflow_name: str, system_prompt: str) -> dict:
    """Webhook -> Function (build body) -> HTTP -> Respond."""
    webhook_id = uuid.uuid4().hex[:8]
    return {
        "name": f"[bench] {workflow_name}",
        "nodes": [
            {
                "parameters": {
                    "httpMethod": "POST",
                    "path": f"bench-{workflow_name}",
                    "responseMode": "responseNode",
                    "options": {},
                },
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 1,
                "position": [240, 300],
                "webhookId": webhook_id,
                "id": uuid.uuid4().hex,
                "name": "Webhook",
            },
            {
                "parameters": {
                    "functionCode": (
                        "const body = items[0].json.body || {};\n"
                        "const sysPrompt = " + json.dumps(system_prompt) + ";\n"
                        "return [{\n"
                        "  json: {\n"
                        "    ollama_body: {\n"
                        "      model: body.model || 'qwen2.5:0.5b',\n"
                        "      messages: [\n"
                        "        { role: 'system', content: sysPrompt },\n"
                        "        { role: 'user', content: body.user || '' }\n"
                        "      ],\n"
                        "      stream: false,\n"
                        "      options: { temperature: 0, num_predict: 512 }\n"
                        "    }\n"
                        "  }\n"
                        "}];\n"
                    ),
                },
                "type": "n8n-nodes-base.function",
                "typeVersion": 1,
                "position": [460, 300],
                "id": uuid.uuid4().hex,
                "name": "Build body",
            },
            {
                "parameters": {
                    "method": "POST",
                    "url": "http://host.docker.internal:11434/api/chat",
                    "sendHeaders": True,
                    "headerParameters": {
                        "parameters": [
                            {"name": "Content-Type", "value": "application/json"}
                        ]
                    },
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": "={{ JSON.stringify($json.ollama_body) }}",
                    "options": {"timeout": 180000},
                },
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.1,
                "position": [680, 300],
                "id": uuid.uuid4().hex,
                "name": "Call Ollama",
            },
            {
                "parameters": {
                    "respondWith": "json",
                    "responseBody": (
                        "={{ JSON.stringify({ response: $json.message?.content || '', model: $json.model || '', wall_s: 0 }) }}"
                    ),
                    "options": {"responseCode": 200},
                },
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1,
                "position": [900, 300],
                "id": uuid.uuid4().hex,
                "name": "Respond",
            },
        ],
        "connections": {
            "Webhook": {"main": [[{"node": "Build body", "type": "main", "index": 0}]]},
            "Build body": {"main": [[{"node": "Call Ollama", "type": "main", "index": 0}]]},
            "Call Ollama": {"main": [[{"node": "Respond", "type": "main", "index": 0}]]},
        },
        "settings": {"executionOrder": "v1"},
    }


def main() -> int:
    data = json.loads(DATA.read_text())
    workflows = data["workflows"]

    sess = requests.Session()
    jar = {}
    for line in Path(COOKIE_JAR).read_text().splitlines():
        if not line or (line.startswith("#") and not line.startswith("#HttpOnly_")):
            continue
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
        parts = line.split("\t")
        if len(parts) != 7:
            continue
        jar[parts[5]] = parts[6]
    sess.cookies = requests.utils.cookiejar_from_dict(jar)

    # First: archive the old ones (idempotent: list + archive all "[bench] " workflows)
    r = sess.get(f"{N8N}/api/v1/workflows", params={"limit": 200})
    if r.status_code == 200:
        for wf in r.json().get("data", []):
            if (wf.get("name") or "").startswith("[bench] "):
                sess.delete(f"{N8N}/api/v1/workflows/{wf['id']}")
                print(f"deleted {wf['name']} (id={wf['id']})")

    out = {}
    for wf_name, wf in workflows.items():
        body = build_workflow(wf_name, wf["system_prompt"])
        r = sess.post(f"{N8N}/api/v1/workflows", json=body)
        if r.status_code not in (200, 201):
            print(f"FAIL {wf_name}: HTTP {r.status_code} {r.text[:300]}")
            return 1
        j = r.json()
        wid = j["id"]
        webhook_url = f"{N8N}/webhook/bench-{wf_name}"
        # activate
        r2 = sess.post(f"{N8N}/api/v1/workflows/{wid}/activate")
        if r2.status_code != 200:
            print(f"FAIL activate {wf_name}: HTTP {r2.status_code} {r2.text[:300]}")
        out[wf_name] = {"id": wid, "webhook_url": webhook_url}
        print(f"OK   {wf_name:20} id={wid}  active={r2.status_code == 200}")

    Path("n8n_workflow_urls.json").write_text(json.dumps(out, indent=2))
    print(f"\nWrote n8n_workflow_urls.json with {len(out)} workflows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
