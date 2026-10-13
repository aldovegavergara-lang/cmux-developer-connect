#!/usr/bin/env python3
"""Audit actual distribution files for architecture, path leaks and dependencies."""
import argparse
import json
import pathlib
import plistlib
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--app', type=pathlib.Path, required=True)
args = parser.parse_args()
app = args.app.resolve()
info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
assert info['CFBundleIdentifier'] == 'com.cmuxterm.app.debug.developer.connect'
assert info.get('LSEnvironment', {}).get('CMUX_SOCKET_PATH') == '/tmp/cmux-debug-developer-connect.sock'
magic = {b'\xce\xfa\xed\xfe', b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xce',
         b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca',
         b'\xca\xfe\xba\xbf', b'\xbf\xba\xfe\xca'}
errors = []
executables = []
private_prefix = str(pathlib.Path.home()).encode()
files = [p for p in app.rglob('*') if p.is_file() and not p.is_symlink()]
all_entries = list(app.rglob('*'))
for p in files:
    contents = p.read_bytes()
    relative = str(p.relative_to(app))
    if private_prefix in contents:
        errors.append('Build user home path: ' + relative)
    if contents[:4] not in magic:
        continue
    arch = subprocess.check_output(['/usr/bin/lipo', '-archs', str(p)], text=True).strip()
    if 'arm64' not in arch.split():
        errors.append('Missing arm64: ' + relative)
    dependencies = subprocess.check_output(['/usr/bin/otool', '-arch', 'arm64', '-L', str(p)], text=True)
    commands = subprocess.check_output(['/usr/bin/otool', '-arch', 'arm64', '-l', str(p)], text=True)
    command_rows = commands.splitlines()
    rpaths = []
    for i, row in enumerate(command_rows):
        if row.strip() == 'cmd LC_RPATH':
            rpaths.append(command_rows[i + 2].strip().removeprefix('path ').split(' (offset')[0])
    for line in dependencies.splitlines():
        if not line.startswith('\t'):
            continue
        dep = line.strip().split(' (compatibility')[0]
        if dep.startswith('/') and not dep.startswith(('/System/Library/', '/usr/lib/')):
            errors.append('External library: ' + relative + ' -> ' + dep)
        if dep.startswith('@loader_path/'):
            target = (p.parent / dep[len('@loader_path/'):]).resolve()
            if not target.exists() or app not in target.parents:
                errors.append('Missing loader dependency: ' + relative + ' -> ' + dep)
        if dep.startswith('@rpath/'):
            suffix = dep[len('@rpath/'):]
            # Framework install names traverse their Versions/Current symlinks.
            # Swift concurrency is supplied by the OS dyld shared cache; it need
            # not exist as a standalone file when /usr/lib/swift is an rpath.
            system_swift = suffix.startswith('libswift') and suffix.endswith('.dylib') and '/usr/lib/swift' in rpaths
            if not system_swift and not any(str(candidate).endswith('/' + suffix) and candidate.exists() for candidate in all_entries):
                errors.append('Missing rpath dependency: ' + relative + ' -> ' + dep)
    executables.append({'file': relative, 'architectures': arch})
for link in app.rglob('*'):
    if link.is_symlink() and (not link.exists() or app not in link.resolve().parents):
        errors.append('Nonportable symlink: ' + str(link.relative_to(app)))
subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(app)], check=True)
print(json.dumps({'files': len(files), 'mach_o_files': len(executables),
                  'errors': errors, 'architecture': 'arm64',
                  'minimum_macos': info.get('LSMinimumSystemVersion')}, indent=2))
if errors:
    raise SystemExit(1)
