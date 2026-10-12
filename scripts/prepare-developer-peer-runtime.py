#!/usr/bin/env python3
"""Fetch the pinned, relocatable Python used only by the app-owned sharing service."""
import hashlib
import json
import pathlib
import platform
import tarfile
import urllib.request

root=pathlib.Path(__file__).resolve().parents[1]
manifest=json.loads((root/'config/developer-peer-runtime.json').read_text())
if platform.machine() not in ('arm64','aarch64'):
    raise SystemExit('This runtime manifest targets Apple Silicon; use an Intel manifest before packaging for Intel.')
cache=pathlib.Path.home()/'Library/Caches/cmux-developer/toolchains'/('peer-python-'+manifest['version']+'-arm64')
cache.mkdir(parents=True,exist_ok=True)
archive=cache/'runtime.tar.gz'
if not archive.exists():
    temporary=cache/'runtime.download'
    with urllib.request.urlopen(manifest['url'],timeout=60) as response,temporary.open('wb') as output:
        while True:
            block=response.read(1024*1024)
            if not block: break
            output.write(block)
    temporary.replace(archive)
if hashlib.sha256(archive.read_bytes()).hexdigest()!=manifest['sha256']:
    raise SystemExit('Runtime checksum mismatch; nothing was extracted.')
runtime=cache/'python'
if not (runtime/'bin/python3').exists():
    with tarfile.open(archive) as bundle:
        if hasattr(tarfile,'data_filter'):
            bundle.extractall(cache,filter='data')
        else:
            # Compatible with the build Mac's system Python 3.9; constrain all
            # archive entries and relative symlink targets before extraction.
            for item in bundle.getmembers():
                target=(cache/item.name).resolve()
                if cache.resolve() not in target.parents: raise SystemExit('Unsafe runtime archive path')
                if item.issym() or item.islnk():
                    link=((target.parent if item.issym() else cache)/item.linkname).resolve()
                    if cache.resolve() not in link.parents: raise SystemExit('Unsafe runtime archive link')
                elif not (item.isdir() or item.isfile()): raise SystemExit('Unsupported runtime archive entry')
            bundle.extractall(cache)
print(runtime)
