#!/usr/bin/env python3
"""Package an already built, isolated Developer app. Never touch production cmux."""
import argparse
import hashlib
import json
import pathlib
import plistlib
import re
import shutil
import subprocess

parser=argparse.ArgumentParser()
parser.add_argument('--app',required=True,type=pathlib.Path)
parser.add_argument('--output',required=True,type=pathlib.Path)
parser.add_argument('--source-commit',help='Verified source commit of this built app')
args=parser.parse_args()
source=args.app.resolve()
info=plistlib.loads((source/'Contents/Info.plist').read_bytes())
if info.get('CFBundleIdentifier')=='com.cmuxterm.app' or source==pathlib.Path('/Applications/cmux.app'):
    parser.error('Only an isolated Developer build can be packaged')
runtime=source/'Contents/Resources/peer-runtime/bin/python3'
if not runtime.exists(): parser.error('Build with CMUX_PEER_RUNTIME; the recipient must not need Homebrew')
destination=args.output.resolve()
destination.mkdir(parents=True,exist_ok=True)
app=destination/'cmux Developer Connect.app'
if app.exists(): parser.error('Output app already exists; choose a new version directory')
subprocess.run(['/usr/bin/ditto',str(source),str(app)],check=True)
if args.source_commit:
    if not re.fullmatch(r'[0-9a-f]{40}',args.source_commit): parser.error('Expected a full Git source commit')
    info['CMUXCommit']=args.source_commit[:9]
info['CFBundleIdentifier']='com.cmuxterm.app.debug.developer.connect'
info['CFBundleName']='cmux Developer Connect'
info['CFBundleDisplayName']='cmux Developer Connect'
# No source-Mac path, source identity, private key, token or invitation travels with the app.
info['LSEnvironment']={'CMUX_BUNDLE_ID':info['CFBundleIdentifier'],
    'CMUX_SOCKET_PATH':'/tmp/cmux-debug-developer-connect.sock','CMUX_DEV_BACKEND_MODE':'local'}
(app/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
resources=app/'Contents/Resources'
shutil.copyfile(pathlib.Path(__file__).resolve().parents[1]/'LICENSE',resources/'Developer-LICENSE')
shutil.copyfile(pathlib.Path(__file__).resolve().parents[1]/'config/developer-peer-runtime.json',resources/'Developer-runtime.json')
subprocess.run(['/usr/bin/codesign','--force','--deep','--sign','-',str(app)],check=True)
subprocess.run(['/usr/bin/codesign','--verify','--deep','--strict',str(app)],check=True)
instructions='''cmux Developer Connect — primera etapa entre Macs

Requisitos: Apple Silicon (M1 o posterior), macOS 14 o posterior.
No requiere Xcode, Homebrew ni Python instalado.

1. Copia «cmux Developer Connect.app» a Aplicaciones y ábrela en ambos Macs.
2. En el Mac donde corren las sesiones: Archivo → Computadores de confianza → Compartir aplicación.
3. Copia la invitación y pégala en la misma ventana del segundo Mac → Conectar.
4. Las sesiones remotas aparecen con el nombre del Mac de origen, junto a las locales.
5. Escribe desde cualquiera de los dos Macs. La terminal y sus procesos viven en el Mac de origen.

La invitación concede control de las sesiones y lectura de sus directorios de trabajo.
Vence en 3 minutos y funciona una vez. Comparte solo con tu propio Mac de confianza.
Desde el origen puedes revocar cada computador o dejar de compartir.
Desconectar una vista remota no mata sus terminales originales.
Se guardan las credenciales en el Llavero; el servidor guarda solo su hash, en una carpeta privada.

Red local: ambos Macs conectados a la misma Wi-Fi. Algunas redes de invitados aíslan dispositivos.
Si macOS pregunta por acceso a la red local, permite el acceso para esta app.
Internet: activa Tailscale en ambos Macs y elige la opción Tailscale antes de compartir.
No abras puertos del router ni uses Funnel. La conexión sigue validando TLS y la credencial.
La IP del origen debe seguir siendo la misma; si cambia, crea una invitación nueva.

Esta compilación de desarrollo tiene firma local, sin notarización de Apple.
Puede requerir autorización explícita de macOS al abrirla en otro equipo.
No reemplaza cmux instalado: tiene nombre e identidad de aplicación propios.

Primera etapa: refleja la pantalla actual del terminal y sus colores. Pegar imágenes funciona
en sesiones locales con Codex y OpenCode; la transferencia a sesiones remotas aún se rechaza.
El historial completo, las imágenes del terminal y la distribución exacta de paneles requieren
otra iteración. El explorador remoto permite lectura (archivos de hasta 2 MiB), no edición.
Seguridad v6: conexiones y tiempos acotados, validacion estricta de frames y acceso
revalidado antes de escribir. El backend movil usa un socket Unix privado, sin
contraseña en los argumentos del proceso.
El segundo Mac físico aún debe probarse; las pruebas locales usan dos instancias aisladas.
'''
(destination/'LEEME.txt').write_text(instructions)
archive=destination.parent/(destination.name+'.zip')
subprocess.run(['/usr/bin/ditto','-c','-k','--sequesterRsrc','--keepParent',str(destination),str(archive)],check=True)
digest=hashlib.sha256(archive.read_bytes()).hexdigest()
(archive.parent/(archive.name+'.sha256')).write_text(digest+'  '+archive.name+'\n')
print(json.dumps({'app':str(app),'archive':str(archive),'sha256':digest,'size_bytes':archive.stat().st_size}))
