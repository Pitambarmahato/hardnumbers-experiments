# Builder image: runs build_agent_workflow.py against the sibling n8n
# container over the mounted Docker socket (docker-out-of-docker). Needs the
# docker CLI, not a full daemon -- it shells out `docker cp`/`docker exec`
# against the n8n container the same way the tutorial's manual commands do.
#
# Debian's own `docker.io` apt package stopped shipping the CLI client
# binary (just dockerd/docker-proxy) as of Debian trixie, so the client
# comes from Docker's official CLI-only image instead.
FROM docker:cli AS docker-cli

FROM python:3.12-slim
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /app
COPY build_agent_workflow.py .

ENTRYPOINT ["python3", "build_agent_workflow.py"]
CMD ["--container", "n8n-agent-test", "--run"]
