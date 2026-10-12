# cmux Developer Connect

**Fork independiente de [manaflow-ai/cmux](https://github.com/manaflow-ai/cmux)**
para terminales nativas de macOS, agentes en paralelo y sesiones remotas de confianza.
No es una versión oficial de Manaflow. Base upstream:
[`b7d8dee8c07`](https://github.com/manaflow-ai/cmux/commit/b7d8dee8c07eb96507a399f1b13f5fce34ac3eeb).

[English](README.md) · [Documentación original](README.upstream.md)

## Cambios de este fork

- Oculta y bloquea el login de cmux y las funciones Cloud/Pro que dependen de esa
  cuenta. Codex, OpenCode y otros CLI mantienen su autenticación propia.
- Desactiva los espacios de navegador integrado; los enlaces web de la terminal
  se abren en Chrome si está disponible. WebKit se conserva para vistas de archivos.
- Incluye un árbol de archivos del directorio actual de la terminal seleccionada.
- Mezcla sesiones locales con terminales existentes de otro Mac. Ambos extremos
  controlan la misma PTY mediante HTTPS optativo y un certificado fijado al emparejar.
- Añade un puente para Android/navegador con menú de sesiones, Tailscale opcional,
  autenticación, vencimiento y un backend de terminal mediante socket Unix privado.
- Acota conexiones, tiempos, respuestas y geometría; revalida el acceso antes de
  escribir y conserva la identidad del proceso durante un pegado fragmentado.

## Compilación y uso

El empaquetado actual se enfoca en Apple Silicon. Sigue [CONTRIBUTING.md](CONTRIBUTING.md)
para preparar Xcode, submódulos y GhosttyKit con `CMUX_DEV_BACKEND_MODE=local`.
Instala la versión de Zig que exige upstream y agrégala a `PATH`, o define `CMUX_ZIG`.
Después ejecuta `scripts/build-developer.sh`. La build usa por defecto el tag
`developer-local` y una identidad distinta a cmux instalado. El runtime Python se
fija por versión y checksum y se guarda en una caché local.

[Conexión entre Macs](docs/developer-peers.md) ·
[Acceso móvil](docs/developer-mobile.md) · [Notas del fork](FORK_NOTES.txt)

## Límites y validación

La vista remota refleja la pantalla actual; todavía no incluye todo el historial,
las imágenes inline ni la distribución exacta de paneles del origen. Los archivos
remotos son de solo lectura. Pegar imágenes funciona localmente con agentes
compatibles; la transferencia de imágenes al origen no está implementada.

Pasaron las pruebas de seguridad enfocadas y 11 verificaciones nativas con dos apps
aisladas en un Mac. Falta probar dos Macs físicos e Internet real. La mejora de 38%
en CPU corresponde solo a decodificar pantallas, no al consumo total de la app.
Es un prototipo para LAN de confianza o Tailscale restringido. Los paquetes de
prueba tienen firma local y no están notarizados por Apple.

## Origen y licencias

Se conservan autores, historial upstream y atribución de dependencias. La app y
estos cambios siguen [LICENSE](LICENSE), generalmente GPL-3.0-or-later. Los
servidores que esa licencia enumera tienen condiciones BUSL-1.1 propias. Consulta
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md). El fork no cambia esas licencias.

La publicación excluye configuración de equipos, credenciales, exportaciones de
sesiones y evidencias personales, también en el historial de commits agregado.
