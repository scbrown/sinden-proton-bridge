#!/usr/bin/env python3
"""
OWR Sinden bridge daemon.

Reads gun position + buttons from one or two Sinden gun HID-mouse evdev
devices, maps the gun's absolute coords (0..32767) into the OWR game-
window coord space, and pushes them to the BepInEx plugin via TCP at
127.0.0.1:33610.

The bridge "grabs" each gun's evdev device so the gun's HID mouse events
do NOT also reach the desktop input layer — preventing the OS cursor
from being hijacked by gun aim.

Calibration model (tuneable per gun):
    game_x = clamp(0..window_w, (gun_x - x_min) / (x_max - x_min) * window_w)
    game_y = clamp(0..window_h, flip(gun_y - y_min) / (y_max - y_min) * window_h)

Defaults assume:
    - gun reports 0..32767 across the entire 4K desktop
    - OWR window at (window_x, window_y) size (window_w, window_h)
    - daemon's coord space = full desktop, so the OWR window covers only
      a sub-range of (0..32767) on each axis
"""
import argparse, select, socket, struct, threading, time, sys, math
from evdev import InputDevice, ecodes

PORT = 33610
ABS_MAX = 32767

# Outputs (plugin → host) frame layout. Envelope is 4-byte LE length +
# 1-byte header (=2 for Outputs), then the payload. Payload fields are
# serialized in alphabetical order by name (same reflection rule as inputs).
# For OWR (2 players): Ammo(int[2]) + Damaged(byte[2]) + IsPlaying(byte[2]) +
# Life(byte[2]) + Recoil(byte[2]) = 16 bytes.
OUTPUT_HEADER_INPUTS  = 1
OUTPUT_HEADER_OUTPUTS = 2
OUTPUT_PAYLOAD_LEN = 16  # 2 players

class GunState:
    __slots__ = ("x", "y", "trigger", "reload", "weapon", "last_event_ts")
    def __init__(self):
        self.x = 0
        self.y = 0
        self.trigger = 0
        self.reload  = 0
        self.weapon  = 0
        self.last_event_ts = 0.0

class GameOutputs:
    """Game-state events sent BACK from the BepInEx plugin."""
    __slots__ = ("ammo", "damaged", "is_playing", "life", "recoil", "last_ts")
    def __init__(self, players=2):
        self.ammo       = [0] * players
        self.damaged    = [0] * players  # one-frame pulse on damage
        self.is_playing = [0] * players
        self.life       = [0] * players
        self.recoil     = [0] * players  # one-frame pulse on weapon fire
        self.last_ts    = 0.0

def parse_output_frames(buf, outputs):
    """
    Consume as many complete output frames from `buf` as possible, mutate
    `outputs` for each one parsed, and return whatever bytes are left over
    (a partial frame at the tail of buf).
    """
    while len(buf) >= 5:
        # Length field counts the header byte (length = payload_len + 1).
        length = struct.unpack_from("<i", buf, 0)[0]
        if length < 1 or length > 4096:
            # Stream desync — bail and reset; the next frame might be unrecoverable.
            return b""
        if len(buf) < 4 + length:
            break  # incomplete frame, wait for more bytes
        header = buf[4]
        payload = buf[5:4 + length]
        if header == OUTPUT_HEADER_OUTPUTS and len(payload) == OUTPUT_PAYLOAD_LEN:
            # Alphabetical: Ammo[2] (int32), Damaged[2], IsPlaying[2], Life[2], Recoil[2]
            ammo       = list(struct.unpack_from("<2i", payload, 0))
            damaged    = list(struct.unpack_from("<2B", payload, 8))
            is_playing = list(struct.unpack_from("<2B", payload, 10))
            life       = list(struct.unpack_from("<2B", payload, 12))
            recoil     = list(struct.unpack_from("<2B", payload, 14))
            outputs.ammo       = ammo
            outputs.damaged    = damaged
            outputs.is_playing = is_playing
            outputs.life       = life
            outputs.recoil     = recoil
            outputs.last_ts    = time.time()
        buf = buf[4 + length:]
    return buf

def make_payload(x1, y1, trig1, reload1, weapon1,
                 x2=0.0, y2=0.0, trig2=0, reload2=0, weapon2=0,
                 enable_hack=1, hide_crosshairs=0):
    # Alphabetical field order, no envelope, 24 bytes.
    payload  = struct.pack("<ff", x1, x2)
    payload += struct.pack("<ff", y1, y2)
    payload += struct.pack("<BB", weapon1, weapon2)
    payload += struct.pack("<B",  enable_hack)
    payload += struct.pack("<B",  hide_crosshairs)
    payload += struct.pack("<BB", reload1, reload2)
    payload += struct.pack("<BB", trig1, trig2)
    return payload

def reader_thread(dev_path, state, stop_evt, debug, grab):
    while not stop_evt.is_set():
        try:
            dev = InputDevice(dev_path)
            if grab:
                dev.grab()
                print(f"[reader] {dev_path}: GRABBED {dev.name!r}", file=sys.stderr)
            else:
                print(f"[reader] {dev_path}: {dev.name!r} opened (no grab)", file=sys.stderr)
            for ev in dev.read_loop():
                if stop_evt.is_set():
                    break
                if ev.type == ecodes.EV_ABS:
                    if ev.code == ecodes.ABS_X:
                        state.x = ev.value
                    elif ev.code == ecodes.ABS_Y:
                        state.y = ev.value
                    state.last_event_ts = time.time()
                elif ev.type == ecodes.EV_KEY:
                    val = 1 if ev.value else 0
                    if ev.code == ecodes.BTN_LEFT:
                        state.trigger = val
                    elif ev.code == ecodes.BTN_RIGHT:
                        state.reload = val
                    elif ev.code == ecodes.BTN_MIDDLE:
                        state.weapon = val
        except OSError as e:
            print(f"[reader] {dev_path}: {e}; retrying in 1s", file=sys.stderr)
            time.sleep(1)

def map_to_window(gun_x, gun_y, args):
    """Map gun (0..32767) to OWR window (0..window_w / 0..window_h)."""
    x_span = max(1, args.x_max - args.x_min)
    y_span = max(1, args.y_max - args.y_min)
    nx = (gun_x - args.x_min) / x_span         # 0..1
    ny = (gun_y - args.y_min) / y_span         # 0..1
    if args.y_flip:
        ny = 1.0 - ny
    win_x = nx * args.window_w
    win_y = ny * args.window_h
    win_x = max(0.0, min(args.window_w, win_x))
    win_y = max(0.0, min(args.window_h, win_y))
    return win_x, win_y

def sender(state1, state2, outputs, args, stop_evt):
    s = socket.socket()
    while not stop_evt.is_set():
        try:
            s.connect(("127.0.0.1", PORT))
            print(f"[sender] connected to plugin on 127.0.0.1:{PORT}", file=sys.stderr)
            break
        except OSError as e:
            print(f"[sender] waiting for plugin: {e}", file=sys.stderr)
            time.sleep(2)
    interval = 1.0 / args.rate
    last_log = 0.0
    # EMA smoothing state
    sx1, sy1 = 0.0, 0.0
    sx2, sy2 = 0.0, 0.0
    alpha = max(0.0, min(1.0, args.smooth))
    reject_count = 0
    reject_streak1 = 0
    reject_streak2 = 0
    # Output stream parsing state
    recv_buf = b""
    # Track per-player edges so we log a one-line event on each fire/damage.
    last_recoil  = [0, 0]
    last_damaged = [0, 0]
    last_life    = list(outputs.life)
    last_ammo    = list(outputs.ammo)

    while not stop_evt.is_set():
        wx1, wy1 = map_to_window(state1.x, state1.y, args)
        if state2 is not None:
            wx2, wy2 = map_to_window(state2.x, state2.y, args)
        else:
            wx2, wy2 = 0.0, 0.0

        # Outlier rejection. Reject single-frame OpenCV spikes but accept
        # sustained position changes — if we've been rejecting for
        # max_reject_frames in a row, treat the new position as intentional
        # fast motion and accept it.
        if args.max_jump > 0:
            d1 = math.hypot(wx1 - sx1, wy1 - sy1)
            if d1 > args.max_jump and reject_streak1 < args.max_reject_frames:
                reject_count += 1
                reject_streak1 += 1
                wx1, wy1 = sx1, sy1
            else:
                reject_streak1 = 0
            d2 = math.hypot(wx2 - sx2, wy2 - sy2)
            if d2 > args.max_jump and reject_streak2 < args.max_reject_frames:
                reject_streak2 += 1
                wx2, wy2 = sx2, sy2
            else:
                reject_streak2 = 0

        # Exponential moving average: small alpha = heavy smoothing.
        sx1 = alpha * wx1 + (1 - alpha) * sx1
        sy1 = alpha * wy1 + (1 - alpha) * sy1
        sx2 = alpha * wx2 + (1 - alpha) * sx2
        sy2 = alpha * wy2 + (1 - alpha) * sy2

        try:
            s.sendall(make_payload(sx1, sy1,
                                   state1.trigger, state1.reload, state1.weapon,
                                   sx2, sy2,
                                   state2.trigger if state2 else 0,
                                   state2.reload  if state2 else 0,
                                   state2.weapon  if state2 else 0))
        except OSError as e:
            print(f"[sender] send failed: {e}; reconnecting", file=sys.stderr)
            try: s.close()
            except: pass
            s = socket.socket()
            recv_buf = b""
            while not stop_evt.is_set():
                try:
                    s.connect(("127.0.0.1", PORT)); break
                except OSError:
                    time.sleep(2)

        # Non-blocking peek for output frames coming back on the same socket.
        try:
            readable, _, _ = select.select([s], [], [], 0)
            if readable:
                chunk = s.recv(4096)
                if chunk:
                    recv_buf += chunk
                    recv_buf = parse_output_frames(recv_buf, outputs)
        except OSError:
            pass

        # Log game-event edges (one line per Recoil↑ / Damaged↑ / Life change /
        # Ammo change). Cheap, only fires when something actually happened.
        for i in (0, 1):
            if outputs.recoil[i] and not last_recoil[i]:
                print(f"[game] P{i+1} RECOIL fired", file=sys.stderr)
            if outputs.damaged[i] and not last_damaged[i]:
                print(f"[game] P{i+1} DAMAGED hp={outputs.life[i]}", file=sys.stderr)
            if outputs.life[i] != last_life[i]:
                print(f"[game] P{i+1} life {last_life[i]} → {outputs.life[i]}", file=sys.stderr)
            if outputs.ammo[i] != last_ammo[i]:
                print(f"[game] P{i+1} ammo {last_ammo[i]} → {outputs.ammo[i]}", file=sys.stderr)
        last_recoil  = list(outputs.recoil)
        last_damaged = list(outputs.damaged)
        last_life    = list(outputs.life)
        last_ammo    = list(outputs.ammo)

        now = time.time()
        if args.debug and now - last_log > 1.0:
            last_log = now
            age1 = now - state1.last_event_ts
            line = (f"[sender] g1=({state1.x:5},{state1.y:5})→({sx1:4.0f},{sy1:4.0f}) "
                    f"t={state1.trigger} r={state1.reload} w={state1.weapon} "
                    f"age={age1:.1f}s")
            if state2 is not None:
                age2 = now - state2.last_event_ts
                line += (f" | g2=({state2.x:5},{state2.y:5})→({sx2:4.0f},{sy2:4.0f}) "
                         f"t={state2.trigger} r={state2.reload} w={state2.weapon} "
                         f"age={age2:.1f}s")
            line += f" rej={reject_count}"
            print(line, file=sys.stderr)
            reject_count = 0
        time.sleep(interval)
    s.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gun",  default="/dev/input/event24",
                    help="Player 1 gun evdev path")
    ap.add_argument("--gun2", default="/dev/input/event26",
                    help="Player 2 gun evdev path (or 'none' to disable)")
    ap.add_argument("--rate", type=float, default=60.0, help="TCP send rate Hz")
    ap.add_argument("--window-w", type=float, default=1920.0,
                    help="OWR game window width (pixels)")
    ap.add_argument("--window-h", type=float, default=1080.0,
                    help="OWR game window height (pixels)")

    # Empirical calibration: the gun ABS range that maps to (0..window_w,
    # 0..window_h). Defaults assume gun spans the full 4K desktop, OWR window
    # is at desktop (1831, 591) size 1920x1080.
    # On the 4K desktop the OWR window occupies:
    #   X: 1831..3751  →  in gun ABS: 1831*32767/3840 .. 3751*32767/3840
    #                  ≈ 15622..32014
    #   Y: 591..1671   →  in gun ABS:  591*32767/2160 .. 1671*32767/2160
    #                  ≈  8966..25344
    ap.add_argument("--x-min", type=float, default=15622.0)
    ap.add_argument("--x-max", type=float, default=32014.0)
    ap.add_argument("--y-min", type=float, default=8966.0)
    ap.add_argument("--y-max", type=float, default=25344.0)
    ap.add_argument("--y-flip", action="store_true", default=True,
                    help="Flip Y axis (default on; HID Y=top, plugin Y=bottom)")
    ap.add_argument("--no-y-flip", dest="y_flip", action="store_false")
    ap.add_argument("--smooth", type=float, default=0.5,
                    help="EMA smoothing factor 0..1 (1=raw, 0.1=heavy smooth)")
    ap.add_argument("--max-jump", type=float, default=250.0,
                    help="Reject samples that jump more than this many game-window "
                         "pixels from the current filtered position. 0 to disable.")
    ap.add_argument("--max-reject-frames", type=int, default=6,
                    help="After this many consecutive rejected frames, accept "
                         "the new position (assume the move was intentional).")

    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--no-grab", action="store_true",
                    help="Don't exclusively grab gun devices.")
    args = ap.parse_args()

    state1 = GunState()
    state2 = GunState() if args.gun2 != "none" else None
    outputs = GameOutputs(players=2)
    stop = threading.Event()
    grab = not args.no_grab

    t1 = threading.Thread(target=reader_thread,
                          args=(args.gun, state1, stop, args.debug, grab),
                          daemon=True)
    t1.start()
    if state2 is not None:
        t2 = threading.Thread(target=reader_thread,
                              args=(args.gun2, state2, stop, args.debug, grab),
                              daemon=True)
        t2.start()
    try:
        sender(state1, state2, outputs, args, stop)
    except KeyboardInterrupt:
        stop.set()

if __name__ == "__main__":
    main()
