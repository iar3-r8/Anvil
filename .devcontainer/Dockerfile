FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg git sudo && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# Configure git to push over HTTPS using $GITHUB_TOKEN from remoteEnv.
# .ssh is not mounted (no key material), so SSH remotes cannot work.
# The credential helper reads the token at use time -- never written to disk.
# Both insteadOf forms must be set because the second replaces the first.
# If you edit this block, edit the identical block in templates/devcontainer/Dockerfile.
# See plans/devcontainer-git-push.md.
RUN git config --system credential.helper \
        '!f() { test "$1" = get && printf "username=x-access-token\npassword=%s\n" "$GITHUB_TOKEN"; }; f' && \
    git config --system --add url."https://github.com/".insteadOf "git@github.com:" && \
    git config --system --add url."https://github.com/".insteadOf "ssh://git@github.com/"

RUN pip install --no-cache-dir uv==0.8.5

RUN groupadd -g 1000 vscode && \
    useradd -u 1000 -g 1000 -m vscode -s /bin/bash && \
    echo "vscode ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/vscode && \
    chmod 0440 /etc/sudoers.d/vscode && \
    mkdir -p /home/vscode/.vscode-server/bin \
             /home/vscode/.vscode-server/data \
             /home/vscode/.vscode-server/extensions \
             /home/vscode/.npm \
             /home/vscode/.cache/uv && \
    chown -R vscode:vscode /home/vscode

USER vscode
WORKDIR /workspaces/anvil
