# Compilar y empaquetar el fork

Para **usar** la app, [instala el DMG](installation.es.md). Esta guía es para modificar su código. Una compilación nativa descarga dependencias y produce cachés de varios GB; esos archivos no son parte de la instalación.

## Preparación (Apple Silicon)

- Xcode completo, no solamente Command Line Tools. Upstream fija Xcode 26 en `.xcode-version`; esta preview se verifica con Xcode 27. Abre Xcode y completa los componentes/licencia que solicite Apple.
- Metal Toolchain disponible en el Xcode seleccionado: `xcrun metal --version`. Si falta, ejecuta `xcodebuild -downloadComponent MetalToolchain`.
- Python 3 para las herramientas de compilación; Rust/Cargo y `rustup`; Go para builds Release; Zig de la misma serie indicada por `ghostty/build.zig.zon` (en esta base: **0.16.x**, mínimo 0.16.0). No uses una serie mayor automáticamente.
- Conexión a Internet para los submódulos, SwiftPM, Rust, GhosttyKit y el runtime Python fijado por checksum. Sigue también los prerrequisitos de [CONTRIBUTING](../CONTRIBUTING.md).

```sh
git clone --branch developer-connect --single-branch --recursive \
  https://github.com/aldovegavergara-lang/cmux-developer-connect.git
cd cmux-developer-connect
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
export PATH="$HOME/.cargo/bin:/opt/homebrew/bin:$PATH"
zig version
xcrun metal --version
./scripts/setup.sh
```

`setup.sh` comprueba herramientas y descarga GhosttyKit precompilado con checksum; no instala ni abre el producto. Si Zig está en una carpeta propia, agrega esa carpeta a `PATH`; `CMUX_ZIG` sirve para las fases que aceptan un ejecutable explícito, pero no sustituye el `PATH` requerido por `setup.sh`.

## Compilar para desarrollo

```sh
export CMUX_DERIVED_DATA="$HOME/Library/Developer/Xcode/DerivedData/cmux-developer-local"
./scripts/build-developer.sh
```

Reutiliza la misma carpeta y tag al recompilar. No ejecutes varios builds a la vez en esa carpeta. El script imprime dónde quedó la app; esa app usa una identidad y un socket distintos a cmux oficial. Sin `--launch`, compilar no abre la app. El runtime Python para compartir sesiones se descarga automáticamente a `~/Library/Caches/cmux-developer/toolchains/`.

## Compilar la app optimizada y crear un DMG

Con Go, Rust, Zig y Metal preparados:

```sh
export CMUX_PEER_RUNTIME="$(python3 scripts/prepare-developer-peer-runtime.py)"
CMUX_DEV_BACKEND_MODE=local CMUX_GHOSTTYKIT_PREPROVISIONED=1 \
  ./scripts/reload.sh --release --tag installer-audit \
  --name 'cmux Developer Installer' --no-global-cli-links
```

La build debe terminar correctamente; usa la ruta **App path** que imprime. Comprueba que las fuentes y submódulos no tengan modificaciones pendientes antes de atribuir el binario a un commit:

```sh
git status --short
git submodule status
```

El empaquetador **no compila ni certifica** la app; quien lo usa debe verificar el commit del build. Sustituye la ruta del siguiente ejemplo por la que imprimió el build:

```sh
python3 scripts/make-developer-dmg.py \
  --app '/ruta/impresa/cmux Developer Installer.app' \
  --output "$HOME/Desktop/Developer-Connect-release" \
  --version 0.1.0-preview.1 \
  --source-commit "$(git rev-parse HEAD)"
```

El resultado incluye DMG, `SHA256SUMS.txt` y `release-manifest.json`. Se repara la ubicación relativa de recursos del CLI, se verifica la firma y el Python incluido, y se rechazan enlaces del bundle que dependan del Mac de compilación. La firma local no permite notarizar: una distribución notarizada necesita certificado Developer ID y credenciales de Apple del distribuidor. No se incluyen esas credenciales en el repo ni en el DMG.

## Cachés y errores

Mantener DerivedData acelera recompilaciones. Si necesitas liberar espacio, cierra antes tus builds y elimina **solamente** la carpeta DerivedData que elegiste para este fork, desde Finder. Esto fuerza una compilación fría; no elimines datos de sesiones, el Llavero ni la app que esté ejecutando trabajo.

Si falta Metal, selecciona el Xcode correcto (`DEVELOPER_DIR`) e instala su componente. Si Zig es incompatible, instala la serie del manifiesto. Si Swift termina con el error conocido de GlobalISel, repite el build etiquetado con `--swift-frontend-workaround`, como en las pruebas de esta preview. Conserva el log que imprime `reload.sh` para cualquier otro error.
