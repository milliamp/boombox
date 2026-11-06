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
- **`ha/blueprints/script/boombox_play.yaml`:** switches the speaker on (or reconnects its audio), waits for
  its *Audio connected* sensor, picks the first account (by name) that isn't playing on another device, moves its
  playback to "Boom" and starts a playlist. The speaker starts silent and fades in once the music plays.
  Needs ha-ueboom ≥ 0.2.
- **`ha/blueprints/script/boombox_stop.yaml`:** fades the speaker out (default 30 s), pauses Spotify if it's still
  playing on "Boom", puts the speaker volume back and switches the speaker off.
- **Speaker volume:** the PulseAudio container serves the speaker's own volume on `127.0.0.1:8090` (set, and
  fade); the HA package turns it into `number.boombox_speaker_volume` and the actions the blueprints use.

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
**Logging in, without VNC.** Each client runs a small *login-helper* that screenshots its own display, decodes
Spotify's "scan to log in" QR code (a `https://spotify.com/pair?code=…` link) and serves it on
`127.0.0.1:8091` / `:8092`, which only the host (and HA on host networking) can reach. Install
`ha/packages/boombox.yaml` (see below). HA then notifies you while a client is logged out, with a link to tap on
the phone of the account that client should use. It also shows the QR code as an image entity. The login is
stored in `/data/boombox/spotify-N`.

For debugging you can set `VNC_PASSWORD` to get noVNC at `http://<host>:6091/vnc.html` / `:6092`.

### 3. Home Assistant

1. Copy `ha/packages/boombox.yaml` to `<config>/packages/` and enable packages
   (`homeassistant: packages: !include_dir_named packages`), then restart.
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

**Boom** shows up in Spotify only while the speaker is connected to the server, like any real speaker. Switch the
speaker on (its power button or HA) and after 10-15 s anyone on either account can tap the devices icon and pick
**Boom**. Spotify Jam works too. When the speaker goes off, the clients quit after 30 s
(`SPEAKER_GRACE`), so Boom disappears and phones fall back to themselves. A client that isn't logged in keeps
running so you can log in at any time. `FOLLOW_SPEAKER=0` keeps the clients running all the time.

If the speaker is connected to someone else's phone, the play blueprint leaves it alone instead of taking it over.

The play blueprint switches to Boom right after switching the speaker on. HA's Spotify integration refreshes
its device list only every 5 minutes, and `select_source` ignores devices it doesn't know yet, so it needs a
small change to refresh the list first: in `homeassistant/components/spotify/media_player.py`,
`async_select_source` starts with `await self.devices.async_refresh()` (installed as a
`custom_components/spotify` copy of the built-in integration). Without it, switching to Boom works only once
HA's next device refresh has seen it.

## Notes

- The clients restart themselves if they crash or update. The weekly image build picks up new Spotify releases.
- Spotify's Linux client is "unofficially supported" by Spotify, so a future release could need tweaks.
- `apparmor=unconfined` is only needed by the PulseAudio container (system D-Bus). Nothing runs privileged.

## License

MIT. The Spotify client is downloaded from Spotify's own apt repository at build time under Spotify's terms.
