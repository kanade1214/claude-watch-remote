#!/usr/bin/env bash
# Sets up an Ubuntu machine as the PC relay server + Claude Code host
# (spec section 2.1's "PC" role, running natively instead of under WSL2).
#
# Usage: run this ON the Ubuntu machine, from the root of this repo:
#   bash scripts/setup_ubuntu_host.sh
#
# What it does:
#   - installs tmux, Python 3 + venv, Node.js LTS, and the Claude Code CLI
#   - creates the Python virtualenv and installs requirements.txt
#   - opens the relay server's port in ufw (if ufw is active)
#   - prints the remaining manual steps (Claude Code login, tmux session)
set -euo pipefail

RELAY_PORT="${CLAUDE_WATCH_PORT:-8000}"
TMUX_SESSION="${CLAUDE_WATCH_TMUX_SESSION:-claude-remote}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Installing system packages (tmux, python3-venv, curl, git)"
sudo apt-get update
sudo apt-get install -y tmux python3-venv python3-pip curl git

if ! command -v node >/dev/null 2>&1; then
  echo "==> Installing Node.js LTS (needed for the Claude Code CLI)"
  curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
  sudo apt-get install -y nodejs
else
  echo "==> Node.js already installed: $(node --version)"
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "==> Installing the Claude Code CLI"
  sudo npm install -g @anthropic-ai/claude-code
else
  echo "==> Claude Code CLI already installed: $(claude --version || true)"
fi

echo "==> Setting up the Python virtualenv for the relay server"
cd "$REPO_ROOT"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
./.venv/bin/pip install -r requirements.txt

if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q "Status: active"; then
  echo "==> Opening port $RELAY_PORT in ufw"
  sudo ufw allow "$RELAY_PORT"/tcp
fi

cat <<EOF

==> System setup complete. Remaining manual steps:

1. Log in to Claude Code (one-time, interactive):
     claude login

2. Create the tmux session the relay server sends input into, and start
   Claude Code inside it (session name must match CLAUDE_WATCH_TMUX_SESSION,
   currently "$TMUX_SESSION"):
     tmux new -s $TMUX_SESSION
     claude
   (detach with Ctrl-b then d; the session must keep running in the background)

3. Start the relay server (from $REPO_ROOT):
     ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $RELAY_PORT

4. From your phone (same LAN, or Tailscale), pair against:
     http://<this-machine's-LAN-IP>:$RELAY_PORT

Find this machine's LAN IP with: ip -4 addr show scope global | grep inet
EOF
