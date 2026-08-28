#!/usr/bin/env bash

# ====================================================================
# Antigravity Hub Bridge - Service Control Utility
# ====================================================================

SERVICE_NAME="antigravity-hub.service"

case "$1" in
    start)
        echo "▶️ Starting ${SERVICE_NAME}..."
        systemctl --user start "${SERVICE_NAME}"
        systemctl --user status "${SERVICE_NAME}" --no-pager
        ;;
    stop)
        echo "⏹️ Stopping ${SERVICE_NAME}..."
        systemctl --user stop "${SERVICE_NAME}"
        ;;
    restart)
        echo "🔄 Restarting ${SERVICE_NAME}..."
        systemctl --user restart "${SERVICE_NAME}"
        systemctl --user status "${SERVICE_NAME}" --no-pager
        ;;
    status)
        systemctl --user status "${SERVICE_NAME}" --no-pager
        ;;
    logs)
        echo "📜 Showing live logs for ${SERVICE_NAME} (Ctrl+C to exit)..."
        journalctl --user -u "${SERVICE_NAME}" -f -n 50
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac
