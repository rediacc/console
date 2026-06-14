---
title: Servicios
description: >-
  Despliegue y administre servicios en contenedores mediante Rediaccfiles,
  redes de servicios e inicio automático.
category: Guides
order: 5
language: es
sourceHash: "011bc5d87114f105"
sourceCommit: "3fb35b9a33c7e8ec6753ecd56231f2018e8f4803"
---

# Servicios

En esta página se cubre: despliegue y administración de servicios en contenedores, incluyendo Rediaccfiles, redes de servicios, inicio/parada, operaciones en lote e inicio automático.

## El Rediaccfile

El **Rediaccfile** es un script de Bash que define cómo se inician y detienen sus servicios. Se **carga** (no se ejecuta como un proceso separado), de modo que sus funciones comparten el mismo contexto de shell y tienen acceso a todas las variables de entorno exportadas. Debe tener el nombre `Rediaccfile` o `rediaccfile` (sin distinción de mayúsculas) y ubicarse dentro del sistema de archivos montado del repositorio.

Los Rediaccfiles se descubren en dos ubicaciones:
1. La **raíz** de la ruta de montaje del repositorio
2. **Subdirectorios de primer nivel** de la ruta de montaje (no recursivo)

Se omiten los directorios ocultos (nombres que comienzan con `.`).

### Funciones del Ciclo de Vida

Un Rediaccfile contiene hasta dos funciones:

| Función | Cuándo se ejecuta | Propósito | Comportamiento en caso de error |
|----------|-------------|---------|----------------|
| `up()` | Al iniciar | Iniciar servicios (por ejemplo, `renet compose -- up -d`) | El fallo raíz es **crítico** (detiene todo). Los fallos en subdirectorios son **no críticos** (registrados, continúa) |
| `down()` | Al detener | Detener servicios (por ejemplo, `renet compose -- down`) | **Mejor esfuerzo** -- los fallos se registran pero siempre se intenta ejecutar todos los Rediaccfiles |

Ambas funciones son opcionales. Si una función no está definida, se omite silenciosamente.

### Orden de Ejecución

- **Iniciando (`up`):** Rediaccfile raíz primero, luego subdirectorios en **orden alfabético** (A a Z).
- **Deteniendo (`down`):** Subdirectorios en **orden alfabético inverso** (Z a A), luego raíz al final.

### Variables de Entorno

Cuando se ejecuta una función de Rediaccfile, están disponibles las siguientes variables de entorno:

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `REDIACC_WORKING_DIR` | Ruta de montaje del repositorio | `/mnt/rediacc/mounts/abc123` |
| `REDIACC_REPOSITORY` | GUID del repositorio | `a1b2c3d4-e5f6-...` |
| `REDIACC_NETWORK_ID` | ID de red (entero) | `2816` |
| `DOCKER_HOST` | Socket de Docker para el daemon aislado de este repositorio | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | IP de loopback para cada servicio definido en `.rediacc.json` | `POSTGRES_IP=127.0.11.2` |

Las variables `{SERVICE}_IP` se generan automáticamente a partir de las asignaciones de slot en `.rediacc.json` y se exportan antes de que se ejecuten sus funciones de Rediaccfile. La convención de nombres convierte el nombre del servicio a mayúsculas con guiones reemplazados por guiones bajos, luego añade `_IP`. Por ejemplo, un servicio denominado `listmonk-app` con slot `0` se convierte en `LISTMONK_APP_IP=127.0.11.2`.

> **Advertencia: No use `sudo docker` en Rediaccfiles.** El comando `sudo` restablece las variables de entorno, lo que significa que se pierde `DOCKER_HOST` y los comandos de Docker se dirigirán al daemon del sistema en lugar del daemon aislado del repositorio. Esto rompe el aislamiento de contenedores y puede causar conflictos de puerto. Rediacc bloqueará la ejecución si detecta `sudo docker` sin `-E`.
>
> Use `renet compose` en sus Rediaccfiles, maneja automáticamente `DOCKER_HOST`, inyecta etiquetas de red para descubrimiento de rutas y configura redes de servicios. Véase [Redes](/es/docs/networking) para detalles sobre cómo se exponen los servicios a través del proxy inverso. Si llama a Docker directamente, use `docker` sin `sudo`, las funciones de Rediaccfile ya se ejecutan con privilegios suficientes. Si debe usar sudo, use `sudo -E docker` para preservar las variables de entorno.
>
> `renet` es la herramienta remota de bajo nivel. Para flujos de trabajo normales de usuario desde su estación de trabajo, prefiera comandos `rdc` como `rdc repo up` y `rdc repo down`. Véase [rdc vs renet](/es/docs/rdc-vs-renet).

### Ejemplo

```bash
#!/bin/bash

up() {
    echo "Starting services..."
    renet compose -- up -d
}

down() {
    echo "Stopping services..."
    renet compose -- down
}
```

> **Importante:** Siempre use `renet compose --` en lugar de `docker compose`. El envoltorio `renet compose` impone redes host, asignación de IP y etiquetas de descubrimiento de servicios requeridas por renet-proxy. Se añaden capacidades de punto de control/restauración CRIU a contenedores con la etiqueta `rediacc.checkpoint=true`. La prueba de Rediaccfile rechaza el uso directo de `docker compose`. Véase [Redes](/es/docs/networking) para detalles.

### Etiquetas de capacidad

Los contenedores se ejecutan con un conjunto mínimo de capacidades de Linux por defecto. Un servicio puede activar capacidades adicionales añadiendo una etiqueta a su `docker-compose.yml`:

| Etiqueta | Otorga | Para usar con |
|-------|--------|---------|
| `rediacc.checkpoint=true` | `CHECKPOINT_RESTORE`, `SYS_PTRACE`, `NET_ADMIN` | Punto de control/restauración CRIU (migración en vivo, guardar y reanudar) |
| `rediacc.wireguard=true` | `NET_ADMIN` más el dispositivo `/dev/net/tun` | Ejecutar un cliente WireGuard dentro del contenedor |

```yaml
services:
  vpn:
    image: alpine
    labels:
      - "rediacc.wireguard=true"
```

`rediacc.wireguard` permite que un servicio establezca un túnel WireGuard, por ejemplo para enrutar un proceso concreto a través de un endpoint remoto. Como todos los servicios usan red de host, confine el túnel a un namespace de red dentro del contenedor para no modificar el enrutamiento del host. Las opciones de privilegio amplio como `privileged: true`, `pid: host` e `ipc: host` siguen siendo rechazadas por la validación independientemente de las etiquetas.

### Diseño Multi-Servicio

Para proyectos con múltiples grupos de servicios independientes, use subdirectorios:

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # Raíz: configuración compartida
├── docker-compose.yml
├── database/
│   ├── Rediaccfile          # Servicios de base de datos
│   └── docker-compose.yml
├── backend/
│   ├── Rediaccfile          # Servidor API
│   └── docker-compose.yml
└── monitoring/
    ├── Rediaccfile          # Prometheus, Grafana, etc.
    └── docker-compose.yml
```

Orden de ejecución para `up`: raíz, luego `backend`, `database`, `monitoring` (A-Z).
Orden de ejecución para `down`: `monitoring`, `database`, `backend`, luego raíz (Z-A).

## Red de Servicios (.rediacc.json)

Cada repositorio obtiene una subred /26 (64 IPs) en el rango de loopback `127.x.x.x`. Los servicios se vinculan a IPs de loopback únicas para que puedan ejecutarse en los mismos puertos sin conflictos.

### El Archivo .rediacc.json

Mapea nombres de servicios a números de **slot**. Cada slot corresponde a una dirección IP única dentro de la subred del repositorio.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

### Generación Automática desde Docker Compose

No necesita crear `.rediacc.json` manualmente. Cuando ejecuta `rdc repo up`, Rediacc automáticamente:

1. Escanea todos los directorios que contienen un Rediaccfile en busca de archivos compose (`docker-compose.yml`, `docker-compose.yaml`, `compose.yml` o `compose.yaml`)
2. Extrae los nombres de servicio de la sección `services:`
3. Asigna el siguiente slot disponible a cualquier servicio nuevo
4. Guarda el resultado en `{repository}/.rediacc.json`

### Cálculo de IP

La IP de un servicio se calcula a partir del ID de red del repositorio y el slot del servicio. El ID de red se distribuye entre el segundo, tercer y cuarto octeto de una dirección de loopback `127.x.y.z`. Los servicios comienzan en el offset 2:

| Offset | Address | Purpose |
|--------|---------|---------|
| .0 | `127.0.11.0` | Network address (reserved) |
| .1 | `127.0.11.1` | Gateway (reserved) |
| .2. .62 | `127.0.11.2`. `127.0.11.62` | Services (`slot + 2`) |
| .63 | `127.0.11.63` | Broadcast (reserved) |

**Ejemplo** para ID de red `2816` (`0x0B00`), dirección base `127.0.11.0`:

| Servicio | Slot | Dirección IP |
|----------|------|--------------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

Cada repositorio soporta hasta **61 servicios** (slots 0 a 60).

### Uso de IPs de Servicio en Docker Compose

Dado que cada repositorio ejecuta un daemon Docker aislado, `renet compose` configura automáticamente `network_mode: host` para todos los servicios. El kernel reescribe transparentemente las llamadas `bind()` a la IP de loopback asignada al servicio, por lo que los servicios pueden vincularse a `0.0.0.0` o `localhost` sin conflictos. Para conexiones **a otros servicios**, use el **nombre del servicio**. renet inyecta cada nombre de servicio como hostname que siempre resuelve a la IP correcta, incluso en forks:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    # No se necesita listen_addresses explícito - el kernel reescribe bind a la IP de loopback correcta

  api:
    image: my-api:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb  # usar nombre de servicio
      LISTEN_ADDR: 0.0.0.0:8080                                      # el kernel reescribe a IP de servicio
```

> **Nombres de servicio para conexiones:** Use el **nombre de servicio** (p.ej. `postgres`, `redis`) para **conectarse a** otros servicios -- renet mapea automáticamente cada nombre de servicio a su IP de loopback vía `/etc/hosts`. Incrustar `${POSTGRES_IP}` en cadenas de conexión almacenadas en bases de datos o archivos de configuración fijará la IP bruta, lo que rompe el aislamiento de forks y es un **error de validación**. Las variables `${SERVICE_IP}` siguen disponibles para uso explícito, pero el binding es manejado automáticamente por el kernel.

> **Nota:** No agregue `network_mode: host` manualmente, `renet compose` lo inyecta automáticamente. Las políticas de reinicio (p.ej., `restart: always`) son seguras de usar, renet las elimina automáticamente para compatibilidad CRIU y el watchdog del router maneja la recuperación de contenedores.

### Recuperación de Contenedores y Política de Reinicio

renet y Docker difieren deliberadamente en cómo manejar los reinicios de contenedores. Entender esta división es importante al depurar por qué un contenedor regresó o no.

**Traducción de la política de reinicio.** Cuando escribe `restart: always` (o `unless-stopped`, o `on-failure`) en su archivo compose, renet la **elimina** al sintetizar el deployment real de compose y la reemplaza con `restart: no`. El valor original se guarda en `.rediacc.json` del repositorio bajo `services.<name>.restart_policy`. Esto evita que el auto-reinicio a nivel de daemon de Docker interfiera con CRIU checkpoint/restore (un reinicio controlado por el daemon reanudaría desde un estado previo al checkpoint desactualizado).

**Aplicación del watchdog.** El watchdog del router se ejecuta periódicamente en cada máquina. En cada ciclo:

1. Lee `.rediacc.json` para cada repositorio y encuentra servicios con una `restart_policy` recuperable.
2. Lista todos los contenedores del daemon de ese repositorio, identifica los detenidos y los reinicia según la política guardada. Un período de gracia de 30 segundos evita conflictos con un operador que acaba de ejecutar `docker stop`.
3. El mismo bucle también procesa `/var/run/rediacc/cold-backup-<guid>.running.json` (ver [Semántica de Cold Backup](backup-restore.md#cold-backup-semantics)). Los contenedores listados se reinician independientemente de la política guardada, porque el sidecar significa "renet detuvo estos intencionalmente y debe al operador un reinicio."

**Por qué `on-failure` puede parecer roto.** La política `on-failure` de Docker solo reinicia cuando el contenedor sale con un código no cero. Una detención ordenada (exit 0) de `docker stop` o un apagado del daemon no es un "fallo" y NO activa un reinicio, ni por la lógica nativa de Docker ni por la ruta de política guardada del watchdog. El sidecar de cold backup es la red de seguridad: cualquier contenedor que detuvimos intencionalmente se reinicia independientemente de su política.

**Cómo interpretar el estado en tiempo de ejecución:**

- `docker inspect <container>` -> `RestartPolicy.Name`: siempre será `no` para contenedores gestionados por renet. No se base en esto para la política semántica.
- `.rediacc.json` en el root del montaje del repositorio -> `services.<name>.restart_policy`: la intención real.
- `docker ps --format '{{.Status}}'`: estado en tiempo de ejecución.

**Cómo corregir una desviación.** Si la política guardada en `.rediacc.json` de un contenedor es incorrecta (por ejemplo, porque editó compose pero nunca recreó el contenedor), vuelva a ejecutar `rdc repo up --name <repo> -m <machine>`. El contenedor se recrea con la política actualizada registrada.

> **Experimental:** La recuperación basada en sidecar de cold backup y el flag `--sync-certs` en `rdc machine query` llegaron en renet 0.9+. Las versiones anteriores dependen únicamente de `restart_policy` guardada para la recuperación del watchdog, lo que puede dejar contenedores `on-failure` atascados después de un cold backup.

> **La red bridge de Docker está deshabilitada en los daemons por repositorio.** Cada daemon por repositorio (`FlavorRediacc`) se configura con `"bridge": "none"` e `"iptables": false`. Un simple `docker run <imagen>` dentro de la shell de un repositorio seguirá ejecutándose, pero el contenedor solo obtiene una interfaz de loopback y no tiene DNS ni conectividad saliente. Esto es intencional, ya que el aislamiento de loopback entre repos se impone mediante ganchos eBPF de cgroup que un contenedor en bridge evitaría. Los servicios de producción deben usar `renet compose` (que inyecta la red de host por usted); para depuración ad-hoc, pase `--network host` explícitamente: `docker run --rm --network host -it ubuntu bash`.
>
> Los daemons Hub por usuario (`FlavorHub`, usados en entornos de desarrollo) son la excepción: establecen `bridge="docker0"`, `iptables=true` y `live-restore=true` para que los contenedores ejecutados por el usuario tengan red bridge normal y conectividad saliente.

> **Nota:** Los repos fork obtienen rutas automáticas bajo el subdominio del padre: `{service}-fork-{tag}.{repo}.{machine}.{baseDomain}`. Los dominios personalizados se omiten para forks.

## Iniciar Servicios

Monte el repositorio e inicie todos los servicios:

```bash
rdc repo up --name my-app -m server-1
```

| Opción | Descripción |
|--------|-------------|
| `--detach` | Devolver el control en cuanto los contenedores estén iniciados; las comprobaciones de estado continúan en segundo plano |
| `--skip-router-restart` | Omitir el reinicio del servidor de rutas después de la operación |

La secuencia de ejecución es:
1. Montar el repositorio cifrado con LUKS (montaje automático si no está montado)
2. Iniciar el daemon Docker aislado
3. Generar automáticamente `.rediacc.json` a partir de archivos compose
4. Ejecutar `up()` en todos los Rediaccfiles (orden A-Z)

Después del despliegue, la salida muestra una sección **PROXY ROUTES** con las URLs reales para cada servicio. Los servicios con etiquetas Traefik personalizadas (p.ej. `traefik.http.routers.myapp.rule=Host(...)`) muestran sus dominios personalizados como URLs principales:

```
HTTP services (accessible via proxy after ~3s):
  gitlab-server:
    HTTPS: https://gitlab.example.com  (custom)
    Auto:  https://gitlab-server.gitlab.server-1.example.com
    IP:    127.0.11.130
```

Los servicios sin etiquetas Traefik personalizadas muestran solo la ruta auto-generada. Use estas URLs (no el patrón genérico impreso por la CLI) para acceso desde el navegador, llamadas API y configuración entre servicios.

### Inicio en modo desconectado

Con `--detach`, el comando devuelve el control en cuanto los contenedores están iniciados, sin esperar a que finalicen las comprobaciones de estado. El arranque termina en segundo plano: el proxy reintenta las conexiones con cada servicio hasta que esté disponible, por lo que las rutas se recuperan solas. Compruebe el progreso con `rdc machine query --containers --name <machine>`. Ideal para forks desechables y bucles automatizados donde no necesita que los servicios estén listos antes del siguiente paso.

### Sonda de disponibilidad

Tras `up()`, renet comprueba cada servicio HTTP hasta que acepta conexiones TCP, de modo que la primera petición del navegador no encuentre un 502 del proxy. Los servicios cuyos contenedores definen una comprobación de estado de Docker se dan por válidos directamente: un contenedor sano omite la sonda, y uno aún dentro de `start_period` registra una nota informativa en lugar de una advertencia. La sonda desiste tras 15 segundos (anúlelo con la variable de entorno `REDIACC_READINESS_TIMEOUT`, en segundos, en la máquina); los inicios en modo desconectado la omiten por completo.

## Detener Servicios

```bash
rdc repo down --name my-app -m server-1
```

| Opción | Descripción |
|--------|-------------|
| `--unmount` | Desmontar el repositorio cifrado después de detener los servicios. Si esto no tiene efecto, use `rdc repo unmount` por separado. |
| `--skip-router-restart` | Omitir el reinicio del servidor de rutas después de la operación |

La secuencia de ejecución es:
1. Ejecutar `down()` en todos los Rediaccfiles (orden inverso Z-A, mejor esfuerzo)
2. Detener el daemon Docker aislado (si se usa `--unmount`)
3. Desmontar y cerrar el volumen cifrado con LUKS (si se usa `--unmount`)

## Operaciones Masivas

Inicie o detenga todos los repositorios en una máquina a la vez:

```bash
rdc repo up -m server-1
```

| Opción | Descripción |
|--------|-------------|
| `--include-forks` | Incluir repositorios bifurcados |
| `--mount-only` | Solo montar, no iniciar contenedores |
| `--dry-run` | Mostrar lo que se haría |
| `--parallel` | Ejecutar operaciones en paralelo |
| `--concurrency <n>` | Máximo de operaciones concurrentes (predeterminado: 3) |
| `--skip-router-restart` | Omitir el reinicio del servidor de rutas después de la operación |

## Inicio Automático al Arranque

Por defecto, los repositorios deben montarse e iniciarse manualmente después de reiniciar el servidor. El **inicio automático** configura los repositorios para montarse automáticamente, iniciar Docker y ejecutar el `up()` del Rediaccfile cuando el servidor arranca.

### Cómo Funciona

Cuando habilita el inicio automático para un repositorio:

1. Se genera un archivo de clave LUKS aleatorio de 256 bytes y se agrega al slot 1 de LUKS del repositorio (el slot 0 permanece como la frase de contraseña del usuario)
2. El archivo de clave se almacena en `{datastore}/.credentials/keys/{guid}.key` con permisos `0600` (solo root)
3. Se instala un servicio systemd (`rediacc-autostart`) que se ejecuta al arranque para montar todos los repositorios habilitados e iniciar sus servicios

Al apagar, el servicio detiene graciosamente todos los servicios (`down()` del Rediaccfile), detiene los daemons Docker y cierra los volúmenes LUKS.

> **Nota de seguridad:** Habilitar el inicio automático almacena un archivo de clave LUKS en el disco del servidor. Cualquier persona con acceso root al servidor puede montar el repositorio sin la frase de contraseña. Evalúe esto según su modelo de amenazas.

### Habilitar

```bash
rdc repo autostart enable --name my-app -m server-1
```

Se le solicitará la frase de contraseña del repositorio.

### Habilitar Todos

```bash
rdc repo autostart enable -m server-1
```

### Deshabilitar

```bash
rdc repo autostart disable --name my-app -m server-1
```

Esto elimina el archivo de clave y destruye el slot 1 de LUKS.

### Actualización del Archivo de Clave en el Despliegue

Cuando el inicio automático está habilitado, `rdc repo up` valida el archivo de clave del slot 1 de LUKS.
Si el archivo de clave en disco aún coincide con el slot LUKS, no se realizan cambios.

Después de transferir un repositorio entre máquinas vía `repo push` / `repo pull`,
el archivo de clave en la nueva máquina no coincidirá. En este caso, `repo up` regenera automáticamente
el archivo de clave y actualiza el slot 1 de LUKS. Verá mensajes de registro:

```
Refreshing keyfile credential for <guid>
Killing LUKS slot 1: /mnt/rediacc/repositories/<guid>
Adding keyfile to LUKS slot 1: /mnt/rediacc/repositories/<guid>
```

Esto es seguro, el slot 0 (su frase de contraseña) nunca se modifica. Si el inicio automático no
está habilitado, la verificación se omite silenciosamente. Los fallos no son fatales y no bloquean el despliegue.

### Listar Estado

```bash
rdc repo autostart list -m server-1
```

Para más detalles sobre cómo el reconciliador periódico recupera repositorios que se caen después del arranque, consulte [Inicio Automático y Recuperación](/es/docs/autostart-recovery).

## Ejemplo Completo

Este ejemplo despliega una aplicación web con PostgreSQL, Redis y un servidor API.

### 1. Configurar

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc config init --name production --ssh-key ~/.ssh/id_ed25519
rdc config machine add --name prod-1 --ip 203.0.113.50 --user deploy
rdc config machine setup --name prod-1
rdc repo create --name webapp -m prod-1 --size 10G
```

### 2. Montar y Preparar

```bash
rdc repo mount --name webapp -m prod-1
```

### 3. Crear los Archivos de la Aplicación

Dentro del repositorio, cree:

**docker-compose.yml:**

```yaml
services:
  postgres:
    image: postgres:16
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme

  redis:
    image: redis:7-alpine

  api:
    image: myregistry/api:latest
    environment:
      DATABASE_URL: postgresql://app:changeme@postgres:5432/webapp
      REDIS_URL: redis://redis:6379
      LISTEN_ADDR: 0.0.0.0:8080
```

**Rediaccfile:**

```bash
#!/bin/bash

up() {
    mkdir -p data/postgres
    renet compose -- up -d

    echo "Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if renet compose -- exec postgres pg_isready -q 2>/dev/null; then
            echo "PostgreSQL is ready."
            return 0
        fi
        sleep 1
    done
    echo "Warning: PostgreSQL did not become ready within 30 seconds."
}

down() {
    renet compose -- down
}
```

### 4. Iniciar

```bash
rdc repo up --name webapp -m prod-1
```

### 5. Habilitar Inicio Automático

```bash
rdc repo autostart enable --name webapp -m prod-1
```

## Usar secretos por repositorio en compose

El placeholder `POSTGRES_PASSWORD: changeme` anterior es correcto para un tutorial, pero las aplicaciones reales necesitan credenciales reales, y confirmar éstas en el archivo compose (o en un archivo `.env` dentro del repositorio) significa que un fork hereda también esas credenciales. Para credenciales en tiempo de despliegue, use `rdc repo secret`. Los valores viven fuera de la imagen de repositorio cifrada, por lo que los forks comienzan con un mapa de secretos vacío.

Dos modos de entrega funcionan en compose:

**Modo `env`.** Interpole vía `${REDIACC_SECRET_<KEY>}` en cualquier valor `environment:`. El wrapper renet pasa el valor al entorno del contenedor en tiempo de despliegue.

**Modo `file`.** El valor aterriza en un archivo tmpfs del lado del host en `/var/run/rediacc/secrets/<networkID>/<KEY>`, y usted lo monta en el contenedor vía el bloque `secrets:` estándar de Docker compose. El contenedor lee `/run/secrets/<key>`. Prefiera este modo para cualquier cosa sensible. Los valores nunca aparecen en `docker inspect` o `/proc/<pid>/environ`.

```yaml
services:
  api:
    image: myregistry/api:latest
    environment:
      DATABASE_URL: ${REDIACC_SECRET_DATABASE_URL}
    secrets:
      - stripe_live_key

secrets:
  stripe_live_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_LIVE_KEY
```

Siembre los valores con `rdc repo secret set --name <repo> --key DATABASE_URL --value <val> --mode env --current ""` y el equivalente en modo file. Consulte [Repositorios § Secretos](/es/docs/repositories#secrets) para la guía completa y [Secretos por repositorio](/es/docs/rdc-cheat-sheet#per-repo-secrets) en la hoja de trucos para la referencia de comandos.

> **Las rutas entre repositorios se rechazan en tiempo de validación.** Un `secrets: file:` (o `configs: file:`, o `env_file:`) de compose que apunta a `/var/run/rediacc/secrets/<other-networkID>/` de otro repositorio se rechaza duramente por el wrapper renet antes de que docker compose se ejecute. `--unsafe` NO anula esto. Defensa en profundidad: el sandbox Landlock alrededor de la shell del Rediaccfile restringe lecturas al directorio de secretos de la red actual, por lo que un `cat /var/run/rediacc/secrets/<other>/X` desde bash del Rediaccfile falla con EACCES incluso si evita el validador YAML. No necesita optar por esto; está activado por defecto para cada `repo up`.
