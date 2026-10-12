#!/bin/bash
set -euo pipefail
app="${CMUX_DERIVED_DATA:-${HOME}/Library/Developer/Xcode/DerivedData/cmux-developer-local}/Build/Products/Debug/cmux Developer Studio.app"
if [[ ! -d "$app" ]]; then
  echo "Compila con CMUX_DEVELOPER_TAG=developer-studio CMUX_DEVELOPER_APP_NAME='cmux Developer Studio' scripts/build-developer.sh."
  exit 1
fi
bundle_id="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$app/Contents/Info.plist")"
if [[ "$bundle_id" != "com.cmuxterm.app.debug.developer.studio" ]]; then
  echo "Este paquete no corresponde a Developer Studio."
  exit 1
fi
open "$app"
