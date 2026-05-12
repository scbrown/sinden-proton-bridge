#!/bin/bash
# Build the SindenBorder BepInEx plugin DLL and drop it into the OWR plugins dir.
set -euo pipefail

GAME_DIR="/home/braino/.local/share/Steam/steamapps/common/Operation Wolf"
MANAGED="$GAME_DIR/OperationWolf_Data/Managed"
BEPINEX_CORE="$GAME_DIR/BepInEx/core"
PLUGINS_DIR="$GAME_DIR/BepInEx/plugins"

cd "$(dirname "$0")"

mcs -target:library -nologo -warn:0 -optimize \
    -r:"$BEPINEX_CORE/BepInEx.dll" \
    -r:"$BEPINEX_CORE/BepInEx.Harmony.dll" \
    -r:"$BEPINEX_CORE/0Harmony.dll" \
    -r:"$MANAGED/UnityEngine.dll" \
    -r:"$MANAGED/UnityEngine.CoreModule.dll" \
    -r:"$MANAGED/UnityEngine.IMGUIModule.dll" \
    -out:SindenBorder.dll \
    SindenBorder.cs

echo "built: $(pwd)/SindenBorder.dll"
cp SindenBorder.dll "$PLUGINS_DIR/"
echo "installed to: $PLUGINS_DIR/SindenBorder.dll"
ls -lh "$PLUGINS_DIR/SindenBorder.dll"
