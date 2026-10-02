# Sandbox for running Claude Code unattended on a clone of nice_events_tracker.
#
# What this container can reach: only the folder mounted at /work (the clone,
# not this repo), its own ~/.claude volume, and the network through the proxy
# in .sandbox/squid. It has no host credentials: no ssh agent, no git
# credential helper, no host gitconfig.
#
# Build (from the repo root, or use `.\sandbox.ps1 rebuild`):
#   docker build -f .sandbox/Dockerfile -t nice-events-agent .
# The build context is whitelisted in .dockerignore.

FROM python:3.14-bookworm

# Claude Code refuses --dangerously-skip-permissions as root, so run as a normal user.
RUN useradd --create-home --shell /bin/bash agent
USER agent
ENV HOME=/home/agent \
    PATH=/home/agent/.local/bin:$PATH \
    CLAUDE_CONFIG_DIR=/home/agent/.claude
WORKDIR /work

# Claude Code, official installer (installs to ~/.local/bin).
RUN curl -fsSL https://claude.ai/install.sh | bash

# Project dependencies. Playwright's browsers are not installed on purpose:
# the unit tests run offline and the agent should not scrape live sites.
COPY --chown=agent:agent requirements.txt /tmp/requirements.txt
RUN pip install --user --no-cache-dir -r /tmp/requirements.txt

# Commits made in here are attributed to the sandbox, not to the host user.
RUN git config --global user.name "sandbox-agent" \
 && git config --global user.email "sandbox-agent@localhost" \
 && git config --global --add safe.directory /work \
 && mkdir -p /home/agent/.claude

# The rules live outside the volume and are copied in at every start, so
# editing them never needs the volume to be recreated.
COPY .sandbox/agent-rules.md /opt/agent-rules.md
CMD ["bash", "-lc", "cp /opt/agent-rules.md \"$CLAUDE_CONFIG_DIR/CLAUDE.md\" && exec bash -l"]
