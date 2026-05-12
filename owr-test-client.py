#!/usr/bin/env python3
"""
Smoke test for the DemulShooter OWR BepInEx plugin TCP protocol.

Corrected per source (UnityPlugin_BepInEx_OWR/TcpData.cs):
  - Fields are written in ALPHABETICAL order by field name (line 32: OrderBy).
  - Array elements are written WITHOUT a length prefix; plugin pre-sizes arrays.
  - Plugin allocates arrays sized to its own PlayerNumber; both sides must agree.

OWR is 2-player (plugin INI references P2_GRENADE) => PLAYERS = 2.

Alphabetical field order for TcpInputData:
  Axis_X           (float[2])  -> 8 bytes
  Axis_Y           (float[2])  -> 8 bytes
  ChangeWeapon     (byte[2])   -> 2 bytes
  EnableInputsHack (byte)      -> 1 byte
  HideCrosshairs   (byte)      -> 1 byte
  Reload           (byte[2])   -> 2 bytes
  Trigger          (byte[2])   -> 2 bytes
Total payload = 24 bytes; envelope = 4 (length) + 1 (header) + 24 = 29 bytes.

If wire format is right, in-game crosshair (player 1) traces a slow circle.

Usage:  owr-test-client.py [amplitude]   # default 0.5
Ctrl+C to stop.
"""
import socket, struct, time, math, sys

HOST, PORT = "127.0.0.1", 33610
PLAYERS = 2

def frame(x1, y1, trig1=0, reload1=0, change1=0,
          x2=0.0, y2=0.0, trig2=0, reload2=0, change2=0,
          enable_hack=1, hide_crosshairs=0):
    # Alphabetical: Axis_X, Axis_Y, ChangeWeapon, EnableInputsHack,
    #               HideCrosshairs, Reload, Trigger
    payload  = struct.pack("<ff", x1, x2)               # Axis_X[2]
    payload += struct.pack("<ff", y1, y2)               # Axis_Y[2]
    payload += struct.pack("<BB", change1, change2)     # ChangeWeapon[2]
    payload += struct.pack("<B",  enable_hack)          # EnableInputsHack
    payload += struct.pack("<B",  hide_crosshairs)      # HideCrosshairs
    payload += struct.pack("<BB", reload1, reload2)     # Reload[2]
    payload += struct.pack("<BB", trig1, trig2)         # Trigger[2]
    return struct.pack("<i", len(payload) + 1) + bytes([1]) + payload

def main():
    amplitude = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
    print(f"connect {HOST}:{PORT}  players={PLAYERS}  amplitude={amplitude}", file=sys.stderr)
    s = socket.socket()
    s.connect((HOST, PORT))
    t = 0.0
    try:
        while True:
            x = math.cos(t) * amplitude
            y = math.sin(t) * amplitude
            s.sendall(frame(x, y))
            t += 0.05
            time.sleep(1/60)
    except KeyboardInterrupt:
        pass
    finally:
        s.close()

if __name__ == "__main__":
    main()
