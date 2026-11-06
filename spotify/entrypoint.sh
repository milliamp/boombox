#!/bin/sh
# Official Spotify desktop client, headless, as a Spotify Connect speaker.
#   DISPLAY_NUM   X display number (any; containers have their own /tmp)
#   LOGIN_PORT    login-helper HTTP port: /status and /qr.png (default 8091)
#   NOVNC_PORT    browser VNC port, for debugging (default 6091)
#   VNC_PASSWORD  set it to enable noVNC
set -eu
DISPLAY_NUM="${DISPLAY_NUM:-91}"
export DISPLAY=":${DISPLAY_NUM}"
export PULSE_SERVER="${PULSE_SERVER:-unix:/run/pulse/native}"
export HOME=/home/spotify

# Stable machine id (see Dockerfile): generated once per data volume.
[ -s "$HOME/.machine-id" ] || dbus-uuidgen > "$HOME/.machine-id"

rm -f "/tmp/.X${DISPLAY_NUM}-lock" "/tmp/.X11-unix/X${DISPLAY_NUM}"
Xvfb "$DISPLAY" -screen 0 1280x800x24 -nolisten tcp &
sleep 1

if [ -n "${VNC_PASSWORD:-}" ]; then
  NOVNC_PORT="${NOVNC_PORT:-6091}"
  x11vnc -storepasswd "$VNC_PASSWORD" /tmp/vncpass >/dev/null
  VNC_PORT=$((5900 + DISPLAY_NUM))
  x11vnc -display "$DISPLAY" -rfbauth /tmp/vncpass -rfbport "$VNC_PORT" -localhost -forever -shared -quiet &
  websockify --web /usr/share/novnc "$NOVNC_PORT" "localhost:$VNC_PORT" >/dev/null 2>&1 &
  echo "noVNC: http://<host>:${NOVNC_PORT}/vnc.html"
fi

login-helper &

# Restart the client if it exits (e.g. after an update prompt or crash).
while true; do
  # Stale Chromium profile locks (after a hostname change or crash) make the
  # client quit silently. Only one client runs per container, so clear them.
  find "$HOME/.cache/spotify" "$HOME/.config/spotify" -maxdepth 2 -name "Singleton*" -exec rm -f {} + 2>/dev/null || true
  # Chromium needs a session bus or its renderer/network processes die (black
  # window). The container is the sandbox, so Chromium's own is disabled.
  dbus-run-session -- spotify --no-sandbox --no-zygote --disable-gpu --disable-dev-shm-usage "$@" || true
  echo "spotify exited; restarting in 5s"
  sleep 5
done
