FROM python:3.12-slim
RUN pip install --no-cache-dir pytest mypy
WORKDIR /workspace
ENTRYPOINT ["bash", "check.sh"]
