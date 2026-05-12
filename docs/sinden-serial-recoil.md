# Reverse-engineering the Sinden serial protocol for game-driven recoil

**Beads:** `sinden-brg` (P3, in-progress)
**Goal:** Drive the Sinden gun's solenoid from the BepInEx plugin's `Recoil[player]` events (game-side, per-shot) instead of from the daemon's local trigger-button detection.

## Why this matters

The Sinden Mono daemon currently does both jobs:

- Position tracking: read camera frame → OpenCV → send "move to X,Y" command to gun via `/dev/ttyACM1`
- Local recoil: watch the gun's HID button state → when trigger pressed AND on-screen, send "recoil now" command via `/dev/ttyACM1`

The local-recoil path has no knowledge of the **game's actual fire events.** Result: holding the trigger on a semi-auto pistol causes machine-gun recoil because the gun's firmware (or the daemon) doesn't know the game is only firing once per click.

The BepInEx plugin DOES know per-shot fire events — it sets `TcpOutputData.Recoil[i] = 1` for one frame on each game-side weapon fire (see `UnityPlugins/UnityPlugin_BepInEx_OWR/Patch/mWeapon.cs:22`). Our bridge already reads this. We just can't get the signal to the gun's solenoid.

If we can send recoil commands directly from our bridge, we get:

- **One recoil per actual shot** for any weapon
- **Auto-fire feel** for actual auto weapons (the game emits Recoil at the right tick rate)
- **No false recoil** when game is in pause/menu/cover

## What we know so far

- **Gun reports as USB CDC ACM serial** on `/dev/ttyACM1` (gun 1, vendor `16c0:0f39`) and `/dev/ttyACM2` (gun 2, vendor `16c0:0f01`).
- **Sinden Mono daemon owns the port** while running — it's the `mono LightgunMono.exe` process. Daemon writes position updates continuously and recoil commands when triggered.
- **Daemon log confirms recoil module loaded** on each gun boot:
  ```
  Lightgun1 Assigned Recoil.
  Lightgun2 Assigned Recoil.
  ```
- **`EnableRecoil=1` in `LightgunMono.exe.config`** is what activates the local-trigger recoil path. Setting it to `0` disables daemon-side recoil — leaving the gun ready to receive recoil commands from us if we know the wire format.
- **Sinden Wiki has no serial-protocol documentation** — checked the Linux Unix Guide and DemulShooter page. Sinden's only software-side support is via `LightgunMono.exe`.
- **mdeguzis/sinden-lightgun-linux does not touch the protocol** — it wraps the official daemon, doesn't reimplement.

## Investigation paths (ranked best → worst)

### Path A: Decompile LightgunMono.exe with ILSpy/dnSpy

The Sinden daemon is a regular .NET assembly. Mono decompilers produce very readable C# from .NET IL. We should be able to:

- Read the SerialPort write code directly
- See exact byte sequences for "move cursor to X,Y," "fire recoil," etc.
- See what other commands exist (LED control? calibration save?)
- Confirm the baud rate, frame format, etc.

Tools on Linux:
- `ilspycmd` — CLI decompiler (NuGet tool, dotnet)
- `dnSpy` — full GUI (Windows-mostly, can run under Wine)
- `monodis` — Mono's built-in disassembler (IL output, not C#; less readable but works)
- `ildasm` — also IL-only

Recommended starter:
```bash
# install ilspycmd
dotnet tool install -g ilspycmd

# decompile
ilspycmd /home/braino/workspace/sinden/run/LightgunMono.exe -o /tmp/lightgun-src
```

Search for: `SerialPort.Write`, `Recoil`, `_serialPort`, `ttyACM`, byte literal arrays sent to ports.

**Risk:** EULA. Sinden's software has some license terms; decompilation may technically violate them. Reverse-engineering for interoperability is generally protected (DMCA §1201(f), EU Software Directive 2009/24/EC Art. 6), but this is a closed-source consumer product. Personal use is the most defensible. We should NOT redistribute decompiled source.

### Path B: Snoop the serial port with strace

Run the daemon under `strace` and log every `write(fd, …)` to the TTY. Decode the bytes by correlating with daemon behavior (e.g., trigger the gun → see what bytes were written in that moment).

```bash
sudo strace -e trace=write -p $(pgrep -f LightgunMono.exe) -o /tmp/sinden-writes.log -s 256
```

Pros: No license risk. Direct observation of the wire.
Cons: Slower (lots of writes per second for position updates). Need to deduplicate position spam to find recoil commands.

A clever variation: only watch writes that happen WITHIN N ms of a trigger press. The position stream is continuous; recoil should be a one-shot.

### Path C: Physical serial sniffer

USB-serial line tap with a logic analyzer (Saleae, sigrok-supported analyzer) sitting between gun and PC. Definitive but requires hardware.

### Path D: Existing community knowledge

A handful of arcade-cab Discord servers may have informally documented the protocol for custom builds. Worth a quiet ask on the Sinden Discord's `#linux` channel after we have a working prototype to share back.

## Recommended order of operations

1. **Path A first** — fastest path to a complete picture of the protocol. ~1 hour to decompile + read.
2. **Path B as cross-check** — verify our reading of the .NET code against actual wire traffic. Catches any reflection-based or runtime-dispatched message construction. ~30 min.
3. **Path D after we publish** — community feedback can refine.

Skip Path C unless A and B both leave gaps.

## Once we have the protocol

### Architectural decision

Two ways to integrate:

| Approach | Pros | Cons |
|---|---|---|
| **Shared port** — leave Sinden daemon running for position tracking, our bridge opens `/dev/ttyACM1` concurrently and writes only recoil commands. | Minimal change. Sinden daemon still handles the hard part (OpenCV). | Linux allows multiple writers to a TTY but bytes from independent writers can **interleave mid-message**, corrupting both sides' frames. Risky unless the protocol is byte-tolerant or the daemon has long quiet periods. |
| **Disable daemon recoil + standalone recoil sender** — set `EnableRecoil=0`, write our own thin "recoil-only" Python helper. Same shared-port risk. | Cleaner separation. Gun's local trigger logic is disabled; ONLY our game-event recoil fires. | Same interleaving risk. |
| **Replace daemon entirely** — write a Python+OpenCV daemon that owns the camera, the position protocol, AND the recoil protocol. | Full control. No interleaving. Long-term cleaner. | Multi-day project. Re-implements work Sinden already did well. |

**Recommended path: try shared-port first.** Recoil commands are likely short (a single byte or two — "fire recoil now") and the daemon's position stream might have natural quiet windows. If interleaving corrupts the stream in practice, fall back to standalone reimpl.

### Implementation sketch (once protocol is known)

`owr-bridge.py` gets a new helper:

```python
import serial

class RecoilDriver:
    def __init__(self, tty_path):
        self.port = serial.Serial(tty_path, baudrate=???, timeout=0)
    def fire(self, strength: int = 50):
        cmd = bytes([???, strength, ???])  # TBD from protocol research
        self.port.write(cmd)
```

In the sender loop:

```python
if outputs.recoil[i] and not last_recoil[i]:
    recoil_drivers[i].fire()
```

The bridge already detects the rising edge of `outputs.recoil[i]` (see `owr-bridge.py` post-sender block) and logs it. Adding the serial fire call is trivial once we know the bytes.

### Per-shot strength

If the protocol supports variable strength (likely — `RecoilStrength` is a config value, so the daemon must transmit a strength byte), we can scale recoil by weapon. Need a per-weapon strength table:

| Weapon | Strength |
|---|---|
| Pistol | 60 |
| Uzi | 35 |
| Shotgun | 90 |
| Rocket | 100 |

OWR doesn't tell us the active weapon via TcpOutputData currently. We could either:
- Detect from rate of Recoil events (auto-fire = lower strength)
- Patch the BepInEx plugin to expose weapon ID
- Read the game's RAM via BepInEx Harmony

The "rate detection" approach needs zero further plugin changes: if Recoil fires faster than N times per second, treat as auto-fire and use lower strength; else single-shot, use higher strength. Heuristic but cheap.

## Risks

- **EULA / DMCA**: decompiling Sinden software for personal-use interoperability is generally legal in US/EU but pushes against the spirit of their proprietary license. We should NOT redistribute decompiled source or ship a recoil reimplementation that obviously copies Sinden's exact byte sequences without attribution. We CAN ship the protocol description and a clean-room implementation.
- **Hardware damage**: the gun's solenoid has duty-cycle limits. Firing too fast or too long can overheat/burn out the coil. Our bridge needs a rate limiter (e.g. max 20 recoils/second, or honor Sinden's `AutoRecoilDelayBetweenPulses` even when we're driving it).
- **Two-writer port corruption**: see architectural note above. If shared-port doesn't work, the project gets significantly bigger.

## Success criteria

- Pistol single-shot: ONE recoil pulse per trigger pull at moderate strength
- Auto weapon (uzi): rapid recoil pulses synced to game-side fire rate at lower strength
- No false recoil while in menus, taking cover, or out of ammo
- Both players supported

## Handoff: what's done, what's next

**Done (in this session):**
- Identified the gap (sinden-brg filed P3)
- Documented why the daemon's local-trigger recoil produces wrong feel for mixed-weapon games
- Drafted this investigation plan
- Confirmed BepInEx output channel works and feeds Recoil events into the bridge

**Open (pick up next):**
1. Install `ilspycmd` and decompile `/home/braino/workspace/sinden/run/LightgunMono.exe`
2. Grep the decompiled source for `SerialPort`, `Recoil`, and any byte-array literals; document the wire protocol in a follow-up doc (`docs/sinden-serial-protocol.md`)
3. Cross-check with `strace` on the running daemon
4. Decide architecture (shared port vs. reimplementation) based on findings
5. Prototype, test, integrate into `owr-bridge.py`
