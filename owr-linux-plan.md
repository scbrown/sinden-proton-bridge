# Operation Wolf Returns + Sinden Lightgun on Linux — Plan

## The problem

- OWR (Steam, Unity x64) does not natively accept the Sinden's HID mouse output for aim. On Windows, you need [DemulShooter](https://github.com/argonlefou/DemulShooter) to translate Sinden input into something the game accepts.
- DemulShooter's host application (`DemulShooterX64.exe`) does not hook 64-bit games running under Wine/Proton — confirmed by [GitHub issue #196](https://github.com/argonlefou/DemulShooter/issues/196), closed "not planned."
- Dual-boot is the documented "blessed" path, but Windows 11's HID stack reportedly breaks Sinden recoil/firmware features — so that's off the table for you.

## The breakthrough

DemulShooter's Unity-game support is actually split into two pieces:

1. **Host** — `DemulShooterX64.exe`, a C# Windows app. Reads the gun, talks IPC to the plugin. **This is the part that breaks under Wine.**
2. **Plugin** — a [BepInEx](https://github.com/BepInEx/BepInEx) C# DLL (`UnityPlugin_BepInEx_OWR`) loaded into OWR's Mono runtime at startup. **BepInEx is cross-platform and works under Wine/Proton.** The plugin runs inside the game process and applies aim/trigger to Unity's input system.

The plugin and the host communicate over an IPC channel (almost certainly a Windows named pipe — under Wine these are implemented as Unix sockets inside the prefix). The plugin doesn't know or care what's on the other end of the pipe.

**So the hack:** keep the BepInEx plugin (already does the hard Unity work), replace only the host with a Linux daemon that reads our Sinden gun and writes the same IPC protocol to the plugin's pipe.

## Realistic paths, ranked

| # | Path | Effort | Risk | Notes |
|---|------|--------|------|-------|
| 1 | BepInEx plugin + Linux host daemon | Medium (1-2 weekends) | Low | Reuse the existing OWR plugin verbatim. Write a Linux daemon that reads the gun and speaks DemulShooter's IPC. Most leverage. |
| 2 | Sinden joystick mode → uinput XInput | Low (~30 min to test) | Medium — depends on whether OWR accepts gamepad aim | Sinden firmware can expose as a HID joystick. If OWR's input system reads gamepad axes for aim, no DemulShooter equivalent needed. |
| 3 | Fork the OWR plugin to read gun directly | Medium-high | Low | Modify the BepInEx plugin to read `/dev/sinden-gun-1` directly via P/Invoke into Linux libc. Self-contained, no IPC, no separate daemon. |
| 4 | Wine DLL override mimicking the DemulShooter host | High | Medium | Write a Win32-targeted C# tool that does the same hooks but Wine-friendly. Brittle. |
| 5 | Direct memory patching of OWR | High | High | Reverse-engineer OWR's aim variable, patch from outside. Breaks on every game update. |

## Recommendation

**Path 2 first** (cheap, 30 min to fail). If it doesn't work, **Path 1** is the real project.

## Concrete phased plan

### Phase 0 — verify the assumption (~1 hour)

Confirm BepInEx works under Proton with OWR.

- Identify OWR's Unity version (IL2CPP vs Mono — affects which BepInEx flavor).
- Install BepInEx into the OWR Proton prefix.
- Launch OWR; confirm BepInEx log shows it loaded.
- Drop in the `UnityPlugin_BepInEx_OWR` DLL; confirm it loads and creates its IPC endpoint.

### Phase 1 — try the cheap test (Path 2, ~30 min)

- Flip Sinden firmware to **joystick mode** (`JoystickModeEnabled` in the daemon config, or the firmware-update tool).
- Launch the Sinden Mono daemon with the `joystick` flag.
- Sinden enumerates as a HID joystick; Linux exposes it via `/dev/input/js*`; Wine maps it as DirectInput/XInput inside OWR's Proton prefix.
- Launch OWR. In its input settings try "gamepad" mode and see if aim follows the gun.

If aim works in joystick mode — done, no further coding needed.

### Phase 2 — if Phase 1 fails, the real project (Path 1, 1-2 weekends)

1. **Read DemulShooter source to nail the IPC spec.**
   - Plugin side: `UnityPlugins/UnityPlugin_BepInEx_OWR/*.cs`
   - Host side: `DemulShooterX64/Games/Game_OperationWolfReturn.cs` (or similar)
   - Find: pipe name, message format (likely a small struct: x, y, trigger, reload, button bits).
2. **Verify the Wine pipe bridge.**
   - When BepInEx in the OWR prefix calls `CreateNamedPipe(\\.\pipe\Demulshooter)`, Wine creates a Unix socket under `~/.steam/steam/steamapps/compatdata/<OWR_APPID>/pfx/dosdevices/.../...`. Find that socket.
3. **Write the Linux daemon (recommended: Rust or Python).**
   - Open `/dev/sinden-gun-1` (CDC ACM serial @ 9600 baud probably).
   - Read x/y/trigger frames from the gun.
   - Connect to the Wine pipe's Unix socket.
   - Send the same byte format DemulShooter's host sends.
4. **Test single-gun first**, then add second-gun support.
5. **Bonus** — wrap it in a systemd user service so it autostarts when OWR launches.

### Phase 3 — second gun and polish

- Sinden firmware supports dual guns natively at the daemon layer (we already have `sinden-gun-1` and `sinden-gun-2` symlinks). Extend the Linux host daemon to handle both pipes/streams.
- Border display on Linux is a separate sub-problem — none of the above provides a white border on a fullscreen Steam game. Options to investigate at the end:
  - Small custom always-on-top transparent window with a white frame (GTK or Qt).
  - Run OWR borderless-windowed against a desktop wallpaper that has the Sinden border baked in.
  - BepInEx plugin could draw its own border via Unity GUI inside the game.

## Open questions to answer during Phase 0

- What is OWR's Unity version? (Check `Steam/steamapps/common/Operation Wolf Returns First Mission/Operation Wolf Returns First Mission_Data/MonoBleedingEdge/` or similar.)
- IL2CPP or Mono? (Determines BepInEx variant.)

## IPC protocol — confirmed from source

Major architectural win: **the plugin talks TCP, not Windows named pipes.** This is the cleanest possible case for Linux interop — no Wine pipe bridge needed, just open a normal Linux TCP socket to localhost.

### Transport

- **Server:** the BepInEx plugin inside OWR's Unity process (binds in `DemulShooter_Plugin.cs` line ~ish: `_TcpListener = new TcpListener(IPAddress.Parse("127.0.0.1"), _TcpPort)`).
- **Address:** `127.0.0.1` (localhost only).
- **Port:** `33610`, hardcoded — not configurable via INI.
- **Direction:** plugin is the server; host is the client. Our Linux daemon connects out to 33610 after OWR starts.

### Wire format — confirmed empirically 2026-05-11

**Inputs (host → plugin): RAW PAYLOAD, NO ENVELOPE.**

The `TcpPacket` envelope (4-byte LE length + 1-byte header) is **only used for outputs (plugin → host)**. The plugin's input parser at `DemulShooter_Plugin.cs:198-204` reads bytes directly from the socket and passes them straight to `TcpInputData.Update()` without any envelope-stripping logic. The original spec in this doc was wrong — sending an envelope on inputs shifts every field by 5 bytes and ends up putting the cursor in the bottom-left corner (the `length` int32 gets read as `Axis_X[0]` ≈ 1.9e-38, etc.).

For outputs (plugin sends recoil/LED status back), the envelope IS used:
```
[ 4 bytes little-endian length=payload+1 ] [ 1 byte header=2 ] [ N bytes payload ]
```

### Inputs payload — `TcpInputData` (host → plugin)

Reflection-serialized via `TcpData.ToByteArray()` (`TcpData.cs:32-105`). Specifics:

- Fields ordered **alphabetically by name** (`OrderBy(field => field.Name)`).
- Arrays: **no length prefix on the wire**, just N raw elements where N matches the plugin's `PlayerNumber` (= `MAX_PLAYERS` = 2 for OWR).
- Endianness: little-endian via `BinaryWriter`.

Total payload for OWR (2 players): **24 bytes**. No envelope.

Field-by-field byte layout (alphabetical):

| Order | Field | Type | Bytes | Notes |
|---|-------|------|-------|-------|
| 1 | `Axis_X` | `float[2]` | 8 | Pixel-space X for each player. `0` = left edge, `Screen.width` = right edge. |
| 2 | `Axis_Y` | `float[2]` | 8 | Pixel-space Y for each player. `0` = bottom, `Screen.height` = top. |
| 3 | `ChangeWeapon` | `byte[2]` | 2 | 0/1 per player. Maps to "Action" / middle-click. |
| 4 | `EnableInputsHack` | `byte` | 1 | **MUST be 1** for our coords to be applied. If 0, plugin falls back to `Input.mousePosition` for aim. |
| 5 | `HideCrosshairs` | `byte` | 1 | 0 = show crosshair, 1 = hide. |
| 6 | `Reload` | `byte[2]` | 2 | 0/1 per player. Maps to right-click. |
| 7 | `Trigger` | `byte[2]` | 2 | 0/1 per player. Fires the weapon. |

**Coord system (verified):** pixel-space relative to the Unity Screen, NOT normalized -1..1. `mCursorMouseMouve.Mouse2DUpdate.Prefix` computes `Cursor2DPos.x = Axis_X - Screen.width/2`, then clamps to `[-Screen.width/2, +Screen.width/2]` before adding the center back. So any value outside `[0, Screen.width]` just clamps to the edge.

**Player count** is hardcoded `MAX_PLAYERS = 2` in `DemulShooter_Plugin.cs:27`. Both players' axes are read every packet regardless of game mode; sending the same coords for player 1 and player 2 makes test visuals unambiguous.

### Plugin GUID / version baseline

- `pluginGuid = "argonlefou.demulshooter.operationwolf"`
- `pluginVersion = "17.0.0.0"` (current at time of writing)
- BepInEx config file: `OperationWolf_BepInEx_DemulShooter_Plugin.ini` (configures key bindings, not the port)

## Phase 1 result (recorded)

Path 2 (Sinden joystick firmware mode) is **blocked**: both guns' USB descriptors confirm they're in mouse firmware. Joystick mode requires the Windows-only Sinden firmware updater (v2.05+ Beta), which doesn't work on Win11 — the user's only available Windows. Path 2 only reopens if a Win10 environment becomes available (real machine or VM).

## Phase 2 Step 1 result (recorded 2026-05-11)

**Confirmed:** BepInEx + the prebuilt OWR plugin DLL from DemulShooter v17.4 load cleanly inside OWR's Mono Unity 2021.3.19f1 runtime under Proton Experimental. Steam launch options:
```
WINEDLLOVERRIDES="winhttp=n,b" gamemoderun mangohud %command%
```
The plugin's TCP listener binds to `127.0.0.1:33610` (wineserver process holds the socket) and is reachable from outside the Wine prefix via standard Linux `socket.connect()`.

Plugin log evidence in `Player.log`:
```
[Message:OperationWolf_BepInEx_DemulShooter_Plugin] mScreenDuckHunt_InOutSystem.UnlockCursor()
[Message:OperationWolf_BepInEx_DemulShooter_Plugin] DemulShooter_Plugin.TcpClientThreadLoop(): TCP Client connected !
```

## Phase 2 Step 2 result (recorded 2026-05-11)

Test client at `~/workspace/sinden/owr-test-snap.py` successfully drives both player crosshairs through a corner-snap pattern. Wire format is now fully verified — see the corrected "Wire format" section above.

**Total elapsed end-to-end-working time:** ~2 hours from BepInEx install to confirmed crosshair control. The original architectural bet (TCP-over-Wine works) was correct.

## Refined Phase 2 plan — concrete enough to start coding

**Step 1 — verify BepInEx + Plugin in Proton (no daemon yet).**

- Determine OWR's Unity version. Run inside the game's Steam install folder: `find . -name 'UnityPlayer.dll' -o -name 'libil2cpp*'`. Presence of `il2cpp` data means IL2CPP build; otherwise Mono. (BepInEx flavor differs.)
- Drop BepInEx into the OWR Proton prefix at the game's install root. Standard "extract here next to the .exe" install.
- Drop the `UnityPlugin_BepInEx_OWR` build (DLL) into `BepInEx/plugins/`.
- Launch OWR via Steam with `gamemoderun mangohud %command%` left intact; check `BepInEx/LogOutput.log` for both BepInEx loaded and the OWR plugin loaded with `Listening on 127.0.0.1:33610`.
- From a Linux terminal: `ss -tlnp | grep 33610` — confirm the listener is reachable from outside the Wine prefix. If yes, we win the architectural bet.

**Step 2 — minimal Linux client that talks the protocol.**

Recommended language: **Python** for prototyping, since it has trivial TCP + struct support and no compile step. Rust later if perf matters.

Sketch:
```python
import socket, struct, time

PLAYERS = 2
def pack_inputs(x1=0.0, y1=0.0, trig1=0, x2=0.0, y2=0.0, trig2=0):
    # reflection writes: int32 array_len + N elements per array, then plain values
    buf = b''
    for arr in ([x1, x2], [y1, y2]):
        buf += struct.pack('<i', PLAYERS) + struct.pack(f'<{PLAYERS}f', *arr)
    for arr in ([trig1, trig2], [0, 0], [0, 0]):  # trigger, reload, changeweapon
        buf += struct.pack('<i', PLAYERS) + struct.pack(f'<{PLAYERS}b', *arr)
    buf += struct.pack('<BB', 0, 1)  # HideCrosshairs=0, EnableInputsHack=1
    header = bytes([1])  # Inputs
    framed = struct.pack('<i', len(buf) + 1) + header + buf
    return framed

s = socket.socket()
s.connect(('127.0.0.1', 33610))
# slowly draw a circle on screen to confirm the wire format is right
t = 0
while True:
    import math
    x = math.cos(t) * 0.5
    y = math.sin(t) * 0.5
    s.sendall(pack_inputs(x1=x, y1=y))
    t += 0.1
    time.sleep(1/60)
```

Run this with OWR's gun-mode menu visible. If the in-game crosshair starts drawing a circle, the protocol is correct.

**Step 3 — wire in the Sinden gun.**

Replace the circle generator with a reader of `/dev/sinden-gun-1`. The gun emits a small binary frame over USB serial that the Sinden daemon already parses. Two implementation options:

- **A: cohabit with the Sinden Mono daemon.** Let it keep running and tracking the screen via camera, but instead of letting the gun's HID mouse drive the cursor, read the daemon's intermediate state (it logs `X=…, Y=…` to stdout). Tap that, send to TCP.
- **B: replace the Sinden daemon entirely.** Read `/dev/sinden-gun-1` directly, do the OpenCV border tracking ourselves using the Sinden camera. Heavier lift but fully open-source and Linux-native.

Start with A — get end-to-end working first, then consider B as polish.

**Step 4 — second gun.**

`TcpInputData` arrays support N players natively. Increment `PLAYERS = 2`, feed both guns' axes/triggers.

**Step 5 — border.**

Independent of the input plumbing. Options:
- Small always-on-top transparent GTK window drawing a white rectangle frame. ~50 lines of Python with PyGObject.
- BepInEx plugin draws its own Unity GUI border inside the game (fork the existing plugin, add a Unity UI canvas with a white frame).

**Step 6 — packaging.**

- systemd user service that starts the daemon when `OperationWolfReturns.exe` appears in process list.
- Configurable INI file for calibration offsets, button mappings.

## Why this might just work

- TCP localhost is the cleanest possible IPC across Wine boundaries — Wine's TCP stack is Linux's stack. No Win32-only IPC primitives in play.
- All the OWR-specific Unity hooking is already done by the existing BepInEx plugin — we don't need to touch Unity or know OWR's internals.
- Two-gun support is baked into the protocol; we don't have to design it.
- DemulShooter is GPL/MIT-ish (need to confirm) — even if we never upstream, reading the source is fair game.

## Risks / things I'm not sure about yet

- The reflection serialization in `TcpData.ToByteArray()` might write arrays in a non-obvious order, or pad something unexpectedly. We'll know by trying the test packet and seeing if the in-game crosshair moves.
- `EnableInputsHack=1` is the field that probably toggles "let DemulShooter drive aim" — if we don't set it, the game might ignore us. Worth a focused look at the plugin's input application code.
- Some BepInEx-IL2CPP plugins have issues under Proton; if OWR is IL2CPP, we may hit Unity hooking quirks. (Unlikely though — IL2CPP+BepInEx is well-supported.)
- The plugin INI's key bindings (START, COIN, EXIT, TEST, P2_GRENADE) imply OWR also needs keyboard input for non-aim actions. We may need to emit synthetic keypresses for those, separately from the TCP stream.

## Why I think Path 1 is viable

- BepInEx is well-established in the Proton modding scene — works for Beat Saber, Lethal Company, Risk of Rain 2, dozens of Unity games people mod under Proton.
- Wine's named-pipe-to-Unix-socket bridge is mature; Wine ships a working `\\.\pipe\NAME` ↔ socket implementation that Linux processes can talk to via the file path inside the prefix.
- The plugin doing the actual Unity work means we don't need to reverse-engineer OWR's input system — the hard part is already done.
- DemulShooter's source being open means we can read the exact IPC contract instead of guessing.

The wrinkle: the IPC pipe might use Windows-specific synchronization primitives (events, mutexes) that don't translate cleanly. We'll find out when we read the source.
