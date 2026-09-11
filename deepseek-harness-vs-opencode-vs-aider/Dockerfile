# Shared image for the DeepSeek Harness vs OpenCode vs Aider comparison.
# All three CLIs point at the host's Ollama server (host.docker.internal)
# running qwen3-14b-ctx16k — the model never changes, only the harness does.
FROM node:22-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv pipx git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV DSH_HOME=/root/.dsh \
    OLLAMA_API_BASE=http://ollama-proxy:11434 \
    OLLAMA_API_KEY=ollama \
    PATH="/root/.local/bin:${PATH}"

# --- Aider ---
RUN pipx install aider-chat

# --- OpenCode ---
RUN npm install -g opencode-ai@1.18.30
COPY configs/opencode.json /root/.config/opencode/opencode.json

# --- DeepSeek Harness (dsh) ---
RUN npm install -g @deepseek-ai/dsh@0.1.2-rc.1
# Pre-warm the headless profile's own plugin install (pnpm) at build time,
# not at container start, so the benchmark doesn't pay npm-registry latency
# per run.
RUN dsh --profile headless --dump-config >/dev/null 2>&1 || true
COPY configs/cordis.patch.yml /root/.dsh/profiles/headless/cordis.patch.yml

WORKDIR /workspace
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
