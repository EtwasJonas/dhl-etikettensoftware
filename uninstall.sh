#!/usr/bin/env bash
# uninstall.sh – entfernt die DHL-Etikettensoftware vom Ziel-PC
set -euo pipefail

APP_DIR="$HOME/.local/share/dhl-label"
BIN_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/dhl-label"
SYSTEMD_DIR="$HOME/.config/systemd/user"
DESKTOP_DIR="$HOME/.local/share/applications"

systemctl --user disable --now dhl-label.service 2>/dev/null || true
rm -f "$SYSTEMD_DIR/dhl-label.service"
systemctl --user daemon-reload 2>/dev/null || true

rm -rf "$APP_DIR" "$CONFIG_DIR"
rm -f "$BIN_DIR/dhl-label" "$DESKTOP_DIR/dhl-label-print.desktop"

echo "DHL-Etikettensoftware entfernt."
