# Install cmux Developer Connect

Use the prebuilt **DMG from [Releases](https://github.com/aldovegavergara-lang/cmux-developer-connect/releases/tag/developer-connect-v0.1.0-preview.1)** for Apple Silicon Macs (M1 or later). The minimum deployment target is macOS 14. It includes the sharing runtime; Xcode, Homebrew, Zig, Rust and an external Python installation are not needed.

1. Download `cmux-Developer-Connect-…-macOS-arm64.dmg`, rather than GitHub's **Source code** archives.
2. Open it and drag **cmux Developer Connect.app** to **Applications**.
3. After copying, eject the DMG and open the installed app from Applications. Keep it in the Dock if desired.
4. Install and authenticate Codex/OpenCode separately. No personal account, session or credentials are included.

This preview is **ad-hoc signed, without Developer ID or Apple notarization**. If macOS blocks first launch and you trust this download, attempt to open the installed app, then use **System Settings → Privacy & Security → Open Anyway** for this app only. See [Apple's instructions](https://support.apple.com/en-us/102445). Do not disable Gatekeeper globally or blindly remove quarantine; managed Macs may disallow this exception.

Download `SHA256SUMS.txt` alongside the DMG and run in that directory:

```sh
shasum -a 256 -c SHA256SUMS.txt
```

Expect `OK`. The checksum checks consistency with the release, not Apple certification. `release-manifest.json` records architecture, source commit, version and signing status.

Install the same preview on both Macs and follow [trusted Mac sharing](developer-peers.md). Local and remote terminals appear together, while remote processes stay on the source Mac. LAN access needs an unrestricted local network and macOS local-network permission. Internet access uses Tailscale on both Macs; do not expose router ports. Pairing invitations grant control, expire and can be revoked. Remote rendering limitations remain as documented in the README.

To update, finish or save your work, quit this app yourself and replace it in Applications using the new DMG. Download fork updates from this repository's Releases, rather than using the upstream cmux updater. To uninstall, quit and remove the app; session data, preferences and Keychain credentials are not erased automatically. Revoke unwanted peers first. Installation does not install a system service or automatically enable remote sharing.

If installation starts compiling or creates gigabytes of build files, you are using source instructions: use the DMG instead. For a launch error, check Apple Silicon, macOS version, checksum and first-launch permission. For a damaged-app warning, download again and keep the exact error instead of bypassing quarantine. The DMG's Applications link installs into `/Applications`, not `~/Applications`. Agent CLIs need their own installation. For a connection error, verify the running source Mac, matching versions, network and invitation expiry.

Developers can use the [build guide](building-developer-connect.md). Release tests run on one Mac; a second physical Mac and every supported macOS version still need validation.
