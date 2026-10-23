"""
VTP Fleet Tracking - Desktop Launcher for Windows & Linux
Starts the local server on 127.0.0.1:8000 and opens the browser automatically.
"""

import os
import sys
import time
import socket
import webbrowser
import threading
from pathlib import Path

# Ensure root directory is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import uvicorn


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def open_browser(url: str, delay: float = 1.5):
    time.sleep(delay)
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"Could not open browser automatically: {e}")


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    url = f"http://{host}:{port}"

    print("=" * 65)
    print("  VIETTEL POST - VTP FLEET TRACKING SYSTEM")
    print("  Unified Fleet Telemetry & Management Dashboard")
    print(f"  Server URL : {url}")
    print(f"  Security   : Strictly bound to {host} (Corporate LAN Safe)")
    print("=" * 65)

    # Launch browser after short delay
    threading.Thread(target=open_browser, args=(url, 1.8), daemon=True).start()

    # Start Uvicorn
    try:
        from app.main import app
        uvicorn.run(app, host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        print("\n[VTP Fleet] Shutting down gracefully...")


if __name__ == "__main__":
    main()
