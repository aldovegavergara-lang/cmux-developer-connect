# cmux Developer Connect

An independent **fork of [manaflow-ai/cmux](https://github.com/manaflow-ai/cmux)**
for native macOS terminals, parallel coding agents and trusted remote sessions.
It is not an official Manaflow release. Upstream base:
[`b7d8dee8c07`](https://github.com/manaflow-ai/cmux/commit/b7d8dee8c07eb96507a399f1b13f5fce34ac3eeb).

[Español](README.es.md) · [Upstream documentation](README.upstream.md)

## What this fork changes

- Hides and blocks cmux account sign-in and account-dependent Cloud/Pro features.
  Codex, OpenCode and other CLI tools keep their own authentication.
- Disables embedded browser workspaces; terminal web links open in Chrome when
  available. WebKit components used for file previews remain in the source.
- Provides a native file tree for the selected terminal's current directory.
- Mixes local workspaces with existing terminal sessions shared by another Mac.
  Both ends control the same owner PTY through an opt-in, pinned HTTPS connection.
- Includes an Android/browser bridge with a session menu, optional Tailscale,
  authentication, expiry and a private Unix-socket terminal backend.
- Bounds remote connections, request time, response size and terminal geometry;
  rechecks access before queued mutations and preserves the producer during paste.

## Build and use

Apple Silicon is the current packaging target. Follow [CONTRIBUTING.md](CONTRIBUTING.md)
for Xcode, submodules and GhosttyKit setup, using `CMUX_DEV_BACKEND_MODE=local`.
Install the Zig version required by upstream and put it on `PATH`, or set `CMUX_ZIG`.
Then run `scripts/build-developer.sh`. The default build is tagged `developer-local`
and uses a separate app identity; it does not replace the production cmux install.
The Python sharing runtime is pinned by version and checksum and cached locally.

[Mac-to-Mac sharing](docs/developer-peers.md) ·
[Mobile sharing](docs/developer-mobile.md) · [Fork notes](FORK_NOTES.txt)

## Current limits and validation

Remote views mirror the current terminal screen, not complete scrollback, inline
images or the owner's exact pane layout. Remote files are read-only. Image paste
works locally with compatible agents; remote image upload is not implemented.

Focused security tests and 11 native session checks passed using two isolated apps
on one Mac. A second physical Mac and a real Internet connection still need testing.
The 38% CPU improvement measured frame decoding only, not total application usage.
This is a private-network prototype; use a trusted LAN or restricted Tailscale access.
Development packages use a local signature and are not Apple-notarized releases.

## Attribution and licenses

Copyright notices, upstream history and dependency attribution are preserved.
The desktop app and these modifications follow [LICENSE](LICENSE), generally
GPL-3.0-or-later. The server directories explicitly listed there have their own
BUSL-1.1 terms. See [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) for dependencies.
The fork does not change those licenses or claim ownership of upstream work.

Machine-specific configuration, credentials, session exports and personal audit
artifacts are excluded from the published source and its added commit history.
