#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
export PATH="${HOME}/.cargo/bin:/opt/homebrew/bin:${PATH}"
export CMUX_DERIVED_DATA="${CMUX_DERIVED_DATA:-${HOME}/Library/Developer/Xcode/DerivedData/cmux-developer-local}"
export CMUX_PEER_RUNTIME="${CMUX_PEER_RUNTIME:-$(python3 scripts/prepare-developer-peer-runtime.py)}"
python3 scripts/verify-local.py --swift-changed
CMUX_DEV_BACKEND_MODE=local CMUX_GHOSTTYKIT_PREPROVISIONED=1 \
  ./scripts/reload.sh --tag "${CMUX_DEVELOPER_TAG:-developer-local}" --name "${CMUX_DEVELOPER_APP_NAME:-cmux Developer}"
