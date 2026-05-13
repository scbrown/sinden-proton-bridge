#!/bin/bash
# Install both Sinden systemd units (system-level daemon + user-level bridge).
# Idempotent — safe to re-run.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Installing sinden-mono.service (system-level, runs as root)"
sudo cp "$SCRIPT_DIR/sinden-mono.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sinden-mono.service
echo "    Installed. Start with:  sudo systemctl start sinden-mono.service"

echo
echo "==> Installing sinden-bridge.service (user-level, runs as $USER)"
mkdir -p "$HOME/.config/systemd/user"
cp "$SCRIPT_DIR/sinden-bridge.service" "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable sinden-bridge.service
echo "    Installed. Start with:  systemctl --user start sinden-bridge.service"

echo
echo "==> All set. Both services will autostart on boot/login."
echo "    Check status anytime with:"
echo "      systemctl status sinden-mono.service"
echo "      systemctl --user status sinden-bridge.service"
echo "    Follow logs with:"
echo "      journalctl -u sinden-mono.service -f"
echo "      journalctl --user -u sinden-bridge.service -f"
