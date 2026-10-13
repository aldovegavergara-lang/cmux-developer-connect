# Instalar cmux Developer Connect

La descarga recomendada es el **DMG de [Releases](https://github.com/aldovegavergara-lang/cmux-developer-connect/releases/tag/v0.1.0-preview.1)**. Está compilado para Mac con Apple Silicon (M1 o posterior), con destino mínimo macOS 14. Incluye el runtime de las conexiones entre Macs. Para usarlo no necesitas Xcode, Homebrew, Zig, Rust ni Python instalado.

## Instalar

1. En Releases, descarga `cmux-Developer-Connect-…-macOS-arm64.dmg`, no los archivos **Source code**. Esos son fuentes, no un instalador.
2. Abre el DMG y arrastra **cmux Developer Connect.app** al acceso **Applications**.
3. Espera que termine la copia. Expulsa el DMG y abre **cmux Developer Connect** desde Aplicaciones. Puedes dejarlo fijo en el Dock.
4. Codex y OpenCode se instalan y autentican por separado en cada Mac. La app no incluye tus cuentas ni sus claves.

Esta preview tiene **firma local (ad hoc), sin Developer ID ni notarización de Apple**. Si macOS bloquea la primera apertura y confías en esta descarga, intenta abrir la copia instalada y ve a **Ajustes del Sistema → Privacidad y seguridad → Abrir de todos modos**. Autoriza solamente esta app. [Explicación de Apple](https://support.apple.com/es-es/102445). No es necesario desactivar Gatekeeper, modificar la seguridad global ni ejecutar un comando de `sudo` para abrirla. Un Mac administrado puede impedir esta excepción.

## Verificar la descarga

Descarga también `SHA256SUMS.txt` en la misma carpeta del DMG. En Terminal, entra a esa carpeta y ejecuta:

```sh
shasum -a 256 -c SHA256SUMS.txt
```

Debe informar `OK`. Esto detecta una descarga incompleta o modificada respecto de la release; no equivale a una certificación de Apple. `release-manifest.json` indica versión, commit de fuentes, arquitectura y firma.

## Conectar el segundo Mac

Instala la misma versión en ambos Macs y sigue [Conexión entre Macs](developer-peers.md). Desde el Mac de origen: **Archivo → Computadores de confianza → Compartir aplicación**. Pega la invitación en el segundo Mac. Las terminales locales y las del origen aparecen juntas; los procesos remotos siguen viviendo en el Mac de origen.

La LAN requiere que la Wi-Fi permita comunicación entre equipos y los permisos de red local que solicite macOS. Para Internet, usa Tailscale en ambos Macs. Las invitaciones vencen y pueden revocarse; trata una invitación como una credencial de control. Las vistas remotas aún tienen los límites descritos en el README.

## Actualizar o desinstalar

Para actualizar, termina o guarda el trabajo, cierra esta app por tu cuenta y sustituye su copia en Aplicaciones con la del nuevo DMG. Una copia local y una remota deben usar la misma preview. No uses el actualizador de cmux upstream para este fork: las nuevas versiones se descargan desde sus propias Releases.

Para desinstalar, cierra la app y retírala de Aplicaciones. Esto no borra automáticamente sesiones, preferencias ni credenciales del Llavero. Revoca antes los computadores que ya no quieres autorizar. El instalador no instala servicios del sistema ni inicia el acceso remoto automáticamente.

## Si algo falla

- **Comienza a compilar o aparecen gigabytes de archivos:** descargaste o ejecutaste las fuentes. Usa el DMG; nunca ejecutes `setup.sh` o `build-developer.sh` para una instalación normal.
- **La app no se abre:** verifica la arquitectura del Mac, su versión de macOS, el checksum y la autorización de primera apertura. Si macOS dice que está dañada, no elimines la cuarentena a ciegas: vuelve a descargar y verifica el checksum; conserva el texto exacto del error.
- **No encuentras la app:** Finder → Aplicaciones → cmux Developer Connect. Copiar al acceso `Applications` del DMG instala en `/Applications`, no en `~/Applications`.
- **Codex/OpenCode no aparecen:** instala sus CLI por separado; el DMG no instala herramientas ni copia la autenticación de otro usuario.
- **La conexión remota falla:** comprueba que el origen esté abierto, que ambos Macs tengan la misma versión, la red local/Tailscale y una invitación vigente.

Para modificar las fuentes: [Guía de compilación](building-developer-connect.es.md). Las pruebas de esta entrega se ejecutan en un Mac; todavía falta validar un segundo Mac físico y todas las versiones de macOS compatibles.
