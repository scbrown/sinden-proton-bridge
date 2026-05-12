#!/usr/bin/env python3
"""
Looping snap-positions test for the DemulShooter OWR plugin.

Coordinate system (confirmed from mCursorMouseMouve.cs Prefix patch):
  Axis_X / Axis_Y are PIXEL-SPACE coordinates.
  (0, 0) is the bottom-left of the game window.
  Plugin computes: cursor.x = AxisX - Screen.width / 2

Usage:
  owr-test-snap.py [screen_width] [screen_height]
  Defaults to 3840 x 2160 (4K).
"""
import socket, struct, time, sys

HOST, PORT = "127.0.0.1", 33610
HOLD_SEC = 3.0

def frame(x, y):
    # NOTE: plugin reads raw bytes from socket and passes them straight to
    # TcpInputData.Update() — there is NO 4-byte-length + 1-byte-header
    # envelope on inputs. The envelope is only used for outputs (plugin->host).
    payload  = struct.pack("<ff", x, x)                 # Axis_X (both players)
    payload += struct.pack("<ff", y, y)                 # Axis_Y (both players)
    payload += struct.pack("<BB", 0, 0)                 # ChangeWeapon
    payload += struct.pack("<B",  1)                    # EnableInputsHack=1
    payload += struct.pack("<B",  0)                    # HideCrosshairs
    payload += struct.pack("<BB", 0, 0)                 # Reload
    payload += struct.pack("<BB", 0, 0)                 # Trigger
    return payload

def hold(s, x, y, label, seconds=HOLD_SEC):
    print(f"  hold {label:14} x={x:6.0f}  y={y:6.0f}", file=sys.stderr, flush=True)
    end = time.time() + seconds
    while time.time() < end:
        s.sendall(frame(x, y))
        time.sleep(1/60)

def main():
    w = float(sys.argv[1]) if len(sys.argv) > 1 else 1920.0
    h = float(sys.argv[2]) if len(sys.argv) > 2 else 1080.0
    print(f"connect {HOST}:{PORT}  screen=({w:.0f}x{h:.0f})  hold={HOLD_SEC}s", file=sys.stderr)
    s = socket.socket()
    s.connect((HOST, PORT))
    try:
        while True:
            hold(s, 0.8*w, 0.8*h, "top-right")
            hold(s, 0.2*w, 0.8*h, "top-left")
            hold(s, 0.2*w, 0.2*h, "bottom-left")
            hold(s, 0.8*w, 0.2*h, "bottom-right")
            hold(s, 0.5*w, 0.5*h, "center")
    except KeyboardInterrupt:
        pass
    finally:
        s.close()

if __name__ == "__main__":
    main()
