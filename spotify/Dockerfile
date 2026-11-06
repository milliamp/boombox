# The official Spotify Linux client, headless (Xvfb), playing to a PulseAudio
# server over a shared unix socket. noVNC is only for the one-time login.
FROM debian:trixie-slim
LABEL org.opencontainers.image.source="https://github.com/milliamp/boombox" \
      org.opencontainers.image.description="Headless official Spotify client as a Spotify Connect speaker"
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends curl gnupg ca-certificates >/dev/null \
 && curl -fsSL https://download.spotify.com/debian/pubkey_5384CE82BA52C83A.asc | gpg --dearmor -o /etc/apt/trusted.gpg.d/spotify.gpg \
 && echo "deb https://repository.spotify.com stable non-free" > /etc/apt/sources.list.d/spotify.list \
 && apt-get update -qq && apt-get install -y -qq --no-install-recommends spotify-client xvfb x11vnc novnc websockify \
      libpulse0 pulseaudio-utils dbus-x11 fonts-dejavu-core procps >/dev/null \
 && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 spotify
COPY --chmod=0755 entrypoint.sh /usr/local/bin/entrypoint.sh
USER spotify
WORKDIR /home/spotify
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
