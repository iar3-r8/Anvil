FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg git && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] \
        https://deb.nodesource.com/node_22.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv==0.8.5

RUN groupadd -g 1000 vscode && \
    useradd -u 1000 -g 1000 -m vscode -s /bin/bash && \
    echo "vscode ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers && \
    # Pre-create .vscode-server with correct ownership so VS Code server can write
    mkdir -p /home/vscode/.vscode-server/{bin,data,extensions} && \
    chown -R vscode:vscode /home/vscode/.vscode-server && \
    chown -R vscode:vscode /home/vscode

ENV PATH="/usr/local/bin:/usr/bin:/root/.local/bin:${PATH}"

USER vscode
WORKDIR /workspaces/anvil
