# PulseAudio as the Bluetooth A2DP source for the host's BlueZ (over the system
# D-Bus), mixing every Spotify client into whichever speaker is connected.
FROM alpine:3.23
LABEL org.opencontainers.image.source="https://github.com/milliamp/boombox" \
      org.opencontainers.image.description="PulseAudio Bluetooth A2DP source for boombox"
RUN apk add --no-cache pulseaudio pulseaudio-bluez pulseaudio-utils dbus-libs
COPY boombox.pa /etc/pulse/boombox.pa
CMD ["pulseaudio", "--daemonize=no", "--exit-idle-time=-1", "--disallow-exit", "--log-target=stderr", "-n", "-F", "/etc/pulse/boombox.pa"]
