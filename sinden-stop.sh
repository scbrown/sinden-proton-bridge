#!/bin/bash
# Kills the Sinden Lightgun daemon. Safe to bind to a global hotkey.
sudo -n pkill -f LightgunMono.exe 2>/dev/null
if [ $? -eq 0 ]; then
  msg="Daemon stopped"
else
  msg="Daemon was not running"
fi
echo "Sinden: $msg"
notify-send -i input-gaming "Sinden" "$msg" 2>/dev/null || true
