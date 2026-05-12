# sinden-proton-bridge

Play **Operation Wolf Returns: First Mission** (and other DemulShooter-supported Unity arcade lightgun games) on **Linux** with a **Sinden Lightgun**. Real aim, real trigger, real reload, real cover, native gameplay — no Windows VM required.

This is the missing piece for Linux gamers who own Sinden gear. Every other guide says "use Windows." This project says "no."

---

## ✅ Features (what works today)

- **Full Sinden Lightgun aim, trigger, reload, weapon-switch, cover, and heal** in Operation Wolf Returns running under Steam Proton on Linux.
- **In-game white border drawn natively** by a custom BepInEx plugin (`SindenBorder`) — no Wayland overlay positioning, no window-decoration hacks, no exclusive-fullscreen requirement.
- **TCP-based Linux daemon** (`owr-bridge.py`) reads gun events via `evdev`, applies smoothing and outlier rejection, and forwards normalized aim coordinates to DemulShooter's BepInEx plugin running inside the Wine prefix on `127.0.0.1:33610`.
- **Both Sinden guns exclusively grabbed** at the kernel level so the gun's HID-mouse output doesn't hijack the desktop cursor while the bridge is running.
- **Hot-reload of border config** — edit `BepInEx/config/braino.sindenborder.cfg`, see results within half a second, no game restart.
- **Per-gun button bindings** for Heal (`H`), Cover (`Space`), Weapon-switch (middle-mouse), and Reload (right-mouse), configurable in `LightgunMono.exe.config`.
- **Two-player local co-op** wiring (both guns visible to the bridge and the DemulShooter plugin; OWR's own 2P mode renders both crosshairs).
- **Single-user-friendly setup**: narrow `sudoers` entry for the daemon, GNOME panic-kill hotkey (`Ctrl+Alt+Q`), udev rules giving gun device ACL access without re-login.

## 🤔 Why this project exists

Operation Wolf Returns has a vibrant Sinden Lightgun scene — on Windows. The community-standard tool ([DemulShooter](https://github.com/argonlefou/DemulShooter)) is built around Windows-process hooks that **explicitly don't work** under Wine / Proton for x64 Unity games (see [DemulShooter#196](https://github.com/argonlefou/DemulShooter/issues/196), closed "not planned"). The "official" path is dual-boot to Windows.

That's blocked for the original author because Windows 11 [doesn't support the Sinden firmware properly](https://www.sindenlightgun.com), and the older Sinden Windows firmware updater requires Windows 10 or earlier. So: no Windows, no DemulShooter, no Sinden in OWR. According to every public source, it's not possible.

It turns out it **is** possible — by recognizing that DemulShooter is actually two pieces: a Windows host app that doesn't run in Wine, and a [BepInEx](https://github.com/BepInEx/BepInEx)-based Unity plugin that runs fine inside the game's Mono runtime under Proton. The plugin and the host communicate over plain TCP on `127.0.0.1:33610` — a protocol that crosses the Wine boundary with zero friction because Wine's TCP stack is Linux's TCP stack. **Replace the Windows host with a Linux daemon and the whole thing works.**

This repo is that Linux daemon, the in-game border plugin we needed alongside it, the udev rules to make the Sinden's input devices behave on Linux, and the documentation to reproduce the setup.

## 🏗️ How it works

```
┌─────────────────────────────────────────────────────────────────┐
│  Linux desktop (GNOME / Wayland)                                │
│                                                                 │
│  ┌──────────────────┐    ┌────────────────────────┐             │
│  │ Sinden Lightgun  │───▶│  Sinden Mono daemon    │             │
│  │ (USB, /dev/...)  │    │  (OpenCV border track) │             │
│  └──────────────────┘    └──────────┬─────────────┘             │
│                                     │ sends gun-aim cmds        │
│                                     ▼                           │
│  ┌──────────────────┐    ┌────────────────────────┐             │
│  │ /dev/input/      │◀───│   Gun's USB HID mouse  │             │
│  │   event24,event26│    │   reports back via HID │             │
│  └────────┬─────────┘    └────────────────────────┘             │
│           │ grabbed exclusively                                 │
│           ▼                                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  owr-bridge.py (this repo)                              │    │
│  │   - reads ABS_X/Y + buttons from grabbed evdev          │    │
│  │   - applies EMA smoothing + outlier rejection           │    │
│  │   - maps gun ABS (0..32767) → game-window pixels        │    │
│  │   - sends 24-byte payload @ 60Hz via TCP                │    │
│  └────────────────────────┬────────────────────────────────┘    │
│                           │ TCP 127.0.0.1:33610                 │
│                           ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Wine / Proton prefix running OperationWolf.exe         │    │
│  │  ┌────────────────────────────────────────────────────┐ │    │
│  │  │  BepInEx 5 (Mono) loaded via winhttp.dll override  │ │    │
│  │  │  ┌────────────────────────┐  ┌───────────────────┐ │ │    │
│  │  │  │ DemulShooter plugin    │  │ SindenBorder      │ │ │    │
│  │  │  │  (TCP listener,        │  │  (this repo:      │ │ │    │
│  │  │  │   hooks OWR's input    │  │   draws white     │ │ │    │
│  │  │  │   system per packet)   │  │   frame via OnGUI)│ │ │    │
│  │  │  └────────────┬───────────┘  └───────────────────┘ │ │    │
│  │  │               │ Harmony-patches OWR's aim/input    │ │    │
│  │  │               ▼                                    │ │    │
│  │  │       OperationWolf game logic                     │ │    │
│  │  └────────────────────────────────────────────────────┘ │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

The key insight: the BepInEx **plugin** runs inside the Wine prefix and is OS-agnostic — it doesn't care that DemulShooter's host (which on Windows would feed it gun coords) was replaced by a Python daemon outside the Wine prefix. The protocol is TCP, the bytes are the same.

### Wire format (host → plugin)

| Bytes | Field | Type | Notes |
|------:|-------|------|-------|
| 0–7  | `Axis_X[2]`        | `float[]` | Per-player X in pixel space (`(0..Screen.width)`) |
| 8–15 | `Axis_Y[2]`        | `float[]` | Per-player Y in pixel space (`(0..Screen.height)`); Y=0 is bottom |
| 16–17| `ChangeWeapon[2]`  | `byte[]`  | 1 = weapon switch held |
| 18   | `EnableInputsHack` | `byte`    | Must be `1` for the plugin to override OWR's native mouse input |
| 19   | `HideCrosshairs`   | `byte`    | 1 to hide the in-game crosshair |
| 20–21| `Reload[2]`        | `byte[]`  | 1 = reload held |
| 22–23| `Trigger[2]`       | `byte[]`  | 1 = trigger held |

**No envelope on inputs** — bytes go straight into `TcpInputData.Update()` on the plugin side. Fields written in **alphabetical order by name** because the plugin uses `OrderBy(field.Name)` reflection. (Outputs from plugin → host *do* have a 4-byte length + 1-byte header envelope, but we're not consuming those yet.)

### Components in this repo

- **`owr-bridge.py`** — the Linux daemon. Reads `/dev/input/event24` (gun 1) and `/dev/input/event26` (gun 2), exclusively grabs them so the gun's HID-mouse output doesn't drive the desktop cursor, applies EMA smoothing + optional outlier rejection, maps gun coords into the OWR game-window coord space, and pushes payloads at 60Hz to the plugin.
- **`SindenBorder/`** — small BepInEx 5 plugin (C#) that draws a configurable white frame via `OnGUI` + `GUI.DrawTexture` so the Sinden's camera-based border tracker has a clean rectangle to lock onto. Hot-reloads its config every ~500ms; no game restart needed when you tweak width/color.
- **`owr-test-snap.py`** — protocol smoke test. Cycles a fake "gun" position through the four corners + center of the game window, useful for verifying the wire format end-to-end without involving a physical gun.
- **`owr-test-client.py`** — variant that draws a slow circle. Useful for first-time wire-format debugging.
- **`sinden-start.sh` / `sinden-stop.sh`** — wrapper scripts around `mono LightgunMono.exe` with a panic-kill banner. Pair these with a global keyboard shortcut (`Ctrl+Alt+Q`) so a runaway daemon is always one keystroke from death.
- **`owr-linux-plan.md`** — the original architecture exploration doc + the reverse-engineering notes for DemulShooter's IPC. Reads as a chronological log of how we got here.

## 🔧 Setup outline

This is not yet a turn-key installer. Reproducing the setup requires:

1. **Sinden Linux Lightgun software** — download from your Sinden account at [sindenlightgun.com](https://www.sindenlightgun.com), extract `SindenLightgunLinuxSoftwareV2.05/PCversion/Ubuntu_Version22_04_Beta/LightgunUbuntu_22_04/` somewhere. Sinden's daemon (`LightgunMono.exe`, run under `mono`) does the gun-aim → screen-pixel computation via OpenCV.
2. **System packages**: `mono-devel libgdiplus libopencv-core410 libopencv-imgproc410 libopencv-videoio410 libopencv-highgui410 libopencv-imgcodecs410 libsdl1.2debian libsdl-image1.2 v4l-utils evtest python3-evdev nfs-common` (Ubuntu 26.04 names; adjust per distro).
3. **udev rules** for your Sinden gun(s) — see [`docs/udev.md`](docs/udev.md) (TODO).
4. **OWR via Steam** with BepInEx 5 (Mono x64) installed in the game's directory plus the prebuilt `UnityPlugin_BepInEx_OperationWolfReturn` DLL from a [DemulShooter release](https://github.com/argonlefou/DemulShooter/releases) dropped in `BepInEx/plugins/`. Steam launch options: `WINEDLLOVERRIDES="winhttp=n,b" %command%`.
5. **Build SindenBorder**: `cd SindenBorder && ./build.sh` — it'll compile and drop the DLL into your OWR `BepInEx/plugins/` directory.
6. **Run it**: launch OWR, start the Sinden Mono daemon, start the bridge.

A real `INSTALL.md` is on the roadmap.

## 🗺️ Roadmap

### Near term

- **Calibration UI / mode** — at the moment, mapping gun coords to game-window coords assumes the game window is on the active display and uses sensible Sinden defaults. A calibration mode that lets the user shoot known on-screen targets would tighten this up without command-line fiddling.
- **Per-game profiles** — the bridge is hardcoded for OWR's TCP port and field layout. A small per-game config (port + button mapping + window-size source) would unlock other Unity titles in the DemulShooter ecosystem with minimal code.
- **Real `INSTALL.md`** — opinionated walk-through, dependencies per distro, troubleshooting matrix.
- **First-class second-gun support** — wiring exists; needs polish, 2P calibration story, and validation in an actual co-op session.
- **Recoil / LED output channel** — DemulShooter's plugin sends `TcpOutputData` *back* over the same socket with recoil + LED state. We currently ignore it; consuming it would let the gun's recoil solenoid fire when the in-game gun fires. Pure Linux feature parity with the Windows experience.

### Medium term

- **GNOME-native border alternative** — for games we *can't* attach BepInEx to (anti-cheat, IL2CPP-only without BepInEx-IL2CPP compatibility), a Wayland-friendly transparent always-on-top overlay drawn via `gtk-layer-shell` or a XWayland fallback. Lets the chain work even without an in-game plugin.
- **systemd user service** — `sinden-bridge.service` that auto-starts when `OperationWolf.exe` appears in the process list, dies when the game exits.
- **Pluggable lightgun back-ends** — current code is Sinden-specific. The bridge's input layer is small enough that AimTrak and GUN4IR adapters are realistic.
- **Custom OpenCV tracker** in Python — replace the Sinden Mono daemon entirely with a small Python+OpenCV reader that talks directly to the gun's serial port. Removes the Mono dependency, drops latency, gives us full control of the camera pipeline.

### Other games we could "easily" support

These all ship a [DemulShooter BepInEx Unity plugin](https://github.com/argonlefou/DemulShooter/tree/master/UnityPlugins). The plugin doesn't care about platform — it's a Mono DLL injected into the game's runtime. **For each, the work is: confirm the game runs under Proton, install BepInEx + the relevant plugin, find the TCP port the plugin opens, possibly tweak the bridge's wire format for that game's payload shape, and ship a SindenBorder analog if the game doesn't already have a clean border on screen.**

In rough order of likely effort:

- **Plants vs. Zombies: Garden Warfare** (PVZ) — large active community, well-documented Sinden setup on Windows.
- **Point Blank X** (PBX) — modern Namco arcade port, classic lightgun lineage.
- **The House of the Dead: Scarlet Dawn** equivalents using NHA / NHA2 (Night Hunter) plugins.
- **Rabbids Hollywood** (RHA) — Ubisoft arcade lightgun, very Sinden-friendly on Windows.
- **Wild West Shootout** (WWS) — indie arcade lightgun, simple input model.
- **Mission: Impossible Arcade** (MIA / MIB-themed variants).
- **Tomb Raider Arcade** (TRA) — Adrenaline Amusements arcade ports.
- **Dark Crystal of Power** (DCOP), **Drakon** (DRK), **Mars Sortie** (MARSS), **Men In Black** (MIB), **Nerf Arcade** (NHA), **Raw Thrills Nerf Arcade** (RTNA) — the rest of the DemulShooter Unity-plugin catalog.

Games that **don't** need this project at all (the Sinden already works as a normal mouse):

- *House of the Dead Remake* (2022, Forever Entertainment) — Steam, Proton, accepts mouse input directly.
- *Operation Wolf Returns: First Mission* — wait, no, that's the whole point of this repo.
- *Blue Estate* — point-and-click rail shooter, mouse input.

## ⚖️ Credits & disclaimers

- **DemulShooter** by [argonlefou](https://github.com/argonlefou/DemulShooter) does the heavy lifting on the Windows side. This project would not be possible without their open-source BepInEx plugin. All Unity-side plugins (`UnityPlugin_BepInEx_*`) used here are theirs; this repo only contains our own additions.
- **BepInEx** by the [BepInEx team](https://github.com/BepInEx/BepInEx) — universal Unity modding framework that gracefully handles the Mono runtime inside Wine.
- **Sinden Lightgun** — hardware and Windows software by [Sinden Technology](https://www.sindenlightgun.com). The Linux daemon shipped by Sinden is what does the camera-based aim tracking; this project orchestrates around it.

This repo redistributes none of the above. You need a legitimate Sinden software download (free with hardware purchase) and your own copy of any games you want to play.

## License

MIT — see [LICENSE](LICENSE).
