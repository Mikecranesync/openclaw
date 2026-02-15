#!/bin/bash
set -euo pipefail

INSTALL_DIR="/opt/openclaw"
PYTHON="python3.11"

echo "=== OpenClaw 1.0 Installer ==="
echo ""

# Create user
sudo useradd -r -s /bin/false openclaw 2>/dev/null || true

# Clone
sudo mkdir -p "$INSTALL_DIR"
sudo chown "$(whoami)" "$INSTALL_DIR"
cd "$INSTALL_DIR"

if [ -d .git ]; then
    git pull
else
    git clone https://github.com/Mikecranesync/openclaw.git .
fi

# Venv + install
$PYTHON -m venv .venv
.venv/bin/pip install -e .

# Config
if [ ! -f openclaw.yaml ]; then
    cp openclaw.yaml.example openclaw.yaml
    echo ">>> Edit $INSTALL_DIR/openclaw.yaml with your settings"
fi

# Systemd
sudo cp deploy/openclaw.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable openclaw

echo ""
echo "=== Done! ==="
echo "1. Edit $INSTALL_DIR/openclaw.yaml"
echo "2. Set env vars: GROQ_API_KEY, TELEGRAM_BOT_TOKEN, etc."
echo "3. sudo systemctl start openclaw"
echo "4. Check: curl http://localhost:8340/health"
