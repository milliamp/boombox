#!/usr/bin/env python3
"""Run PulseAudio and serve the speaker's volume over HTTP for Home Assistant.

The speaker is PulseAudio's Bluetooth sink. Its volume is the speaker's own
volume (A2DP absolute volume), so the speaker's buttons change it too.

  GET  /status  -> {"connected": bool, "sink": str|null, "volume": int|null,
                    "muted": bool|null, "playing": bool, "fading": bool}
  POST /volume  {"volume": 0-100}                 set it now (stops a fade)
  POST /fade    {"to": 0-100, "seconds": 10,      fade from "from" (default:
                 "from": 0-100, "wait": 20}       the current volume) to "to".
                With "wait", wait up to that many seconds for the speaker to
                connect (it may still be off) and a client to start playing,
                holding the volume at "from" meanwhile, so the fade starts with
                the music and the speaker's own restored volume never plays.

Listens on 127.0.0.1 only (the container uses host networking).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("VOLUME_PORT", "8090"))
BIND = os.environ.get("VOLUME_BIND", "127.0.0.1")
STEP = 0.1  # seconds between fade steps

fade_lock = threading.Lock()
fade_generation = 0  # bumped by every request; a running fade stops when it changes
fading = False


def pactl(*args: str) -> str:
    return subprocess.run(
        ["pactl", *args], capture_output=True, text=True, timeout=10, check=True
    ).stdout


def bluetooth_sink() -> dict | None:
    try:
        sinks = json.loads(pactl("-f", "json", "list", "sinks"))
    except (subprocess.SubprocessError, ValueError):
        return None
    for sink in sinks:
        if sink.get("name", "").startswith("bluez_sink."):
            return sink
    return None


def sink_volume(sink: dict) -> int:
    channels = sink.get("volume", {}).values()
    percents = [int(c["value_percent"].rstrip("%")) for c in channels]
    return round(sum(percents) / len(percents)) if percents else 0


def playing() -> bool:
    """Is any client stream on the speaker actually playing (not corked)?"""
    sink = bluetooth_sink()
    if not sink:
        return False
    try:
        inputs = json.loads(pactl("-f", "json", "list", "sink-inputs"))
    except (subprocess.SubprocessError, ValueError):
        return False
    return any(i.get("sink") == sink.get("index") and not i.get("corked") for i in inputs)


def set_volume(sink: str, volume: float) -> None:
    pactl("set-sink-volume", sink, f"{max(0, min(100, round(volume)))}%")


def status() -> dict:
    sink = bluetooth_sink()
    return {
        "connected": sink is not None,
        "sink": sink["name"] if sink else None,
        "volume": sink_volume(sink) if sink else None,
        "muted": sink.get("mute") if sink else None,
        "playing": playing(),
        "fading": fading,
    }


def new_generation() -> int:
    global fade_generation
    with fade_lock:
        fade_generation += 1
        return fade_generation


def fade(gen: int, start: float | None, to: float, seconds: float, wait: float) -> None:
    """Fade the speaker to `to`.

    With `wait`, first wait (up to `wait` seconds in all) for the speaker to
    connect and for a client to start playing, holding the volume at `start`
    meanwhile: the speaker restores its own last volume when it connects.
    """
    global fading
    fading = True
    try:
        deadline = time.monotonic() + wait
        sink = bluetooth_sink()
        while wait and time.monotonic() < deadline:
            if gen != fade_generation:
                return
            if sink:
                if start is not None and sink_volume(sink) != round(start):
                    set_volume(sink["name"], start)
                if playing():
                    break
            time.sleep(STEP)
            sink = bluetooth_sink()
        if not sink:
            return
        if start is not None:
            set_volume(sink["name"], start)
        begin = sink_volume(sink) if start is None else start
        steps = max(1, round(seconds / STEP))
        for n in range(1, steps + 1):
            if gen != fade_generation:
                return
            set_volume(sink["name"], begin + (to - begin) * n / steps)
            time.sleep(STEP)
    except subprocess.SubprocessError as err:
        print(f"volume-api: fade stopped: {err}", file=sys.stderr, flush=True)
    finally:
        if gen == fade_generation:
            fading = False


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split("?")[0] == "/status":
            self._send(200, status())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            path = self.path.split("?")[0]
            if path not in ("/volume", "/fade"):
                return self._send(404, {"error": "not found"})
            wait = float(body.get("wait", 0)) if path == "/fade" else 0
            sink = bluetooth_sink()
            if not sink and not wait:
                return self._send(409, {"error": "speaker not connected"})
            gen = new_generation()
            if path == "/volume":
                global fading
                fading = False  # any running fade stops (new generation)
                set_volume(sink["name"], float(body["volume"]))
            else:
                start = body.get("from")
                threading.Thread(
                    target=fade,
                    args=(
                        gen,
                        None if start in (None, "") else float(start),
                        float(body["to"]),
                        float(body.get("seconds", 10)),
                        wait,
                    ),
                    daemon=True,
                ).start()
            self._send(200, status())
        except (KeyError, TypeError, ValueError) as err:
            self._send(400, {"error": f"bad request: {err}"})
        except subprocess.SubprocessError as err:
            self._send(500, {"error": str(err)})

    def log_message(self, *args) -> None:
        pass


def main() -> None:
    daemon = subprocess.Popen(sys.argv[1:])

    def stop(*_):
        daemon.terminate()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    # The container lives as long as PulseAudio does.
    sys.exit(daemon.wait())


if __name__ == "__main__":
    main()
