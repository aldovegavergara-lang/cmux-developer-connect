#!/bin/bash
set -euo pipefail
app="${CMUX_DERIVED_DATA:-${HOME}/Library/Developer/Xcode/DerivedData/cmux-developer-local}/Build/Products/Debug/cmux Developer.app"
if [[ ! -d "$app" ]]; then
  echo "Primero compila el fork con scripts/build-developer.sh."
  exit 1
fi
bundle_id="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$app/Contents/Info.plist")"
if [[ "$bundle_id" != "com.cmuxterm.app.debug.developer.local" ]]; then
  echo "El identificador de esta aplicación no corresponde al fork Developer."
  exit 1
fi
open "$app"
