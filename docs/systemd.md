# Running the bridge + daemon as systemd services

By default the bridge and the Sinden Mono daemon are convenient to start by hand for development. For routine play, you want both running automatically on boot/login, surviving game crashes, and restarting on failure. This is what the units in `systemd/` are for.

## What gets installed

Two services with deliberately different scopes:

| Service | Scope | Runs as | Why |
|---|---|---|---|
| `sinden-mono.service` | system-level | `root` | The Sinden Mono daemon needs to write to `/dev/uinput`, talk to `/dev/ttyACM*` serial ports, and access `/dev/video*` cameras. Easiest if it just owns those devices outright via the system instance. |
| `sinden-bridge.service` | user-level | the desktop user | The bridge reads `/dev/input/event24,event26` (granted by our udev rule to the `plugdev` group), connects to `127.0.0.1:33610` for the BepInEx plugin, and sends TCP frames. Doesn't need root. Cleaner to run alongside your normal desktop session. |

## One-shot install

```bash
./systemd/install.sh
```

That copies the unit files into the right locations, reloads systemd, and enables both services for autostart. You can run it again any time to re-sync the units after editing.

## Manual install (if you want to read what's happening)

```bash
# system service
sudo cp systemd/sinden-mono.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sinden-mono.service

# user service
mkdir -p ~/.config/systemd/user
cp systemd/sinden-bridge.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now sinden-bridge.service
```

## Operating

```bash
# status
systemctl status sinden-mono.service
systemctl --user status sinden-bridge.service

# follow logs
journalctl -u sinden-mono.service -f
journalctl --user -u sinden-bridge.service -f

# restart after editing a unit file
sudo systemctl daemon-reload && sudo systemctl restart sinden-mono.service
systemctl --user daemon-reload && systemctl --user restart sinden-bridge.service

# stop / disable temporarily
sudo systemctl stop sinden-mono.service
systemctl --user stop sinden-bridge.service
```

The **panic-kill hotkey** (`Ctrl+Alt+Q`) still works — `sinden-stop.sh` is now somewhat redundant since the daemon will be auto-restarted by systemd if it dies. If you want the hotkey to actually keep the daemon dead, edit `sinden-stop.sh` to also `systemctl stop sinden-mono.service`.

## How "starts with OWR" works in practice

Neither unit triggers off OWR's process specifically — systemd doesn't have a clean way to do that. Instead:

- The **daemon** runs from boot. It auto-detects guns when they're plugged in, processes camera frames at ~66fps, and idles cheaply when there's no border to track.
- The **bridge** runs from login. It polls `127.0.0.1:33610` once every 2 seconds; when OWR launches and BepInEx opens the port, the bridge connects within a second.
- When OWR closes, the bridge sees the disconnect and goes back to polling.

The result is an effectively-on-demand pipeline: launch OWR via Steam exactly the way you would without this project, and the gun chain wires itself up. No wrapper scripts, no extra commands.

## Trade-offs

- **CPU**: the Sinden Mono daemon at 66fps OpenCV uses ~6-10% of one core continuously while a gun is connected. If you object to that during non-gaming use, `systemctl stop sinden-mono.service` and start it manually before gaming sessions. The unit's `Nice=5` keeps it from fighting foreground games.
- **Cursor hijack on boot**: the bridge grabs the gun's evdev mouse devices on startup, so the gun won't move the desktop cursor. That's a feature for gaming but means you can't use the gun as a desktop pointer while the bridge is running. To use the gun as a desktop mouse, stop the bridge.
- **Both guns required by daemon**: if you only have one gun plugged in, the Mono daemon should still start (it'll log "Number of Sinden Lightguns Found 1"). The bridge will keep polling event26 and stay silent for gun 2.

## Uninstall

```bash
systemctl --user disable --now sinden-bridge.service
sudo systemctl disable --now sinden-mono.service
rm ~/.config/systemd/user/sinden-bridge.service
sudo rm /etc/systemd/system/sinden-mono.service
sudo systemctl daemon-reload
systemctl --user daemon-reload
```
