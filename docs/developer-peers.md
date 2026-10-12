# Developer Connect: computadores de confianza

Esta función conecta dos instalaciones del fork y muestra las sesiones existentes
del Mac de origen junto a las sesiones locales del cliente. Ambos extremos escriben
en la misma PTY del origen; desconectar la vista no termina esa terminal.

## Compilar y empaquetar

Prepara Xcode, los submódulos y GhosttyKit según [CONTRIBUTING.md](../CONTRIBUTING.md),
con `CMUX_DEV_BACKEND_MODE=local`. Zig debe cumplir la versión que exige upstream.
`scripts/build-developer.sh` usa el tag `developer-local` y una identidad independiente.
Puedes definir `CMUX_DEVELOPER_TAG`, `CMUX_DEVELOPER_APP_NAME`, `CMUX_DERIVED_DATA`,
`CMUX_ZIG` y `CMUX_PEER_RUNTIME` para personalizar la build sin editar fuentes.

La descarga de Python está fijada en `config/developer-peer-runtime.json` y su
SHA-256 se verifica antes de extraerla. La caché predeterminada está bajo
`~/Library/Caches/cmux-developer/toolchains/`. No se incluyen configuraciones del
Mac de desarrollo. La app empaquetada contiene ese runtime y no requiere que el
receptor instale Python, Homebrew o Xcode para la conexión nativa entre Macs.

```sh
python3 scripts/package-developer-connect.py \
  --app '/ruta/a/cmux Developer.app' \
  --output '/ruta/a/paquete-developer-connect'
python3 scripts/test_developer_bundle.py \
  --app '/ruta/a/paquete-developer-connect/cmux Developer Connect.app'
```

El paquete usa la identidad `com.cmuxterm.app.debug.developer.connect`, conserva
el control local del socket para procesos de la app y elimina rutas de build del
entorno de lanzamiento. Es una firma de desarrollo local, sin notarización Apple.
El empaquetado actual se enfoca en Apple Silicon y macOS 14 o posterior.

## Conectar dos Macs

1. Abre Developer Connect en ambos Macs dentro de una LAN de confianza.
2. En el origen: Archivo → Computadores de confianza → Compartir aplicación.
3. Copia la invitación al cliente y elige Conectar en esa misma ventana.
4. Selecciona una sesión remota en la barra lateral; las locales siguen disponibles.
5. Escribe desde cualquiera de los extremos. El proceso permanece en el origen.

La invitación vence en tres minutos y sirve una vez. Compartirla concede acceso a
las terminales exportadas y lectura de sus directorios de trabajo. Desde el origen
puedes revocar un cliente o detener el servicio completo. Las credenciales del
cliente se guardan en el Llavero; el servidor guarda hashes y estado privado.

Si la IP cambia, vuelve a emparejar. Las redes de invitados pueden aislar los Macs.
Para Internet, Tailscale debe estar conectado en ambos extremos antes de compartir;
selecciona su modo en el origen. No abras puertos del router ni utilices Funnel.

## Comportamiento y límites

- La vista remota usa Ghostty nativo y refleja texto, colores y cursor de la pantalla
  actual. No replica todo el historial, imágenes inline ni el layout exacto del origen.
- El catálogo sigue las sesiones existentes. Solo se capturan pantallas visibles;
  las terminales ocultas continúan funcionando en el origen.
- Crear, renombrar, seleccionar, dividir y cerrar se ejecutan en el propietario;
  cerrar requiere confirmación en el protocolo. Un override de comando local se rechaza.
- El árbol remoto sigue el CWD del origen, con navegación y vista previa de solo
  lectura. Los archivos tienen límite de 2 MiB; no se siguen escapes por symlinks.
- La API no transfiere imágenes al origen. El pegado de imágenes permanece local.
- La entrada de texto respeta acentos; el dictado depende de la configuración de
  voz del sistema. No se empaquetan preferencias de micrófono ni idiomas personales.

## Seguridad de la conexión

HTTPS verifica el certificado exacto admitido por la invitación y mantiene la
validación de hostname. No se siguen redirecciones con tokens. Los endpoints están
limitados a IP privadas admitidas; el modo Tailscale se habilita explícitamente.
La API exporta acciones cerradas y comprueba que los objetos pertenezcan al origen.
No expone RPC arbitrario, terminal spawn con comandos ni escrituras de archivos.
La autorización del relay SSH mantiene su rechazo por defecto.

Los permisos privados, certificados y credenciales se crean al activar el servicio.
No vienen en el repositorio ni en el instalador. Las sesiones y el estado de cada
instalación permanecen fuera del árbol de fuentes.

La revisión local reprodujo y corrigió:

| Hallazgo | Corrección |
| --- | --- |
| TLS lento bloqueaba la aceptación móvil | Handshake dentro de workers, plazo y cuotas por dirección |
| Un cliente lento agotaba slots entre Macs | Cuotas por IP y plazo absoluto de lectura |
| Clave móvil aparecía en argv de ttyd | Proxy autenticado y backend Unix privado |
| Entrada pendiente tras revocar acceso | Revalidación dentro de la cola antes del RPC mutante |
| Pegado cambiaba de productor entre fragmentos | Un epoch fijo para todo el pegado |
| Geometría e historial extremos | Límites antes de materializar el frame |
| Anchura Int.max provocaba overflow | Comparación contra espacio restante sin sumar enteros |
| HTTP/JSON ambiguo | Parser estricto de cabeceras, claves y números |
| Credenciales expiradas agotaban el cupo | Purga antes de comprobar el límite |

El servicio entre Macs admite hasta 256 espacios y 512 terminales por propietario.
Las pantallas se acotan a 1024 columnas, 512 filas y 262144 celdas. Cada respuesta
HTTPS tiene límite de 4 MiB. Los procesos Python empaquetados usan `-I -B`.

No se encontró un bypass de autenticación en los casos ejecutados. Esta revisión
no certifica todos los componentes ni protege contra un dispositivo autorizado
comprometido o ataques distribuidos. Python describe su servidor HTTP básico como
no recomendado para producción pública
([documentación oficial](https://docs.python.org/3.13/library/http.server.html)).
Este prototipo se limita a LAN de confianza o Tailscale con permisos restringidos.

## Validación y rendimiento

Pasaron 22 casos del servicio entre Macs, cinco de seguridad móvil, cinco del menú
móvil y cuatro de integración CLI/tmux. También se probaron el cliente Swift TLS,
revocación durante una cola, límites del decoder y overflow, identidad del productor
al pegar, Llavero real, regeneración de recursos y firma del paquete extraído.

Once verificaciones nativas pasaron con dos apps aisladas en un Mac y seis PTY
descartables: emparejar, escribir desde ambos extremos, CWD, seleccionar una sesión
oculta, dividir, crear/renombrar/cerrar, rechazar un comando local en una proyección,
desconectar sin terminar el origen, reconectar y renovar el emparejamiento.
Falta verificar dos Macs físicos y una conexión real por Internet.

El decoder tipado evita conversiones repetidas de JSON. Para 200 frames de 45264
bytes, Swift optimizado midió 0,486 s de CPU antes y 0,301 s después: aproximadamente
38% menos solo en esa etapa. No implica igual ahorro total de app, RAM o GPU.
La compilación Debug con shells quietas mostró RSS del orden de 379–388 MiB por
instancia y auxiliares; RSS incluye páginas compartidas y no es huella física.
Las mediciones no incluyen inferencia de agentes ni una carga activa de trabajo.

Para reproducir pruebas enfocadas, usa Python 3.13 o posterior, preferentemente
el runtime empaquetado con `-I -B`:

```sh
python3 -B scripts/test_developer_peer_pentest.py
python3 -B scripts/test_developer_mobile_security.py
python3 -B scripts/test_developer_mobile_menu.py
python3 -B scripts/test_developer_peer_transport.py
python3 -B scripts/test_developer_peer_credentials.py
python3 -B scripts/test_developer_peer_frame_bounds.py --benchmark
python3 -B scripts/test_developer_peer_input_epoch.py
bash tests/test_build_app_bundled_resources.sh
python3 scripts/verify-local.py --all --swift-changed
```

`test_developer_mobile_share.py` necesita un CLI de build aislada y tmux/ttyd de
prueba. `test_developer_peer_native.py` se ejecuta desde una terminal local de un
cliente aislado, con sockets explícitos del cliente y propietario. No apuntes estas
pruebas a una instalación en uso ni a agentes o archivos personales.
