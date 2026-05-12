# Sinden Lightgun serial protocol (as reverse-engineered)

**Status:** documented from `monodis` IL disassembly of `LightgunMono.exe` v1.9, cross-referenced against gun HID descriptors. Personal-interoperability research only — Sinden's software is closed-source and we redistribute nothing of theirs in this repo.

## Frame formats

Two distinct frame types travel over the gun's USB CDC-ACM serial port (`/dev/ttyACM*`):

### Config frame (one-time, at daemon boot)

```
+------+------+------+------+------+------+------+
| 0xAA |  CMD |  P1  |  P2  |  P3  |  P4  | 0xBB |
+------+------+------+------+------+------+------+
   0      1      2      3      4      5      6
```

7 bytes. `0xAA` start marker, `0xBB` end marker, single command byte, four parameter bytes.

### Runtime frame (continuous, per camera-tracked aim update)

```
+------+------+------+------+------+------+
| 0xDE |  ??  |  ??  |  ??  |  ??  | 0xDF |
+------+------+------+------+------+------+
```

6 bytes. `0xDE` start marker, `0xDF` end marker, 4 payload bytes (likely X-hi, X-lo, Y-hi, Y-lo or similar packing of the daemon-computed aim coordinate). Emitted by `MoveMouse` / `ProcessImage` methods every frame the daemon has a valid OpenCV target.

## Complete command vocabulary

Every distinct `CMD` byte the daemon ever emits. Note the gaps — there are **NO commands** in the ranges `0xA3-0xFF` (except `0xa1` and `0xa2`) or `0x00-0x28`, etc.

| CMD | Method | When | Apparent purpose |
|---|---|---|---|
| `0x29` | MoveMouse | runtime setup (once) | Initialize mouse-mode tracking |
| `0x36` | SetupLightgunSettings | boot | Apply calibration / general settings |
| `0x3c` | AssignButtons | boot (×27 per gun) | Map each physical button to a key/mouse-action |
| `0x6a` | ProcessImage | runtime setup (once) | Initialize image processing |
| `0x6d` | HandshakeWithLightgun | boot | Read-response handshake stage |
| `0x6e` | HandshakeWithLightgun | boot | Initial handshake |
| `0x79` | HandshakeWithLightgun | boot | Finalize handshake |
| `0xa1` | SwitchOffRecoil | boot (if `EnableRecoil=false`) | Disable recoil entirely |
| `0xa2` | AssignRecoil | boot (if `EnableRecoil=true`) | Configure recoil (strength, mode, delays, per-button) |

## The recoil situation

**The daemon NEVER issues a "fire recoil now" command at runtime.** Verified two independent ways:

- Every named method in `LightgunMono.dll` that calls `SerialPort.Write` only emits boot-time config frames or runtime aim updates (`0xDE`-framed). No method writes to the serial port in response to button events.
- `strace -f -e write` on the running daemon, filtered to the `/dev/ttyACM1` fd, shows zero writes during 10-second windows of active gameplay with multiple trigger pulls. (The aim-update stream pauses when the daemon doesn't have a valid target, so writes are sparse.)

The HID side reinforces this — the gun's USB HID descriptor (107 bytes) contains only `0x81` (INPUT) report items for the mouse and keyboard interfaces. No `0x91` (OUTPUT) report items exist, so we can't send recoil commands via HID either.

### What `0xa2 AssignRecoil` actually does

The 4 parameter bytes after `0xa2` carry the recoil configuration:

- `RecoilStrength` (0-100)
- `AutoRecoilStrength` (0-100)
- Per-button armed flags (`RecoilTrigger`, `RecoilPumpActionOnEvent`, `RecoilFrontLeft`, etc.)
- Auto-fire timing (`AutoRecoilStartDelay`, `AutoRecoilDelayBetweenPulses`)
- `TriggerRecoilNormalOrRepeat`

These map directly to the fields visible in `LightgunMono.exe.config`. The gun's firmware applies this config to its local trigger-handling code: when the relevant button is pressed, fire the solenoid with the configured strength/timing.

### What we wanted vs. what we have

| Wanted | Have |
|---|---|
| Per-shot recoil driven by the game's `Recoil[player]` signal | Per-trigger-pull recoil driven by the gun's local button state |
| Variable strength per weapon (pistol soft, shotgun strong) | One global strength applied to every trigger pull |
| No false recoil when out of ammo / in cover / in menus | Recoil fires on ANY trigger pull while gun is on-screen |

## Architectural conclusion

**Game-event-driven recoil is not achievable with the unmodified Sinden firmware.** The gun's microcontroller is the only thing that ever decides to fire the solenoid, and it does so based purely on local trigger state + `0xA2` config.

Realistic paths if we want game-driven recoil:

1. **Fuzz the command space** — send each unknown `0xCC` byte (with random 4-byte payloads) and watch for solenoid pulses. Risky: random parameters could brick the gun, overheat the solenoid, or trigger unknown calibration paths. Low confidence the command even exists.

2. **Custom gun firmware** — replace the Sinden firmware with our own. Requires:
   - Reading the gun's chip via ICSP / SWD
   - Reverse-engineering / rewriting the entire gun logic
   - Reflashing
   - Voids warranty, irreversible if done wrong.

3. **Hardware mod** — splice a relay/transistor into the solenoid wires, drive it from a Raspberry Pi GPIO triggered by the bridge daemon. Bypass the gun's firmware entirely for recoil. Requires opening the gun chassis. Reversible-ish.

4. **Accept the limitation** — tune `RecoilStrength`, `AutoRecoilStrength`, `TriggerRecoilNormalOrRepeat`, and `AutoRecoilStartDelay` for the best feel across most weapons in the games we care about. This is the entire API Sinden offers.

## Recommendation

**Path 4** is the only one with bounded cost. The current Sinden tuning gives us:

- Pistol-feeling for tap-style triggers (single-shot recoil)
- Auto-fire for held triggers (transitioning at `AutoRecoilStartDelay`)
- Per-button strength via `0xA2` config

The downside (machine-gun recoil when holding a semi-auto pistol's trigger) is annoying but tolerable. Better to ship a working, configurable system than chase a "perfect" recoil that requires firmware mods.

If we ever want to revisit, **Path 3 (hardware relay)** is the most realistic next step — it doesn't require firmware reverse-engineering, just basic soldering and a GPIO output, and it cleanly decouples our recoil control from the gun's internal logic.

## What we WILL ship soon

The bridge's `TcpOutputData` consumer (already wired) gives us per-shot game events. Even if we can't drive the gun's solenoid from them, we can:

- Log them for stats / debugging
- Drive other haptics — e.g. a USB rumble controller, a Buttkicker, a desk-mounted solenoid
- Drive on-screen feedback (a Unity GUI flash, a screen-shake plugin)
- Use them for telemetry (shot count, accuracy)

The `Damaged`, `Life`, and `Ammo` outputs especially are valuable for telemetry and feedback features that don't need the gun's solenoid.
