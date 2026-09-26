# n8n AI Agent workflow demo

Companion code for two Hard Numbers articles:

- **Tutorial:** [Build an AI Agent Workflow in n8n With Ollama](https://hardnumbers.dev/articles/build-ai-agent-workflow-n8n-ollama)
- **Experience report:** [I Built an AI Agent Workflow in n8n: What Happened](https://hardnumbers.dev/articles/n8n-ai-agent-workflow-experience)

`build_agent_workflow.py` builds and (optionally) runs n8n's native
**AI Agent** node (`@n8n/n8n-nodes-langchain.agent`), wired to a local Ollama
model and n8n's built-in Calculator tool, against a running n8n container.
It replaces the manual `docker cp` / `n8n import:*` / `n8n execute` sequence
in the tutorial with one command.

## Quick start (docker compose)

```bash
docker compose up --build
```

That's it — no manual `docker run`, no owner setup, no separate script
invocation. `docker compose up` starts n8n, waits for its healthcheck, then
runs the builder against it and prints the result:

```
builder-1  | Successfully imported 1 credential.
builder-1  | Importing 1 workflows...
builder-1  | Successfully imported 1 workflow.
builder-1  |
builder-1  | == executing (model=qwen2.5:14b) ==
builder-1  |
builder-1  | LLM calls: 2  Calculator calls: 1
builder-1  | Output: {"output": "47.51"}
```

n8n itself keeps running afterward at `http://127.0.0.1:5678` (open it and
complete the one-time owner setup if you want to click around the canvas —
that step is only needed for the browser UI, not for this CLI-driven
build). Reproduce the tutorial's failing case with a different model:

```bash
MODEL=qwen2.5:7b docker compose up --build
```

```
builder-1  | == executing (model=qwen2.5:7b) ==
builder-1  |
builder-1  | LLM calls: 10  Calculator calls: 10
builder-1  | Output: {"output": "Agent stopped due to max iterations."}
```

`docker compose down -v` tears everything down, including n8n's data volume.

### How the builder talks to n8n

`builder`'s Dockerfile has no daemon of its own — it mounts the host's
Docker socket (`/var/run/docker.sock`) and shells out `docker cp` /
`docker exec` against the `n8n` service's container, the same commands the
manual walkthrough below uses. The CLI binary comes from Docker's official
`docker:cli` image via a multi-stage build; Debian's own `docker.io` apt
package stopped shipping the client binary as of Debian trixie, only the
daemon (`dockerd`) — a real gotcha hit while building this image, not a
hypothetical one.

## Manual / standalone use

Prefer running the script yourself against an n8n you already have
(no compose, no Docker socket mount):

```bash
# n8n already running, e.g.:
docker run -d --name n8n-agent-test -p 5678:5678 \
  -e N8N_SECURE_COOKIE=false -e N8N_RUNNERS_ENABLED=true \
  -v n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n:latest

python3 build_agent_workflow.py --run
python3 build_agent_workflow.py --model qwen2.5:7b --run   # the failing case
```

## What it does

1. Writes an Ollama credential JSON and the workflow JSON (trigger -> `Set`
   node -> **AI Agent**, with an **Ollama Chat Model** node on the agent's
   `ai_languageModel` input and a **Calculator** tool node on its `ai_tool`
   input) to temp files.
2. `docker cp`'s each into the container and runs
   `n8n import:credentials` / `n8n import:workflow`.
3. With `--run`: executes the workflow via
   `n8n execute --id=<id> --rawOutput` (with `N8N_RUNNERS_BROKER_PORT` set
   to avoid the port-5679 collision the tutorial covers), then parses out
   the LLM/Calculator call counts and the final output.

Re-running with a different `--model` overwrites the workflow in place
(n8n's importer upserts by id) — that's how the tutorial's before/after
comparison was produced.

## Flags

| Flag | Default | Notes |
|---|---|---|
| `--container` | `n8n-agent-test` | name of the running n8n container |
| `--model` | `qwen2.5:14b` | any Ollama model tag |
| `--ollama-url` | `http://host.docker.internal:11434` | from the container's point of view |
| `--message` | (the refund example from the article) | prompt sent to the agent |
| `--workflow-id` / `--credential-id` | fixed defaults | change to run side by side with another instance |
| `--project-id` | none | only needed on a multi-project n8n instance |
| `--broker-port` | `5680` | port for the throwaway `execute` process |
| `--run` | off | execute immediately and print the result |

## Limitations

Same as the article's: this exercises one tool (Calculator) and one prompt
(a fixed arithmetic question). It is not a general n8n-workflow builder —
see `workflow_json()` in the script if you want to swap in a different
tool or prompt shape.
