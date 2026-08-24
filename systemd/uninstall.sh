#!/usr/bin/env bash
set -e

# ====================================================================
# Antigravity Telegram Bridge - Systemd User Daemon Uninstaller
# ====================================================================

SERVICE_NAME="antigravity-telegram.service"
USER_SYSTEMD_DIR="${HOME}/.config/systemd/user"

echo "======================================================"
echo "🛑 Uninstalling Antigravity Telegram Bridge Daemon..."
echo "======================================================"

if systemctl --user is-active --quiet "${SERVICE_NAME}" 2>/dev/null; then
    echo "⏹️ Stopping ${SERVICE_NAME}..."
    systemctl --user stop "${SERVICE_NAME}" || true
fi

if systemctl --user is-enabled --quiet "${SERVICE_NAME}" 2>/dev/null; then
    echo "🔒 Disabling ${SERVICE_NAME}..."
    systemctl --user disable "${SERVICE_NAME}" || true
fi

if [ -f "${USER_SYSTEMD_DIR}/${SERVICE_NAME}" ]; then
    echo "🗑 Removing service unit file..."
    rm -f "${USER_SYSTEMD_DIR}/${SERVICE_NAME}"
fi

echo "🔄 Reloading systemd user daemon..."
systemctl --user daemon-reload
systemctl --user reset-failed 2>/dev/null || true

echo "✅ Antigravity Telegram Bridge Daemon successfully uninstalled."
