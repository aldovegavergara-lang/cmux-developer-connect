#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -m)" != arm64 ]]; then
  echo 'This distribution build targets an Apple Silicon Mac.' >&2
  exit 1
fi
export DEVELOPER_DIR="${DEVELOPER_DIR:-/Applications/Xcode.app/Contents/Developer}"
export PATH="${HOME}/.cargo/bin:/opt/homebrew/bin:${PATH}"
export CMUX_PEER_RUNTIME="${CMUX_PEER_RUNTIME:-$(python3 scripts/prepare-developer-peer-runtime.py)}"
export CMUX_DERIVED_DATA="${CMUX_DERIVED_DATA:-${HOME}/Library/Developer/Xcode/DerivedData/cmux-developer-release}"
export CMUX_RELOAD_BUILD_ARCHS=arm64
export CMUX_RELOAD_REMAP_HOME=1
export RUSTFLAGS="${RUSTFLAGS:-} --remap-path-prefix=${HOME}=/build/user"
python3 scripts/verify-local.py
CMUX_DEV_BACKEND_MODE=local CMUX_GHOSTTYKIT_PREPROVISIONED=1 \
  ./scripts/reload.sh --release --tag "${CMUX_DEVELOPER_TAG:-installer-audit}" \
  --name 'cmux Developer Installer' --no-global-cli-links --swift-frontend-workaround
