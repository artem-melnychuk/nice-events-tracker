#!/bin/bash
# Smoke test of the sandbox image: who am I, does the project work, and what can this container reach?
echo "--- identity"
echo "user=$(whoami) uid=$(id -u) home=$HOME"
echo "python=$(python --version 2>&1)"
echo "claude=$(claude --version 2>&1 | head -1)"
echo "git identity=$(git config --global user.name) <$(git config --global user.email)>"
echo "--- unit tests"
python -m unittest discover -s tests 2>&1 | tail -3
echo "--- can this container push to GitHub? (the dry run must FAIL)"
GIT_TERMINAL_PROMPT=0 timeout 30 git push --dry-run https://github.com/artem-melnychuk/nice-events-tracker.git agent 2>&1 | tail -2
echo "--- host credentials visible? (all of these should be empty or missing)"
ls -A ~/.ssh 2>&1 | head -2
git config --global --get-regexp 'credential' 2>&1 | head -2
env | grep -iE 'token|secret|api_key|password' | head -3
ls /var/run/docker.sock 2>&1 | head -1
echo "--- filesystem: only /work should be host-backed"
mount | grep -E ' /work | /mnt/|host_mnt' | head -3
touch /work/.write_test && rm /work/.write_test && echo "write to /work: ok"
echo "--- network"
curl -sI --max-time 15 https://api.anthropic.com 2>&1 | head -1
echo "--- capabilities (CapEff should be 0000000000000000)"
grep CapEff /proc/self/status
