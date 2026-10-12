#!/bin/bash
set -euo pipefail
app="${CMUX_DERIVED_DATA:-${HOME}/Library/Developer/Xcode/DerivedData/cmux-developer-local}/Build/Products/Debug/cmux Developer Mobile.app"
if [[ ! -d "$app" ]]; then
  echo "Primero compila la variante Mobile con scripts/build-developer.sh."
  exit 1
fi
bundle_id="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$app/Contents/Info.plist")"
if [[ "$bundle_id" != "com.cmuxterm.app.debug.developer.mobile" ]]; then
  echo "El identificador no corresponde al fork Developer Mobile."
  exit 1
fi
open "$app"
