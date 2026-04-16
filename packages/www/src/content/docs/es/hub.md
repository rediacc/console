---
title: "Hub"
description: "Proporciona entornos de contenedor por usuario con autenticación, Docker daemons por usuario, selección de múltiples plantillas, checkpoint/restore con CRIU, registros de auditoría y recolección de basura de data-roots."
category: "Guides"
order: 14
language: es
sourceHash: "6fa16a1c73af497e"
sourceCommit: "b997ae00deb9e814edaf2fc449f4d9e36cfafe81"
---

# Hub

El Hub proporciona entornos de contenedor por usuario detrás de autenticación OAuth. Los usuarios visitan una única URL, se autentican con cualquier proveedor OAuth2 y son enrutados de forma transparente a su contenedor personal. Los contenedores se crean bajo demanda, cada usuario tiene su propio Docker daemon aislado y las sesiones inactivas se guardan con checkpoint CRIU para reanudación instantánea.

Todo se configura mediante etiquetas en `docker-compose.yml`. El Hub en sí se ejecuta como un servicio systemd del host materializado por el comando `renet hub install` desde el archivo Compose de tu repositorio. Los repositorios definen el comportamiento; el Hub gestiona la autenticación, el enrutamiento, el ciclo de vida y el aislamiento por usuario.

## Cómo funciona

1. Un usuario visita `code.example.com` (o `term.`, `desktop.`, o cualquier otro prefijo configurado).
2. El Hub comprueba la cookie de sesión. Si no existe, el usuario es redirigido al proveedor OAuth2 configurado (Nextcloud, Keycloak, GitHub, etc.).
3. Tras la autenticación, el Hub identifica al usuario y busca su contenedor.
4. Si no existe contenedor, el Hub aprovisiona un Docker daemon dedicado para ese usuario en el host y luego crea su contenedor.
5. La solicitud se redirige por proxy inverso al contenedor del usuario a través de la red de loopback.
6. Los contenedores inactivos se guardan con checkpoint CRIU y su daemon por usuario se detiene para liberar memoria. En el siguiente inicio de sesión el daemon vuelve y CRIU restaura el estado del contenedor en segundos.

## Inicio rápido

Añade el Hub como servicio en el `docker-compose.yml` de tu repositorio. El servicio está marcado como `install_as=systemd` para que se ejecute como servicio del host en lugar de como contenedor Docker (necesario para la gestión de daemons por usuario, que usa systemd).

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN:-example.com}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"

      # Mapeo de rutas: prefijo de subdominio -> puerto en contenedores de usuario
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # Plantilla de contenedor
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host __SERVICE_IP__ --port 8080"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"

      # Rutas Traefik (proveedor de archivo; rediacc-router también lee estas etiquetas)
      - "traefik.http.routers.hub-code.rule=Host(`code.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-code.entrypoints=websecure"
      - "traefik.http.routers.hub-code.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-code.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-term.rule=Host(`term.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-term.entrypoints=websecure"
      - "traefik.http.routers.hub-term.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-term.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-desktop.rule=Host(`desktop.${HUB_DOMAIN:-example.com}`)"
      - "traefik.http.routers.hub-desktop.entrypoints=websecure"
      - "traefik.http.routers.hub-desktop.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-desktop.loadbalancer.server.port=7112"
```

Crea `hub/.env` con las credenciales de tu proveedor OAuth2:

```bash
HUB_DOMAIN=example.com
HUB_OAUTH_CLIENT_ID=your-client-id
HUB_OAUTH_CLIENT_SECRET=your-client-secret
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/authorize
HUB_OAUTH_TOKEN_URL=https://auth.example.com/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
HUB_SESSION_SECRET=64-character-hex-string
```

Instala la unidad systemd del host (una sola vez, requiere root):

```bash
sudo renet hub install /path/to/docker-compose.yml
```

Esto lee los servicios `install_as=systemd` y escribe:

- `/etc/systemd/system/rediacc-hub.service` (la unidad)
- `/etc/rediacc/hub/hub.labels.yaml` (las etiquetas de plantilla)
- `/opt/rediacc/proxy/traefik/dynamic/rediacc-hub.yaml` (rutas del proveedor de archivo Traefik)

Luego `systemctl daemon-reload && systemctl enable --now rediacc-hub`. Para eliminar: `sudo renet hub uninstall /path/to/docker-compose.yml`.

## Referencia del comando install

| Comando | Propósito |
|---------|---------|
| `sudo renet hub install <compose-file>` | Traducir los servicios `install_as=systemd` del archivo Compose a artefactos del host e iniciar la unidad. |
| `sudo renet hub uninstall <compose-file>` | Detener, deshabilitar y eliminar todos los artefactos de los servicios. Los data-roots bajo `<workspace>/<user>-docker/` se conservan. |
| `sudo renet hub gc <workspace-dir>` | Limpiar los data-roots por usuario abandonados (por defecto: con más de 30 días sin daemon activo). Flags: `--max-age=30d`, `--dry-run`. |
| `renet hub status` | Estado JSON de todos los contenedores a través de la API del Hub en ejecución. |
| `renet hub stop <username>` | Detener el contenedor de un usuario específico. |

## Configuración

Toda la configuración del Hub reside en las etiquetas Compose del servicio Hub. Los secretos (OAuth client_secret, session_secret) van en `hub/.env`, no en las etiquetas.

### Mapeo de rutas

Mapea los prefijos de subdominio a los puertos en los contenedores de usuario. El Hub lee estas etiquetas para saber a dónde redirigir cada solicitud.

| Etiqueta | Descripción | Ejemplo |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | Mapea `{prefix}.{domain}` a este puerto en el contenedor del usuario | `rediacc.hub.route.code=8080` |

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

Cada ruta también necesita un router Traefik correspondiente que apunte al puerto del Hub (7112). El Hub gestiona el enrutamiento por usuario internamente en función del hostname.

### Plantilla de contenedor

Define el aspecto de los contenedores de usuario. El Hub lee estas etiquetas y las usa al crear un nuevo contenedor.

| Etiqueta | Descripción | Valor por defecto |
|-------|-------------|---------|
| `rediacc.hub.image` | Imagen del contenedor | Valor del flag `--container-image` |
| `rediacc.hub.command` | Comando de inicio (compatible con bash -c) | ninguno |
| `rediacc.hub.user` | Usuario del contenedor (se recomienda no root) | `vscode` |
| `rediacc.hub.workspace` | Punto de montaje del workspace dentro del contenedor | `/workspace` |
| `rediacc.hub.shm_size` | Tamaño de memoria compartida en bytes | `1073741824` (1 GB) |
| `rediacc.hub.docker` | `per-user` para aprovisionar un dockerd dedicado por usuario (muy recomendado) | `""` |

La etiqueta `command` admite la expansión de `${SERVICE_IP}` y `__SERVICE_IP__` (este último evita la pre-expansión de Compose) para la IP de loopback asignada al contenedor.

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.workspace=/workspace"
  - "rediacc.hub.docker=per-user"
```

### Docker daemon por usuario

Cuando se establece `rediacc.hub.docker=per-user`, cada usuario obtiene una instancia `dockerd` dedicada en el host, montada como `/var/run/docker.sock` dentro de su contenedor. Esto proporciona:

- `docker ps`, `docker run`, `docker build` completos dentro del entorno de usuario sin contenedores privilegiados ni Docker-in-Docker.
- Aislamiento completo entre usuarios (el usuario A no puede ver los contenedores o imágenes del usuario B).
- Un data-root BTRFS por usuario en `<workspace-dir>/<user>-docker/.rediacc/docker/data`, conservado entre sesiones para que las imágenes en caché sobrevivan los ciclos de checkpoint inactivo.

Los daemons se asignan en un rango de network-ID dedicado que comienza en 32768. Un archivo marcador `.networkid` en el data-root de cada usuario registra su ID asignado para que los usuarios recurrentes retomen el mismo daemon.

### Límites de recursos

Establece límites de recursos por usuario para evitar que un solo usuario consuma todos los recursos del host. Los límites se aplican tanto al contenedor del usuario como a su instancia dockerd por usuario (mediante systemd `CPUQuota=` / `MemoryMax=`).

| Etiqueta | Descripción | Ejemplo |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | Valor de systemd CPUQuota | `200%` (2 núcleos) |
| `rediacc.hub.limits.memory` | Valor de systemd MemoryMax | `8G` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=200%"
  - "rediacc.hub.limits.memory=8G"
```

Los daemons se ubican en el slice systemd `rediacc.slice` para que hereden los límites a nivel de slice.

### Soporte de múltiples plantillas

Ofrece múltiples tipos de entorno. Los usuarios eligen una plantilla al iniciar sesión visitando `https://code.example.com/_hub/login?template=python` (la selección viaja a través del estado OAuth). Cambiar de plantilla en inicios de sesión posteriores reconstruye el contenedor.

Define las plantillas con etiquetas `rediacc.hub.templates.<name>.<field>`. Las etiquetas planas `rediacc.hub.image` / `rediacc.hub.command` / etc. siguen definiendo la plantilla "por defecto" implícita para los usuarios que no eligen ninguna.

```yaml
labels:
  # La plantilla por defecto cuando se omite ?template=...
  - "rediacc.hub.template=fulldev"

  # Un entorno completo VS Code + desktop + terminal.
  - "rediacc.hub.templates.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.templates.fulldev.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
  - "rediacc.hub.templates.fulldev.user=vscode"

  # Solo VS Code, ligero.
  - "rediacc.hub.templates.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.templates.lite.command=exec openvscode-server --host __SERVICE_IP__ --port 8080"
  - "rediacc.hub.templates.lite.user=vscode"

  # Entorno específico de Python.
  - "rediacc.hub.templates.python.image=python:3.12-slim"
  - "rediacc.hub.templates.python.command=pip install jupyterlab && exec jupyter lab --ip=__SERVICE_IP__ --port=8888"
  - "rediacc.hub.templates.python.user=1000:1000"
```

### Hooks del ciclo de vida

Ejecuta comandos dentro del contenedor del usuario en puntos del ciclo de vida. Los hooks se ejecutan como el usuario del contenedor (no root).

| Etiqueta | Cuándo se ejecuta | Ejemplo |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | Tras la creación del contenedor (primer inicio de sesión) | Clonar repositorios, instalar dependencias |
| `rediacc.hub.hook.checkpoint.pre_dump` | Antes del checkpoint CRIU de una sesión inactiva | Detener daemons que no pueden checkpointearse (X server, dbus) |
| `rediacc.hub.hook.checkpoint.post_restore` | Tras la restauración CRIU | Reiniciar los daemons detenidos en pre_dump |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
  - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
```

### Checkpoint / Restore

Cuando se establece `--checkpoint`, los contenedores de usuario inactivos se guardan con checkpoint CRIU y su daemon por usuario se detiene para liberar memoria. En el siguiente inicio de sesión el daemon se reinicia y CRIU restaura el estado del contenedor desde disco, conservando archivos abiertos, procesos en ejecución y sesiones de terminal. El tiempo de reanudación típico es de unos pocos segundos independientemente de la carga de trabajo.

| Etiqueta | Descripción | Valor por defecto |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | Habilitar checkpoint CRIU para contenedores de usuario | `false` |

Pasa `--checkpoint` y un `--idle-timeout` distinto de cero (por ejemplo, `30m`) en el comando del Hub. Los directorios de checkpoint se encuentran en `<workspace-dir>/<user>/.checkpoint/`.

Si CRIU falla 3 veces seguidas para un usuario, el checkpoint se deshabilita para ese usuario y el respaldo pasa a ser detener y recrear.

### Modo efímero

Por defecto, los workspaces de usuario son persistentes (sobreviven al reinicio). El modo efímero proporciona un entorno limpio en cada inicio de sesión, útil para demos, formación o CI.

| Etiqueta | Descripción | Valor por defecto |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` o `ephemeral` | `persistent` |

En modo efímero el workspace usa tmpfs (respaldado por RAM) y el contenedor se elimina automáticamente al detenerse.

### Timeout de inactividad

| Flag | Descripción | Valor por defecto |
|------|-------------|---------|
| `--idle-timeout=<dur>` | Detener/checkpointear contenedores inactivos más tiempo del indicado | `0` (deshabilitado) |

`0` mantiene los contenedores ejecutándose indefinidamente. Un valor práctico es `30m`: los usuarios inactivos liberan memoria tras media hora y los que regresan reanudan en segundos mediante CRIU.

### Control de acceso

| Variable | Descripción |
|----------|-------------|
| `HUB_ALLOWED_GROUPS` | Grupos separados por comas con permiso para usar el Hub (cuando tu proveedor expone claims de grupo) |
| `HUB_ADMIN_USERS` | Nombres de usuario administradores separados por comas. Los admins ven y controlan los contenedores de otros usuarios en el dashboard. |

## Registro de auditoría

Cada evento de contenedor/imagen iniciado por el usuario (create, start, stop, destroy, kill, pull, push) en el daemon por usuario se añade como registro JSON delimitado por líneas en `/var/log/rediacc/hub/<user>.log`:

```json
{"ts":"2026-04-16T05:53:12Z","user":"alice","net_id":32768,"type":"container","action":"start","resource":"abc123...","attrs":{"image":"hello-world:latest","name":"happy_pike"}}
```

Las entradas sobreviven al checkpoint/restore de CRIU (el flujo de auditoría se rearma en la restauración). Usa `logrotate` para limitar el uso de disco; una configuración de ejemplo:

```
/var/log/rediacc/hub/*.log {
  daily
  rotate 30
  compress
  missingok
  notifempty
  copytruncate
}
```

## Dashboard

El Hub incluye un dashboard de autoservicio en `/_hub/dashboard`. Muestra:

- Todos los entornos en ejecución con su estado
- Plantilla seleccionada
- Enlaces de servicio (un clic para abrir código, terminal, escritorio u otra ruta)
- Temporizadores de inactividad
- Uso de disco por usuario, recuento de contenedores en ejecución y recuento de imágenes
- Los admins ven todos los contenedores; los usuarios regulares solo los suyos

Las estadísticas se muestrean cada 30 segundos.

## Recolección de basura de data-roots

Los data-roots por usuario se acumulan en hosts de larga duración. Programa `renet hub gc` para limpiar los abandonados. Un timer systemd funciona bien:

```ini
# /etc/systemd/system/rediacc-hub-gc.service
[Unit]
Description=Rediacc Hub data-root GC

[Service]
Type=oneshot
ExecStart=/usr/lib/rediacc/renet/current/renet hub gc /mnt/rediacc/mounts/<repo-guid>/devbox/workspaces --max-age=30d
```

```ini
# /etc/systemd/system/rediacc-hub-gc.timer
[Unit]
Description=Daily Rediacc Hub GC

[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

`--dry-run` registra candidatos sin eliminar. Un data-root es elegible cuando su archivo marcador `.networkid` es más antiguo que `--max-age` Y el daemon registrado ya no está configurado en el host.

## Configuración de OAuth

El Hub funciona con cualquier proveedor OAuth2 estándar. La configuración se realiza mediante variables de entorno.

| Variable | Descripción | Requerido |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | Client ID de OAuth2 | Sí |
| `HUB_OAUTH_CLIENT_SECRET` | Client secret de OAuth2 | Sí |
| `HUB_OAUTH_AUTHORIZE_URL` | Endpoint de autorización del proveedor | Sí |
| `HUB_OAUTH_TOKEN_URL` | Endpoint de token del proveedor | Sí |
| `HUB_OAUTH_USERINFO_URL` | Endpoint de userinfo del proveedor | Sí |
| `HUB_OAUTH_USERINFO_PATH` | Ruta con puntos para extraer el nombre de usuario de la respuesta JSON | Sí |
| `HUB_OAUTH_REDIRECT_URI` | Anular URL de callback (se calcula automáticamente si está vacío) | No |
| `HUB_OAUTH_SCOPES` | Scopes adicionales (separados por espacios) | No |
| `HUB_SESSION_SECRET` | Cadena hexadecimal de 32+ bytes para firmar cookies | Recomendado |

### Ejemplos de proveedores

**Nextcloud:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://cloud.example.com/apps/oauth2/authorize
HUB_OAUTH_TOKEN_URL=https://cloud.example.com/apps/oauth2/api/v1/token
HUB_OAUTH_USERINFO_URL=https://cloud.example.com/ocs/v2.php/cloud/user?format=json
HUB_OAUTH_USERINFO_PATH=ocs.data.id
```

**Keycloak:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://auth.example.com/realms/master/protocol/openid-connect/auth
HUB_OAUTH_TOKEN_URL=https://auth.example.com/realms/master/protocol/openid-connect/token
HUB_OAUTH_USERINFO_URL=https://auth.example.com/realms/master/protocol/openid-connect/userinfo
HUB_OAUTH_USERINFO_PATH=preferred_username
```

**GitHub:**
```bash
HUB_OAUTH_AUTHORIZE_URL=https://github.com/login/oauth/authorize
HUB_OAUTH_TOKEN_URL=https://github.com/login/oauth/access_token
HUB_OAUTH_USERINFO_URL=https://api.github.com/user
HUB_OAUTH_USERINFO_PATH=login
HUB_OAUTH_SCOPES=read:user
```

`HUB_OAUTH_USERINFO_PATH` es una ruta separada por puntos en la respuesta JSON. Para objetos anidados como `{"ocs":{"data":{"id":"alice"}}}` de Nextcloud, usa `ocs.data.id`.

## Ejemplos

### Entorno de desarrollo (VS Code + Terminal + Escritorio)

Un entorno de desarrollo completo con OpenVSCode Server, un terminal web (ttyd) y un escritorio noVNC. Los usuarios tienen su propio Docker daemon dentro.

```yaml
services:
  hub:
    env_file:
      - ./hub/.env
    command:
      - hub
      - start
      - --docker-socket=${DOCKER_SOCKET}
      - --network-id=${REDIACC_NETWORK_ID}
      - --port=7112
      - --base-domain=${HUB_DOMAIN}
      - --workspace-dir=${REDIACC_WORKING_DIR}/devbox/workspaces
      - --idle-timeout=30m
      - --checkpoint
    labels:
      - "rediacc.install_as=systemd"
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash --login & exec openvscode-server --host __SERVICE_IP__ --port 8080 --without-connection-token"
      - "rediacc.hub.user=vscode"
      - "rediacc.hub.docker=per-user"
      - "rediacc.hub.limits.cpu=200%"
      - "rediacc.hub.limits.memory=8G"
      - "rediacc.hub.checkpoint=true"
      - "rediacc.hub.hook.checkpoint.pre_dump=start-desktop.sh stop"
      - "rediacc.hub.hook.checkpoint.post_restore=start-desktop.sh"
      # ... Routers Traefik para cada prefijo ...
```

### Entorno Jupyter Notebook

Un entorno de ciencia de datos con JupyterLab:

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.notebook=8888"
  - "rediacc.hub.image=jupyter/datascience-notebook:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=__SERVICE_IP__ --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password=''"
  - "rediacc.hub.user=1000:100"
  - "rediacc.hub.workspace=/home/jovyan/work"
  - "rediacc.hub.limits.cpu=400%"
  - "rediacc.hub.limits.memory=16G"
```

### Aplicación web simple (Efímera)

Un entorno de servicio único que comienza desde cero en cada inicio de sesión:

```yaml
labels:
  - "rediacc.install_as=systemd"
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host __SERVICE_IP__"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## Guías relacionadas

- [**Servicios**](/es/docs/services) -- Ciclo de vida de Rediaccfile, patrones de Compose
- [**Redes**](/es/docs/networking) -- Etiquetas de Docker, enrutamiento Traefik, certificados TLS
- [**Backup y Restore**](/es/docs/backup-restore) -- Persistencia del workspace y recuperación
- [**Entornos de Desarrollo**](/es/docs/development-environments) -- Clonación de producción para entornos de desarrollo
