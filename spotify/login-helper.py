#!/usr/bin/env python3
"""Expose the Spotify client's login state over HTTP, so no VNC is needed.

While logged out, the client shows a "scan to log in" QR code that encodes a
https://spotify.com/pair?code=... link. Every INTERVAL seconds this takes a
screenshot of the virtual display, decodes any QR code and serves:

  GET /status  -> {"logged_in": bool, "login_url": str|null, "code": str|null,
                   "client_running": bool, "checked_at": iso8601}
  GET /qr.png  -> the login QR code (re-rendered, crisp), 404 when logged in

While the client is stopped (no speaker connected, see entrypoint.sh) it counts
as logged in if it has a saved login. While the QR code shows it writes
NEEDS_LOGIN, which keeps the client running until someone logs in.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("LOGIN_PORT", "8091"))
INTERVAL = float(os.environ.get("LOGIN_CHECK_INTERVAL", "10"))
DISPLAY = os.environ["DISPLAY"]
PREFS = os.path.expanduser("~/.config/spotify/prefs")
NEEDS_LOGIN = "/tmp/boombox-needs-login"
PAIR_RE = re.compile(r"^https://(?:www\.)?spotify\.com/pair\?code=([A-Z0-9]+)")

state: dict = {
    "logged_in": False,
    "login_url": None,
    "code": None,
    "client_running": False,
    "checked_at": None,
}
qr_png: bytes | None = None
lock = threading.Lock()


def run(cmd: list[str], data: bytes | None = None) -> bytes:
    return subprocess.run(
        cmd, input=data, capture_output=True, timeout=30, check=False
    ).stdout


def client_running() -> bool:
    return bool(run(["pgrep", "-f", "/usr/share/spotify/spotify"]).strip())


def saved_login() -> bool:
    try:
        with open(PREFS, encoding="utf-8", errors="replace") as f:
            return any(line.startswith("autologin.username=") for line in f)
    except OSError:
        return False


def check() -> None:
    global qr_png
    running = client_running()
    url = None
    if running:
        shot = run(["import", "-display", DISPLAY, "-window", "root", "png:-"])
        if shot:
            for line in run(["zbarimg", "-q", "--raw", "-"], shot).decode().splitlines():
                if PAIR_RE.match(line.strip()):
                    url = line.strip()
                    break
    png = run(["qrencode", "-o", "-", "-s", "10", "-m", "2", url]) if url else None
    # Logged in = the client runs and shows no login QR code, or it's stopped
    # (waiting for a speaker) with a saved login.
    logged_in = (url is None) if running else saved_login()
    if url:
        open(NEEDS_LOGIN, "w").close()
    elif running and os.path.exists(NEEDS_LOGIN):
        os.remove(NEEDS_LOGIN)
    with lock:
        state.update(
            logged_in=logged_in,
            login_url=url,
            code=PAIR_RE.match(url).group(1) if url else None,
            client_running=running,
            checked_at=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        )
        qr_png = png


def loop() -> None:
    while True:
        try:
            check()
        except Exception as err:  # noqa: BLE001 - keep serving whatever happens
            print(f"login-helper: check failed: {err}", flush=True)
        time.sleep(INTERVAL)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        with lock:
            if path == "/status":
                body, ctype, code = json.dumps(state).encode(), "application/json", 200
            elif path == "/qr.png" and qr_png:
                body, ctype, code = qr_png, "image/png", 200
            else:
                body, ctype, code = b"not found\n", "text/plain", 404
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


if __name__ == "__main__":
    threading.Thread(target=loop, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
