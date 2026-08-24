#!/usr/bin/env bash
set -e

# ====================================================================
# Antigravity Telegram Bridge - Systemd User Daemon Installer
# ====================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICE_NAME="antigravity-telegram.service"
USER_SYSTEMD_DIR="${HOME}/.config/systemd/user"

echo "======================================================"
echo "🚀 Installing Antigravity Telegram Bridge Daemon..."
echo "📁 Project Directory: ${PROJECT_DIR}"
echo "======================================================"

# 1. Check Python 3
if ! command -v python3 &>/dev/null; then
    echo "❌ Python 3 is not installed! Please install Python 3."
    exit 1
fi

# 2. Setup Virtual Environment
VENV_DIR="${PROJECT_DIR}/venv"
if [ ! -d "${VENV_DIR}" ]; then
    echo "📦 Creating virtual environment at ${VENV_DIR}..."
    python3 -m venv "${VENV_DIR}"
fi

echo "📦 Installing / updating Python dependencies..."
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${PROJECT_DIR}/requirements.txt"

# 3. Check / Initialize .env
if [ ! -f "${PROJECT_DIR}/.env" ]; then
    echo "⚠️  .env file not found. Creating from .env.example..."
    cp "${PROJECT_DIR}/.env.example" "${PROJECT_DIR}/.env"
    echo "📝 Please edit ${PROJECT_DIR}/.env and set your TELEGRAM_BOT_TOKEN!"
fi

# 4. Prepare Systemd User Directory
mkdir -p "${USER_SYSTEMD_DIR}"

# 5. Install Service Unit
echo "⚙️ Installing systemd user unit: ${SERVICE_NAME}..."
cp "${SCRIPT_DIR}/${SERVICE_NAME}" "${USER_SYSTEMD_DIR}/${SERVICE_NAME}"

# 6. Enable User Lingering (keeps daemon running after SSH logout)
if command -v loginctl &>/dev/null; then
    echo "🔒 Enabling user linger for ${USER}..."
    loginctl enable-linger "${USER}" || true
fi

# 7. Reload systemd user daemon and restart service
echo "🔄 Reloading systemd user daemon..."
systemctl --user daemon-reload
echo "▶️ Enabling and starting ${SERVICE_NAME}..."
systemctl --user enable --now "${SERVICE_NAME}"

echo ""
echo "======================================================"
echo "✅ Antigravity Telegram Bridge successfully installed!"
echo "======================================================"
echo "Status check:"
systemctl --user status "${SERVICE_NAME}" --no-pager || true
echo ""
echo "Helpful commands:"
echo "• View status: ${PROJECT_DIR}/systemd/service.sh status"
echo "• View live logs: ${PROJECT_DIR}/systemd/service.sh logs"
echo "• Restart service: ${PROJECT_DIR}/systemd/service.sh restart"
echo "• Stop service: ${PROJECT_DIR}/systemd/service.sh stop"
echo "======================================================"
