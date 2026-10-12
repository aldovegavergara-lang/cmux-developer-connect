# Developer Connect: acceso móvil

El puente permite ver y controlar una terminal compartida desde Android o un
navegador. El menú muestra las sesiones exportadas de la aplicación de origen.
La autenticación de este puente es independiente del login de cmux, desactivado
en el fork, y de las cuentas que use cada agente CLI.

## Preparación

En el Mac de origen, instala `tmux` y `ttyd` de sus fuentes oficiales. El modo
Tailscale requiere Tailscale conectado y HTTPS habilitado en la tailnet. Estas
herramientas no son necesarias para la conexión nativa entre Macs y no se incluyen
como credenciales ni configuración predefinida en el repositorio.

1. En Developer Connect elige Archivo → Nueva sesión móvil.
2. Sigue el asistente y selecciona Tailscale o una LAN privada.
3. Abre la URL que muestra en Android; conecta también Tailscale si usas ese modo.
4. Usa `developer` y la clave aleatoria que muestra el asistente. No reutilices
   claves de otras cuentas.
5. Usa el menú de sesiones para elegir un espacio; la terminal sigue en el origen.
6. Detener el asistente cierra el acceso. No termina la sesión tmux original.

Las invitaciones, direcciones y claves se generan localmente. El paquete no incluye
un hostname, tailnet, IP ni contraseña de ningún equipo concreto.

## Seguridad y límites

El modo `--menu` es obligatorio. El proxy comprueba autenticación y Origin antes
de llegar a ttyd. El backend escucha en un socket Unix 0600 dentro de un directorio
0700; la contraseña no aparece en los argumentos del proceso ni hay un puerto TCP
secundario de terminal. La clave y el estado se almacenan fuera del repositorio con
permisos privados. Las conexiones y los tiempos de lectura están acotados.
Los WebSocket autenticados conservan el plazo de la sesión sin aplicarles el límite
corto de lectura de cabeceras.

Tailscale Serve publica el puerto solo en la tailnet y utiliza una concesión en
primer plano. Detenerla revoca ese puerto sin resetear otros servicios. No se abre
un puerto del router ni se usa Funnel. Usa permisos restringidos de la tailnet.

El modo LAN usa HTTPS con certificado local autofirmado: verifica su huella antes
de confiar en él. Esa confianza debe aprobarla el usuario; no se desactiva la
validación TLS para evitar el paso. Algunas Wi-Fi de invitados aíslan dispositivos.
El puente es un prototipo para redes de confianza, no un servicio público.

El menú web conserva sus nueve idiomas y sigue el idioma del navegador. El dictado
usa la configuración y permisos del sistema operativo, fuera del repositorio.

## Verificar

Usa un CLI de build aislada, Python 3.13 o posterior y tmux/ttyd de prueba:

```sh
CMUX_MOBILE_TEST_CLI='/ruta/a/la/build/Contents/Resources/bin/cmux' \
  python3 -B scripts/test_developer_mobile_share.py
python3 -B scripts/test_developer_mobile_menu.py
python3 -B scripts/test_developer_mobile_security.py
python3 scripts/verify-local.py --swift-changed
python3 scripts/localization_catalog.py check
```

Los fixtures son descartables. Cubren TLS, HTTP/WebSocket, autenticación, rechazo de
Origin ajeno, escritura, solo lectura, menú de sesiones, vencimiento y conservación
del proceso original. Las pruebas locales no certifican un celular físico conectado
por Internet.

Referencias: [ttyd](https://github.com/tsl0922/ttyd), [Tailscale Serve](https://tailscale.com/kb/1242/tailscale-serve),
[persistencia local](local-tmux.md) y [conexión entre Macs](developer-peers.md).
