# Build and package the fork

To **use** the app, [install the DMG](installation.md). Building is for source changes: native dependencies and caches take multiple GB, which are not installation files.

Use a full Xcode installation with Metal, Python 3, Rust/Cargo and `rustup`, Go for Release builds, and Zig matching `ghostty/build.zig.zon` (this base requires **0.16.x**, at least 0.16.0). Upstream pins Xcode 26; this preview is verified with Xcode 27. Complete Xcode's first-run components/license. See [CONTRIBUTING](../CONTRIBUTING.md) for prerequisite setup.

```sh
git clone --branch developer-connect --single-branch --recursive \
  https://github.com/aldovegavergara-lang/cmux-developer-connect.git
cd cmux-developer-connect
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export PATH="$HOME/.cargo/bin:/opt/homebrew/bin:$PATH"
zig version
xcrun metal --version
./scripts/setup.sh
export CMUX_DERIVED_DATA="$HOME/Library/Developer/Xcode/DerivedData/cmux-developer-local"
./scripts/build-developer.sh
```

If Metal is missing, run `xcodebuild -downloadComponent MetalToolchain` with the intended Xcode selected. A custom Zig directory must be on `PATH` for setup; `CMUX_ZIG` only configures build phases supporting an explicit executable. Setup obtains checksum-pinned prebuilt GhosttyKit. The developer script downloads pinned Python to `~/Library/Caches/cmux-developer/toolchains/`, builds an isolated app and prints its location without launching it. Reuse the same tag and DerivedData directory; do not run simultaneous builds against it.

For an optimized distribution, after preparing Go and the other tools:

```sh
export CMUX_PEER_RUNTIME="$(python3 scripts/prepare-developer-peer-runtime.py)"
CMUX_DEV_BACKEND_MODE=local CMUX_GHOSTTYKIT_PREPROVISIONED=1 \
  ./scripts/reload.sh --release --tag installer-audit \
  --name 'cmux Developer Installer' --no-global-cli-links
```

Verify the build succeeded and the source/submodules are clean (`git status --short`; `git submodule status`). Use the printed **App path**, replacing the placeholder below:

```sh
python3 scripts/make-developer-dmg.py \
  --app '/printed/path/cmux Developer Installer.app' \
  --output "$HOME/Desktop/Developer-Connect-release" \
  --version 0.1.0-preview.1 \
  --source-commit "$(git rev-parse HEAD)"
```

Packaging does not compile or establish source provenance; verify the input app corresponds to the named commit. It repairs relative CLI resource links, verifies the signature and bundled Python, rejects nonportable app symlinks, and creates a DMG, `SHA256SUMS.txt` and `release-manifest.json`. Ad-hoc signing is not notarization; Developer ID and Apple account credentials are a separate distribution prerequisite and never belong in sources or packages.

Keep build caches to make subsequent builds faster. To recover disk space, stop your builds and remove only your chosen fork DerivedData directory through Finder. Do not remove active apps, sessions or Keychain entries. A missing Metal toolchain requires the selected Xcode component; an incompatible Zig requires the manifest's version series. For the known GlobalISel Swift compiler failure, rerun the tagged build with `--swift-frontend-workaround`, as used for this preview. Keep the log path printed by `reload.sh` for other failures.
