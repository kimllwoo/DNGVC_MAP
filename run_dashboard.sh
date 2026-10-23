#!/usr/bin/env bash
# ==============================================================================
# VTP FLEET TRACKING STARTUP SCRIPT
# CORPORATE LAN SECURITY POLICY: Strictly binds to 127.0.0.1 (localhost)
# NEVER bind to 0.0.0.0 or LAN interface (enp2s0)
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

echo "=================================================================="
echo " Starting VTP Fleet Tracking Dashboard..."
echo " Host: ${HOST} (Loopback / Localhost only)"
echo " Port: ${PORT}"
echo " Dashboard URL: http://${HOST}:${PORT}"
echo "=================================================================="

# Check Python environment
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 is required."
    exit 1
fi

# Automatically release port if an older instance is still running
OLD_PID=$(lsof -t -i :"${PORT}" 2>/dev/null || true)
if [ -n "${OLD_PID}" ]; then
    echo "Detected existing process on port ${PORT} (PID: ${OLD_PID}). Releasing port..."
    kill -15 ${OLD_PID} 2>/dev/null || true
    sleep 1
    for pid in ${OLD_PID}; do
        if kill -0 "${pid}" 2>/dev/null; then
            kill -9 "${pid}" 2>/dev/null || true
        fi
    done
    echo "Port ${PORT} cleared successfully."
fi

# Run Uvicorn server bound strictly to localhost
exec python3 -m uvicorn app.main:app --host "${HOST}" --port "${PORT}" --log-level info
