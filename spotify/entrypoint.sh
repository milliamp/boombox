#!/bin/sh
# Official Spotify desktop client, headless, as a Spotify Connect speaker.
#   DISPLAY_NUM   X display number (any; containers have their own /tmp)
#   LOGIN_PORT    login-helper HTTP port: /status and /qr.png (default 8091)
#   NOVNC_PORT    browser VNC port, for debugging (default 6091)
#   VNC_PASSWORD  set it to enable noVNC
#   FOLLOW_SPEAKER  1 (default): run the client only while a Bluetooth speaker
#                 is connected, so the device disappears from Spotify when the
#                 speaker goes off (phones fall back to themselves, like with
#                 any speaker). A client that isn't logged in always runs, so
#                 you can log in. 0: always run.
#   SPEAKER_GRACE seconds without a speaker before the client stops (default 30)
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

PULSE_SOCKET="${PULSE_SERVER#unix:}"
FOLLOW_SPEAKER="${FOLLOW_SPEAKER:-1}"
SPEAKER_GRACE="${SPEAKER_GRACE:-30}"
PREFS="$HOME/.config/spotify/prefs"
NEEDS_LOGIN=/tmp/boombox-needs-login  # written by login-helper while the QR shows

speaker_connected() { pactl list sinks short 2>/dev/null | grep -q 'bluez_sink\.'; }
saved_login() { grep -q '^autologin\.username=' "$PREFS" 2>/dev/null; }
want_client() {
  [ "$FOLLOW_SPEAKER" = 0 ] && return 0
  saved_login || return 0
  [ -e "$NEEDS_LOGIN" ] && return 0
  speaker_connected
}
pulse_id() { stat -c %i "$PULSE_SOCKET" 2>/dev/null || echo none; }
stop_client() {
  pkill -TERM -f /usr/share/spotify/spotify 2>/dev/null || true
  i=0
  while kill -0 "$1" 2>/dev/null && [ "$i" -lt 15 ]; do sleep 1; i=$((i + 1)); done
  pkill -KILL -f /usr/share/spotify/spotify 2>/dev/null || true
  wait "$1" 2>/dev/null || true
}

# Supervise the client: start it when wanted, restart it if it exits (update
# prompt, crash) or PulseAudio restarts (it never reconnects to a new audio
# server and would stay silent), stop it SPEAKER_GRACE s after the speaker goes.
while true; do
  if ! want_client; then
    echo "waiting for a speaker"
    until want_client; do sleep 2; done
  fi
  # Stale Chromium profile locks (after a hostname change or crash) make the
  # client quit silently. Only one client runs per container, so clear them.
  find "$HOME/.cache/spotify" "$HOME/.config/spotify" -maxdepth 2 -name "Singleton*" -exec rm -f {} + 2>/dev/null || true
  # Chromium needs a session bus or its renderer/network processes die (black
  # window). The container is the sandbox, so Chromium's own is disabled.
  dbus-run-session -- spotify --no-sandbox --no-zygote --disable-gpu --disable-dev-shm-usage "$@" &
  pid=$!
  echo "spotify started"
  pulse=$(pulse_id)
  idle=0
  reason=exited
  while kill -0 "$pid" 2>/dev/null; do
    sleep 2
    now=$(pulse_id)
    if [ "$now" != none ] && [ "$pulse" != none ] && [ "$now" != "$pulse" ]; then
      reason="PulseAudio restarted"
      break
    fi
    [ "$now" = none ] || pulse=$now
    if want_client; then idle=0; else idle=$((idle + 2)); fi
    if [ "$idle" -ge "$SPEAKER_GRACE" ]; then
      reason="no speaker for ${SPEAKER_GRACE}s"
      break
    fi
  done
  echo "spotify stopping: $reason"
  stop_client "$pid"
  if [ "$reason" = exited ]; then sleep 5; fi
done
