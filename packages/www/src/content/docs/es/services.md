---
title: Servicios
description: >-
  Despliegue y gestione servicios en contenedores usando Rediaccfiles, red de
  servicios e inicio automático.
category: Guides
order: 5
language: es
sourceHash: "9a08a357e86497e3"
sourceCommit: "8b0f83c57ebaaa0a2bee93143db34ab677b4e68b"
---

# Servicios

Si no tienes claro qué herramienta usar, consulta [rdc vs renet](/es/docs/rdc-vs-renet).

Esta página cubre cómo desplegar y gestionar servicios en contenedores: Rediaccfiles, red de servicios, inicio/detención, operaciones masivas e inicio automático.

## El Rediaccfile

El **Rediaccfile** es un script Bash que define cómo se inician y detienen sus servicios. Debe llamarse `Rediaccfile` o `rediaccfile` (insensible a mayúsculas) y colocarse dentro del sistema de archivos montado del repositorio.

Los Rediaccfiles se descubren en dos ubicaciones:
1. La **raíz** de la ruta de montaje del repositorio
2. **Subdirectorios de primer nivel** de la ruta de montaje (no recursivo)

Los directorios ocultos (nombres que comienzan con `.`) se omiten.

### Funciones del Ciclo de Vida

Un Rediaccfile contiene hasta dos funciones:

| Función | Cuándo se ejecuta | Propósito | Comportamiento en caso de error |
|---------|-------------------|-----------|--------------------------------|
| `up()` | Al iniciar | Iniciar servicios (por ejemplo, `renet compose -- up -d`) | La falla del Rediaccfile raíz es **crítica** (detiene todo). Las fallas en subdirectorios son **no críticas** (se registran, continúa al siguiente) |
| `down()` | Al detener | Detener servicios (por ejemplo, `renet compose -- down`) | **Mejor esfuerzo** -- las fallas se registran pero siempre se intentan todos los Rediaccfiles |

Ambas funciones son opcionales. Si una función no está definida, se omite silenciosamente.

### Orden de Ejecución

- **Inicio (`up`):** Primero el Rediaccfile raíz, luego los subdirectorios en **orden alfabético** (A a Z).
- **Detención (`down`):** Subdirectorios en **orden alfabético inverso** (Z a A), luego el raíz al final.

### Variables de Entorno

Cuando se ejecuta una función del Rediaccfile, las siguientes variables de entorno están disponibles:

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `REDIACC_WORKING_DIR` | Ruta de montaje del repositorio | `/mnt/rediacc/mounts/abc123` |
| `REDIACC_REPOSITORY` | GUID del repositorio | `a1b2c3d4-e5f6-...` |
| `REDIACC_NETWORK_ID` | ID de red (entero) | `2816` |
| `DOCKER_HOST` | Socket Docker del daemon aislado de este repositorio | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | IP de loopback para cada servicio definido en `.rediacc.json` | `POSTGRES_IP=127.0.11.2` |

Las variables `{SERVICE}_IP` se generan automáticamente a partir de `.rediacc.json`. La convención de nomenclatura convierte el nombre del servicio a mayúsculas con guiones reemplazados por guiones bajos, y luego agrega `_IP`. Por ejemplo, `listmonk-app` se convierte en `LISTMONK_APP_IP`.

> **Advertencia: No use `sudo docker` en los Rediaccfiles.** El comando `sudo` restablece las variables de entorno, lo que significa que `DOCKER_HOST` se pierde y los comandos de Docker apuntarán al daemon del sistema en lugar del daemon aislado del repositorio. Esto rompe el aislamiento de contenedores y puede causar conflictos de puertos. Rediacc bloqueará la ejecución si detecta `sudo docker` sin `-E`.
>
> Use `renet compose` en sus Rediaccfiles -- automáticamente gestiona `DOCKER_HOST`, inyecta etiquetas de red para el descubrimiento de rutas y configura la red de servicios. Consulte [Red](/es/docs/networking) para detalles sobre cómo se exponen los servicios a través del proxy inverso. Si llama a Docker directamente, use `docker` sin `sudo` -- las funciones del Rediaccfile ya se ejecutan con privilegios suficientes. Si debe usar sudo, use `sudo -E docker` para preservar las variables de entorno.

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

> **Importante:** Use siempre `renet compose --` en lugar de `docker compose`. El wrapper `renet compose` impone la red del host, la asignación de IP y las etiquetas de descubrimiento de servicios requeridas por renet-proxy. Las capacidades de checkpoint/restauración CRIU se añaden a los contenedores con la etiqueta `rediacc.checkpoint=true`. El uso directo de `docker compose` es rechazado por la validación del Rediaccfile. Consulte [Red](/es/docs/networking) para más detalles.

### Diseño Multi-Servicio

Para proyectos con múltiples grupos de servicios independientes, use subdirectorios:

```
/mnt/rediacc/mounts/my-app/
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

La IP de un servicio se calcula a partir del ID de red del repositorio y el slot del servicio. El ID de red se distribuye entre el segundo, tercer y cuarto octeto de una dirección de loopback `127.x.y.z`. Cada servicio recibe un desplazamiento de `slot + 2` (los desplazamientos 0 y 1 están reservados).

| Offset | Address | Purpose |
|--------|---------|---------|
| .0 | `127.0.11.0` | Network address (reserved) |
| .1 | `127.0.11.1` | Gateway (reserved) |
| .2 – .62 | `127.0.11.2` – `127.0.11.62` | Services (`slot + 2`) |
| .63 | `127.0.11.63` | Broadcast (reserved) |

**Ejemplo** para ID de red `2816` (`0x0B00`), dirección base `127.0.11.0`:

| Servicio | Slot | Dirección IP |
|----------|------|--------------|
| api | 0 | `127.0.11.2` |
| postgres | 1 | `127.0.11.3` |
| redis | 2 | `127.0.11.4` |

Cada repositorio soporta hasta **61 servicios** (slots 0 a 60).

### Uso de IPs de Servicio en Docker Compose

Dado que cada repositorio ejecuta un daemon Docker aislado, `renet compose` configura automáticamente `network_mode: host` para todos los servicios. El kernel reescribe transparentemente las llamadas `bind()` a la IP de loopback asignada al servicio, por lo que los servicios pueden vincularse a `0.0.0.0` o `localhost` sin conflictos. Para conexiones **a otros servicios**, use el **nombre del servicio** -- renet inyecta cada nombre de servicio como hostname que siempre resuelve a la IP correcta, incluso en forks:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    # No se necesita listen_addresses explícito -- el kernel reescribe bind a la IP de loopback correcta

  api:
    image: my-api:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb  # usar nombre de servicio
      LISTEN_ADDR: 0.0.0.0:8080                                      # el kernel reescribe a IP de servicio
```

> **Nombres de servicio para conexiones:** Use el **nombre de servicio** (p.ej. `postgres`, `redis`) para **conectarse a** otros servicios -- renet mapea automáticamente cada nombre de servicio a su IP de loopback via `/etc/hosts`. Incrustar `${POSTGRES_IP}` en cadenas de conexión almacenadas en bases de datos o archivos de configuración fijará la IP bruta, lo que rompe el aislamiento de forks y es un **error de validación**. Las variables `${SERVICE_IP}` siguen disponibles para uso explícito, pero el binding es manejado automáticamente por el kernel.

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

- `docker inspect <container>` → `RestartPolicy.Name`: siempre será `no` para contenedores gestionados por renet. No se base en esto para la política semántica.
- `.rediacc.json` en el root del montaje del repositorio → `services.<name>.restart_policy`: la intención real.
- `docker ps --format '{{.Status}}'`: estado en tiempo de ejecución.

**Cómo corregir una desviación.** Si la política guardada en `.rediacc.json` de un contenedor es incorrecta (por ejemplo, porque editó compose pero nunca recreó el contenedor), vuelva a ejecutar `rdc repo up --name <repo> -m <machine>`. El contenedor se recrea con la política actualizada registrada.

> **Experimental:** La recuperación basada en sidecar de cold backup y el flag `--sync-certs` en `rdc machine query` llegaron en renet 0.9+. Las versiones anteriores dependen únicamente de `restart_policy` guardada para la recuperación del watchdog, lo que puede dejar contenedores `on-failure` atascados después de un cold backup.

> **La red bridge de Docker está deshabilitada en los daemons gestionados por rediacc.** Cada daemon por repositorio se configura con `"bridge": "none"` e `"iptables": false`. Un simple `docker run <imagen>` dentro de la shell de un repositorio seguirá ejecutándose, pero el contenedor solo obtiene una interfaz de loopback y no tiene DNS ni conectividad saliente. Esto es intencional, ya que el aislamiento de loopback entre repos se impone mediante ganchos eBPF de cgroup que un contenedor en bridge evitaría. Los servicios de producción deben usar `renet compose` (que inyecta la red de host por usted); para depuración ad-hoc, pase `--network host` explícitamente: `docker run --rm --network host -it ubuntu bash`.

> **Nota:** Los repos fork obtienen rutas automáticas bajo el subdominio del padre: `{service}-fork-{tag}.{repo}.{machine}.{baseDomain}`. Los dominios personalizados se omiten para forks.

## Iniciar Servicios

Monte el repositorio e inicie todos los servicios:

```bash
rdc repo up --name my-app -m server-1
```

| Opción | Descripción |
|--------|-------------|
| `--skip-router-restart` | Omitir el reinicio del servidor de rutas después de la operación |

La secuencia de ejecución es:
1. Montar el repositorio cifrado con LUKS (montaje automático si no está montado)
2. Iniciar el daemon Docker aislado
3. Generar automáticamente `.rediacc.json` a partir de archivos compose
4. Ejecutar `up()` en todos los Rediaccfiles (orden A-Z)

Después del despliegue, la salida muestra una sección **PROXY ROUTES** con las URLs reales para cada servicio. Los servicios con etiquetas Traefik personalizadas muestran sus dominios personalizados como URLs principales:

```
HTTP services (accessible via proxy after ~3s):
  gitlab-server:
    HTTPS: https://gitlab.example.com  (custom)
    Auto:  https://gitlab-server.gitlab.server-1.example.com
    IP:    127.0.11.130
```

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

Después de transferir un repositorio entre máquinas via `repo push` / `repo pull`,
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
