#!/usr/bin/env python3
"""Check the actual signed package, its source resources and isolated Python imports."""
import argparse
import pathlib
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--app', required=True, type=pathlib.Path)
args = parser.parse_args()
root = pathlib.Path(__file__).resolve().parents[1]
app = args.app.resolve()
resources = app / 'Contents/Resources'
files = ['cmux-mobile-share', 'cmux-mobile-menu.py', 'cmux-mobile-menu.html',
         'cmux-peer-service.py', 'peer/policy.py', 'peer/http_limits.py']
for name in files:
    assert (root / 'Resources/bin' / name).read_bytes() == (resources / 'bin' / name).read_bytes(), name
subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
subprocess.run([str(resources / 'peer-runtime/bin/python3'), '-I', '-B', '-c',
    "import pathlib,runpy,sys; p=pathlib.Path(sys.argv[1]); "
    "[runpy.run_path(str(p/n),run_name='bundle_import_test') for n in "
    "['cmux-peer-service.py','cmux-mobile-menu.py','cmux-mobile-share']]; "
    "print('Isolated bundled Python imports passed')", str(resources / 'bin')], check=True)
subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
print('Bundled resources match source; signature valid before and after imports')
