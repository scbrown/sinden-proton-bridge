#!/bin/bash
# Sinden Lightgun daemon — safe launcher.
# Reminder: do NOT start this unless a Sinden white border is already on screen and focused,
# because the gun will start hijacking your cursor as soon as the daemon runs.

set -e

if pgrep -f LightgunMono.exe >/dev/null; then
  echo "Daemon is already running. Stop it first with: $HOME/workspace/sinden/sinden-stop.sh"
  exit 1
fi

cat <<'BANNER'
================================================================
  Sinden Lightgun daemon
================================================================
  PANIC KILL options (in priority order):
    1. Press  Ctrl+Alt+Q   (global hotkey runs sinden-stop.sh)
    2. Run    ~/workspace/sinden/sinden-stop.sh
    3. Unplug the gun from USB (always works)
================================================================
  Before you continue, make sure:
    * RetroArch (or your game) is OPEN, FULLSCREEN, and FOCUSED
    * A Sinden white border is VISIBLE around the screen
BANNER

read -p "Press Enter to start the daemon (Ctrl+C to abort) ... "

sudo -n /usr/local/bin/sinden-launcher &
disown
sleep 2

if pgrep -f LightgunMono.exe >/dev/null; then
  echo "Daemon started (log: /tmp/sinden.log)."
  echo "Tailing log — Ctrl+C exits the tail but leaves the daemon running."
  echo "---"
  sudo -n tail -f /tmp/sinden.log
else
  echo "Daemon failed to start. Check /tmp/sinden.log."
  sudo -n tail -30 /tmp/sinden.log
  exit 1
fi
