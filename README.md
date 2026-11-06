# boombox

Spotify on a Bluetooth speaker plugged into nothing but a Linux server, controlled from
Home Assistant. Built for a UE BOOM 3 on a Docker host, but any A2DP speaker works.

```
 phones (Spotify app) ─┐                     ┌─ boombox-spotify-1 (account A) ─┐
 Home Assistant ───────┼── Spotify cloud ────┤                                 ├─ boombox-pulseaudio ── BlueZ ── 🔊
   (Spotify integration)                     └─ boombox-spotify-2 (account B) ─┘     (A2DP source)
 Home Assistant ── ha-ueboom (BLE power) ─────────────────────────────────────────────────────────────┘
```

- **boombox-spotify:** the **official** Spotify Linux client, headless (Xvfb). One container per account. Each
  shows up as **"Boom"** in that account's Spotify device list. It uses the official client because Spotify
  refuses audio keys to librespot-based players (go-librespot, raspotify, spotifyd) for a growing number of
  accounts ([go-librespot#279](https://github.com/devgianlu/go-librespot/issues/279)).
- **boombox-pulseaudio:** registers with the host's BlueZ as an A2DP source, mixes the clients, and follows the
  speaker as it connects and disconnects.
- **[ha-ueboom](https://github.com/milliamp/ha-ueboom):** switches a UE BOOM on and off over BLE from HA. On
  power-on the speaker connects its audio to the host by itself.
- **`ha/blueprints/script/boombox_play.yaml`:** switches the speaker on, picks the first account (by name) that
  isn't playing on another device, moves its playback to "Boom" and starts a playlist.

## Setup

### 1. Host (once)

Pair and trust the speaker with the host's BlueZ. Put the speaker in pairing mode first:

```bash
bluetoothctl
  agent NoInputNoOutput
  default-agent
  scan on            # wait for the speaker's name, note its MAC
  pair  XX:XX:XX:XX:XX:XX
  trust XX:XX:XX:XX:XX:XX
```

### 2. Stack (Portainer)

**Stacks → Add stack → Repository**: `https://github.com/milliamp/boombox`, compose path `docker-compose.yml`.
Add the environment variable `VNC_PASSWORD=<something>` for the first deploy.

Then, for each account, open `http://<host>:6091/vnc.html` (account 1) or `:6092` (account 2), enter the
password and **scan the QR code** with that account's phone. The "Log in" button needs a web browser, which
the container doesn't have. The login is stored in `/data/boombox/spotify-N`.

Once both accounts are logged in, remove `VNC_PASSWORD` and redeploy. That turns noVNC off.

### 3. Home Assistant

1. Install [ha-ueboom](https://github.com/milliamp/ha-ueboom) through HACS and add the speaker.
2. Create a Spotify app at [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard). Set the
   redirect URI to `https://my.home-assistant.io/redirect/oauth`, select the Web API, and add each account's email
   under *User Management*. Since February 2026, development-mode apps need a Premium owner and allow up to 5 users.
3. Add the **Spotify** integration once per account, using the app's client ID and secret.
4. Import the blueprint:

   [![Import blueprint](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fmilliamp%2Fboombox%2Fblob%2Fmain%2Fha%2Fblueprints%2Fscript%2Fboombox_play.yaml)

   Create a script from it, then call it from any automation:

   ```yaml
   action: script.boombox_play
   data:
     playlist: spotify:playlist:0XWM4RAYRE5pWJGsOSOEmf   # optional, else the default
     volume: 30                                         # optional
   ```

## Everyday use

Anyone on either account can open Spotify, tap the devices icon and pick **Boom**. Spotify Jam works too.

## Notes

- The clients restart themselves if they crash or update. The weekly image build picks up new Spotify releases.
- Spotify's Linux client is "unofficially supported" by Spotify, so a future release could need tweaks.
- `apparmor=unconfined` is only needed by the PulseAudio container (system D-Bus). Nothing runs privileged.

## License

MIT. The Spotify client is downloaded from Spotify's own apt repository at build time under Spotify's terms.
