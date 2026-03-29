---
title: "Hub"
description: "Proporcione entornos contenedorizados autenticados por usuario con aprovisionamiento automático, gestión de inactividad y checkpoint/restore."
category: "Guides"
order: 14
language: es
sourceHash: "1fc292d45411451c"
sourceCommit: "b41fcf7b6f7e7235c0b7ca008df638c9aec5985e"
---

# Hub

El Hub proporciona entornos contenedorizados por usuario detrás de autenticación OAuth. Los usuarios visitan una única URL, se autentican con cualquier proveedor OAuth2 y son enrutados de forma transparente a su contenedor personal. Los contenedores se crean bajo demanda y se gestionan automáticamente.

Todo se configura mediante labels en `docker-compose.yml`. El Hub no conoce ni se preocupa por lo que se ejecuta dentro de los contenedores -- se encarga de la autenticación, el enrutamiento y el ciclo de vida. Los repositorios definen el comportamiento.

## Cómo funciona

![Arquitectura del Hub](/img/hub-architecture.svg)

1. Un usuario visita `code.example.com`
2. El Hub verifica la cookie de sesión. Si no existe, el usuario es redirigido al proveedor OAuth2 configurado (Nextcloud, Keycloak, GitHub, etc.)
3. Tras la autenticación, el Hub identifica al usuario y busca su contenedor
4. Si no existe ningún contenedor, se crea uno bajo demanda a partir de la plantilla configurada
5. La solicitud se envía mediante proxy inverso al contenedor del usuario
6. El Hub determina a qué puerto hacer proxy según el hostname (p. ej., `code.` -> puerto 8080, `term.` -> puerto 7681)

Los contenedores inactivos se detienen automáticamente o se guardan mediante checkpoint (CRIU) para restauración instantánea en el siguiente inicio de sesión.

## Inicio rápido

Agregue el Hub como servicio en el `docker-compose.yml` de su repositorio:

```yaml
services:
  hub:
    image: ubuntu:24.04
    entrypoint: /usr/bin/renet
    command:
      - hub
      - start
      - --docker-socket=/var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock
      - --network-id=${REDIACC_NETWORK_ID}
      - --base-domain=${HUB_DOMAIN}
      - --workspace-dir=${REDIACC_WORKING_DIR}/workspaces
    env_file:
      - ./hub.env
    volumes:
      - /usr/lib/rediacc/renet/current/renet:/usr/bin/renet:ro
      - /var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock:/var/run/rediacc/docker-${REDIACC_NETWORK_ID}.sock
      - ./workspaces:${REDIACC_WORKING_DIR}/workspaces
    labels:
      - "traefik.enable=true"

      # Mapeo de rutas: prefijo de subdominio -> puerto en contenedores de usuario
      - "rediacc.hub.route.code=8080"
      - "rediacc.hub.route.term=7681"
      - "rediacc.hub.route.desktop=6080"

      # Plantilla de contenedor
      - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
      - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host $${SERVICE_IP} --port 8080"
      - "rediacc.hub.user=vscode"

      # Rutas de Traefik (una por subdominio)
      - "traefik.http.routers.hub-code.rule=Host(`code.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-code.entrypoints=websecure"
      - "traefik.http.routers.hub-code.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-code.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-term.rule=Host(`term.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-term.entrypoints=websecure"
      - "traefik.http.routers.hub-term.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-term.loadbalancer.server.port=7112"
      - "traefik.http.routers.hub-desktop.rule=Host(`desktop.${HUB_DOMAIN}`)"
      - "traefik.http.routers.hub-desktop.entrypoints=websecure"
      - "traefik.http.routers.hub-desktop.tls.certresolver=letsencrypt"
      - "traefik.http.services.hub-desktop.loadbalancer.server.port=7112"
```

Cree `hub.env` con las credenciales de su proveedor OAuth2:

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

Despliegue con `rdc repo up`.

## Configuración

Toda la configuración del Hub reside en los labels de Compose del propio servicio Hub. No hay archivos de configuración dentro del binario del Hub.

### Mapeo de rutas

Asocie prefijos de subdominio a puertos en los contenedores de usuario. El Hub lee estos labels para saber a dónde enviar cada solicitud.

| Label | Descripción | Ejemplo |
|-------|-------------|---------|
| `rediacc.hub.route.{prefix}` | Asocia `{prefix}.{domain}` a este puerto en el contenedor del usuario | `rediacc.hub.route.code=8080` |

Puede definir cualquier cantidad de rutas. El prefijo se compara con el primer segmento del hostname:

```yaml
labels:
  - "rediacc.hub.route.code=8080"      # code.example.com -> :8080
  - "rediacc.hub.route.term=7681"      # term.example.com -> :7681
  - "rediacc.hub.route.desktop=6080"   # desktop.example.com -> :6080
  - "rediacc.hub.route.jupyter=8888"   # jupyter.example.com -> :8888
```

Cada ruta necesita además un router de Traefik correspondiente que apunte al puerto del Hub (7112). El Hub maneja el enrutamiento por usuario internamente.

### Plantilla de contenedor

Defina cómo deben verse los contenedores de usuario. El Hub lee estos labels y los usa al crear un nuevo contenedor para un usuario.

| Label | Descripción | Valor predeterminado |
|-------|-------------|---------|
| `rediacc.hub.image` | Imagen del contenedor | Valor del flag `--container-image` |
| `rediacc.hub.command` | Comando de inicio (compatible con bash -c) | ninguno |
| `rediacc.hub.user` | Usuario del contenedor (se recomienda no-root) | `vscode` |
| `rediacc.hub.workspace` | Punto de montaje del workspace dentro del contenedor | `/workspace` |
| `rediacc.hub.shm_size` | Tamaño de memoria compartida en bytes | `1073741824` (1 GB) |

El label `command` soporta la expansión `${SERVICE_IP}`, que se reemplaza con la IP de loopback asignada al contenedor en el momento de la creación.

```yaml
labels:
  - "rediacc.hub.image=ghcr.io/my-org/dev-env:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=$${SERVICE_IP} --port=8888 --no-browser"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.workspace=/home/jovyan/work"
```

> **Consejo:** Use `$$` para un `$` literal en labels de Compose para evitar la expansión prematura de variables de entorno por Docker Compose.

### Límites de recursos

Establezca límites de recursos por usuario para evitar que un solo usuario consuma todos los recursos del host.

| Label | Descripción | Ejemplo |
|-------|-------------|---------|
| `rediacc.hub.limits.cpu` | Límite de CPU (núcleos) | `2` |
| `rediacc.hub.limits.memory` | Límite de memoria | `4g` |

```yaml
labels:
  - "rediacc.hub.limits.cpu=2"
  - "rediacc.hub.limits.memory=4g"
```

### Hooks de ciclo de vida

Ejecute comandos dentro del contenedor del usuario en puntos específicos del ciclo de vida.

| Label | Cuando se ejecuta | Ejemplo |
|-------|-------------|---------|
| `rediacc.hub.hook.on_create` | Después de crear el contenedor (primer inicio de sesión) | Clonar repos, instalar dependencias |
| `rediacc.hub.hook.on_start` | Después de iniciar o restaurar el contenedor | Montar secretos, actualizar tokens |
| `rediacc.hub.hook.on_idle` | Antes de detener o hacer checkpoint del contenedor | Guardar estado, enviar cambios |

```yaml
labels:
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/repo /workspace/project"
  - "rediacc.hub.hook.on_start=echo Welcome back, $HUB_USER"
  - "rediacc.hub.hook.on_idle=cd /workspace && git stash"
```

### Checkpoint / Restore

Cuando está habilitado, los contenedores inactivos se guardan mediante checkpoint con CRIU en lugar de detenerse. En el siguiente inicio de sesión, el contenedor se restaura desde el checkpoint en segundos, preservando el estado exacto: archivos abiertos, procesos en ejecución, sesiones de terminal.

| Label | Descripción | Valor predeterminado |
|-------|-------------|---------|
| `rediacc.hub.checkpoint` | Habilitar checkpoint CRIU para contenedores de usuario | `false` |

También pase `--checkpoint` al iniciar el Hub:

```yaml
command:
  - hub
  - start
  - --checkpoint
  - ...otros flags...
```

> **Nota:** Checkpoint/restore requiere que el binario CRIU esté disponible en el host y que el contenedor se ejecute en modo de red del host (el valor predeterminado para servicios Rediacc).

### Control de acceso

Restrinja quién puede usar el Hub y quién tiene privilegios de administrador.

| Label | Descripción | Ejemplo |
|-------|-------------|---------|
| `rediacc.hub.allowed_groups` | Grupos separados por coma autorizados a usar el Hub | `developers,ops` |
| `rediacc.hub.admin_users` | Nombres de usuario administrador separados por coma | `alice,bob` |

Los usuarios administradores pueden ver y gestionar todos los contenedores en el dashboard. Los usuarios regulares solo ven los suyos.

### Modo efímero

De forma predeterminada, los workspaces de usuario son persistentes (sobreviven a reinicios de contenedor). El modo efímero proporciona un entorno limpio en cada inicio de sesión, útil para demos, capacitación o CI.

| Label | Descripción | Valor predeterminado |
|-------|-------------|---------|
| `rediacc.hub.mode` | `persistent` o `ephemeral` | `persistent` |

```yaml
labels:
  - "rediacc.hub.mode=ephemeral"
```

En modo efímero, el workspace utiliza tmpfs (respaldado por RAM) y el contenedor se elimina automáticamente cuando se detiene.

### Soporte multi-plantilla

Ofrezca múltiples tipos de entorno. Los usuarios pueden elegir su plantilla en el primer inicio de sesión o cambiar a través del dashboard.

```yaml
labels:
  # Plantilla predeterminada
  - "rediacc.hub.template.default=fulldev"

  # Entorno de desarrollo completo
  - "rediacc.hub.template.fulldev.image=ghcr.io/org/devcontainer:latest"
  - "rediacc.hub.template.fulldev.command=start-desktop.sh & ttyd ... & exec openvscode-server ..."
  - "rediacc.hub.template.fulldev.description=Full development environment with VS Code, terminal, and desktop"

  # Opción ligera
  - "rediacc.hub.template.lite.image=ghcr.io/org/devcontainer:lite"
  - "rediacc.hub.template.lite.command=exec openvscode-server --host $${SERVICE_IP} --port 8080"
  - "rediacc.hub.template.lite.description=VS Code only (lightweight, faster startup)"
```

## Configuración de OAuth

El Hub funciona con cualquier proveedor OAuth2 estándar. La configuración es mediante variables de entorno, no labels de Compose (los secretos no deben estar en labels).

| Variable | Descripción | Requerido |
|----------|-------------|----------|
| `HUB_OAUTH_CLIENT_ID` | ID de cliente OAuth2 | Sí |
| `HUB_OAUTH_CLIENT_SECRET` | Secreto de cliente OAuth2 | Sí |
| `HUB_OAUTH_AUTHORIZE_URL` | Endpoint de autorización del proveedor | Sí |
| `HUB_OAUTH_TOKEN_URL` | Endpoint de token del proveedor | Sí |
| `HUB_OAUTH_USERINFO_URL` | Endpoint de información de usuario del proveedor | Sí |
| `HUB_OAUTH_USERINFO_PATH` | Ruta con puntos para extraer el nombre de usuario de la respuesta JSON | Sí |
| `HUB_OAUTH_REDIRECT_URI` | Sobreescribir URL de callback (se calcula automáticamente si está vacío) | No |
| `HUB_OAUTH_SCOPES` | Scopes adicionales (separados por espacios) | No |
| `HUB_SESSION_SECRET` | String hexadecimal de 32+ bytes para firmar cookies | Recomendado |

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

El `HUB_OAUTH_USERINFO_PATH` es una ruta separada por puntos dentro de la respuesta JSON. Para objetos anidados como el de Nextcloud `{"ocs":{"data":{"id":"alice"}}}`, use `ocs.data.id`.

## Dashboard

El Hub incluye un dashboard de autoservicio en `/_hub/dashboard`. Muestra:

- Todos los entornos en ejecución con su estado
- Enlaces a servicios (un clic para abrir código, terminal o escritorio)
- Temporizadores de inactividad y uso de recursos
- Controles de inicio/parada
- Los administradores pueden ver y gestionar todos los contenedores

Acceda al dashboard visitando `https://code.example.com/_hub/dashboard` después de autenticarse.

## Ejemplos

### Entorno de desarrollo (VS Code + Terminal + Escritorio)

Un entorno de desarrollo completo con OpenVSCode Server, una terminal web (ttyd) y un escritorio noVNC:

```yaml
labels:
  - "rediacc.hub.route.code=8080"
  - "rediacc.hub.route.term=7681"
  - "rediacc.hub.route.desktop=6080"
  - "rediacc.hub.image=ghcr.io/your-org/devcontainer:latest"
  - "rediacc.hub.command=start-desktop.sh & ttyd --writable --port 7681 bash & exec openvscode-server --host $${SERVICE_IP} --port 8080 --without-connection-token"
  - "rediacc.hub.user=vscode"
  - "rediacc.hub.limits.cpu=2"
  - "rediacc.hub.limits.memory=4g"
  - "rediacc.hub.hook.on_create=git clone https://github.com/org/project /workspace/project"
```

### Entorno de Jupyter Notebook

Un entorno de ciencia de datos con JupyterLab:

```yaml
labels:
  - "rediacc.hub.route.notebook=8888"
  - "rediacc.hub.image=jupyter/datascience-notebook:latest"
  - "rediacc.hub.command=exec jupyter lab --ip=$${SERVICE_IP} --port=8888 --no-browser --NotebookApp.token='' --NotebookApp.password=''"
  - "rediacc.hub.user=1000:100"
  - "rediacc.hub.workspace=/home/jovyan/work"
  - "rediacc.hub.limits.cpu=4"
  - "rediacc.hub.limits.memory=8g"
```

### Aplicación web simple

Un entorno de servicio único para un framework web:

```yaml
labels:
  - "rediacc.hub.route.app=3000"
  - "rediacc.hub.image=node:22-alpine"
  - "rediacc.hub.command=cd /workspace && npm install && exec npm run dev -- --host $${SERVICE_IP}"
  - "rediacc.hub.user=1000:1000"
  - "rediacc.hub.mode=ephemeral"
```

## Guías relacionadas

- [**Servicios**](/es/docs/services) -- Ciclo de vida de Rediaccfile, patrones de Compose
- [**Redes**](/es/docs/networking) -- Labels de Docker, enrutamiento Traefik, certificados TLS
- [**Backup y restauración**](/es/docs/backup-restore) -- Persistencia y recuperación de workspaces
- [**Entornos de desarrollo**](/es/docs/development-environments) -- Clonación de producción para entornos de desarrollo
