#!/usr/bin/env python3
"""Create a portable Apple Silicon DMG from an already built isolated app."""
import argparse
import hashlib
import json
import pathlib
import plistlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO = 'https://github.com/aldovegavergara-lang/cmux-developer-connect'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--app', type=pathlib.Path, required=True)
parser.add_argument('--output', type=pathlib.Path, required=True)
parser.add_argument('--version', required=True)
parser.add_argument('--source-commit', required=True)
args = parser.parse_args()
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=True)
name = f'cmux-Developer-Connect-{args.version}-macOS-arm64.dmg'
dmg = output / name
if dmg.exists():
    parser.error('The DMG already exists; use a new output directory or version')
with tempfile.TemporaryDirectory(prefix='cmux-dmg-') as folder:
    stage = pathlib.Path(folder) / 'volume'
    subprocess.run([sys.executable, str(ROOT / 'scripts/package-developer-connect.py'),
                    '--app', str(args.app.resolve()), '--output', str(stage),
                    '--version', args.version, '--source-commit', args.source_commit,
                    '--no-archive'], check=True)
    app = stage / 'cmux Developer Connect.app'
    # A packaged app must be self-contained. Framework version links are allowed
    # only when their resolved target remains inside the app.
    for link in app.rglob('*'):
        if link.is_symlink() and (not link.exists() or app not in link.resolve().parents):
            raise SystemExit(f'Nonportable or dangling app symlink: {link.relative_to(app)}')
    subprocess.run([sys.executable, str(ROOT / 'scripts/test_developer_bundle.py'),
                    '--app', str(app)], check=True)
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    (stage / 'Applications').symlink_to('/Applications', target_is_directory=True)
    (stage / 'LEEME.txt').write_text(
        'cmux Developer Connect ' + args.version + '\n\n'
        'Mac con Apple Silicon (M1 o posterior); macOS 14 o posterior.\n'
        'Arrastra cmux Developer Connect.app a Applications y abre la copia instalada.\n'
        'No ejecutes la app desde esta imagen de disco. No requiere compilar, Xcode,\n'
        'Homebrew ni Python. Codex/OpenCode se instalan y autentican por separado.\n\n'
        'Esta preview tiene firma local; no tiene Developer ID ni notarizacion Apple.\n'
        'Si macOS bloquea la primera apertura: Ajustes del Sistema > Privacidad y\n'
        'seguridad > Abrir de todos modos. Revisa que sea esta app antes de autorizar.\n'
        'No desactives Gatekeeper ni elimines la cuarentena de forma global.\n\n'
        'Instalacion, actualizaciones y conexion entre Macs:\n' + REPO + '/blob/developer-connect/docs/installation.es.md\n\n'
        'Fuentes: ' + REPO + '/tree/' + args.source_commit + '\n'
        'Fork independiente de manaflow-ai/cmux. Incluye licencia y atribuciones.\n', encoding='utf-8')
    (stage / 'INSTALL.txt').write_text(
        'cmux Developer Connect ' + args.version + '\n\n'
        'Apple Silicon Mac; macOS 14 or later. Drag the app to Applications, then\n'
        'open the installed copy. Xcode, Homebrew and external Python are not needed.\n'
        'Codex/OpenCode need their own installation and authentication.\n\n'
        'This preview is ad-hoc signed and is NOT Apple notarized. If macOS blocks\n'
        'the first launch, inspect the app and use System Settings > Privacy &\n'
        'Security > Open Anyway. Do not disable Gatekeeper globally.\n\n'
        'Instructions: ' + REPO + '/blob/developer-connect/docs/installation.md\n'
        'Source: ' + REPO + '/tree/' + args.source_commit + '\n', encoding='utf-8')
    for document in ('LICENSE', 'THIRD_PARTY_LICENSES.md', 'FORK_NOTES.txt'):
        (stage / document).write_bytes((ROOT / document).read_bytes())
    subprocess.run(['/usr/bin/hdiutil', 'create', '-volname', 'Developer Connect',
                    '-srcfolder', str(stage), '-format', 'UDZO', '-fs', 'HFS+',
                    str(dmg)], check=True)
subprocess.run(['/usr/bin/hdiutil', 'verify', str(dmg)], check=True)
with dmg.open('rb') as stream:
    sha = hashlib.file_digest(stream, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else None
if sha is None:
    digest = hashlib.sha256()
    with dmg.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    sha = digest.hexdigest()
(output / 'SHA256SUMS.txt').write_text(sha + '  ' + name + '\n', encoding='utf-8')
manifest = {'version': args.version, 'source_commit': args.source_commit,
            'file': name, 'sha256': sha, 'size_bytes': dmg.stat().st_size,
            'architecture': 'arm64', 'minimum_macos': info.get('LSMinimumSystemVersion'),
            'bundle_identifier': info['CFBundleIdentifier'],
            'signing': 'ad-hoc', 'notarized': False, 'upstream': 'manaflow-ai/cmux'}
(output / 'release-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
