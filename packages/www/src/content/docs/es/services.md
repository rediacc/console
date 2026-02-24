---
title: Servicios
description: >-
  Despliegue y gestione servicios en contenedores usando Rediaccfiles, red de
  servicios e inicio automático.
category: Guides
order: 5
language: es
sourceHash: 294f92dc32f10c86
---

# Servicios

Si no tienes claro qué herramienta usar, consulta [rdc vs renet](/es/docs/rdc-vs-renet).

Esta página cubre cómo desplegar y gestionar servicios en contenedores: Rediaccfiles, red de servicios, inicio/detención, operaciones masivas e inicio automático.

## El Rediaccfile

El **Rediaccfile** es un script Bash que define cómo se preparan, inician y detienen sus servicios. Debe llamarse `Rediaccfile` o `rediaccfile` (insensible a mayúsculas) y colocarse dentro del sistema de archivos montado del repositorio.

Los Rediaccfiles se descubren en dos ubicaciones:
1. La **raíz** de la ruta de montaje del repositorio
2. **Subdirectorios de primer nivel** de la ruta de montaje (no recursivo)

Los directorios ocultos (nombres que comienzan con `.`) se omiten.

### Funciones del Ciclo de Vida

Un Rediaccfile contiene hasta tres funciones:

| Función | Cuándo se ejecuta | Propósito | Comportamiento en caso de error |
|---------|-------------------|-----------|--------------------------------|
| `prep()` | Antes de `up()` | Instalar dependencias, descargar imágenes, ejecutar migraciones | **Fallo rápido** -- si algún `prep()` falla, todo el proceso se detiene inmediatamente |
| `up()` | Después de que todos los `prep()` se completen | Iniciar servicios (por ejemplo, `docker compose up -d`) | La falla del Rediaccfile raíz es **crítica** (detiene todo). Las fallas en subdirectorios son **no críticas** (se registran, continúa al siguiente) |
| `down()` | Al detener | Detener servicios (por ejemplo, `docker compose down`) | **Mejor esfuerzo** -- las fallas se registran pero siempre se intentan todos los Rediaccfiles |

Las tres funciones son opcionales. Si una función no está definida, se omite silenciosamente.

### Orden de Ejecución

- **Inicio (`up`):** Primero el Rediaccfile raíz, luego los subdirectorios en **orden alfabético** (A a Z).
- **Detención (`down`):** Subdirectorios en **orden alfabético inverso** (Z a A), luego el raíz al final.

### Variables de Entorno

Cuando se ejecuta una función del Rediaccfile, las siguientes variables de entorno están disponibles:

| Variable | Descripción | Ejemplo |
|----------|-------------|---------|
| `REPOSITORY_PATH` | Ruta de montaje del repositorio | `/mnt/rediacc/repos/abc123` |
| `REPOSITORY_NAME` | GUID del repositorio | `a1b2c3d4-e5f6-...` |
| `REPOSITORY_NETWORK_ID` | ID de red (entero) | `2816` |
| `DOCKER_HOST` | Socket Docker del daemon aislado de este repositorio | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | IP de loopback para cada servicio definido en `.rediacc.json` | `POSTGRES_IP=127.0.11.2` |

Las variables `{SERVICE}_IP` se generan automáticamente a partir de `.rediacc.json`. La convención de nomenclatura convierte el nombre del servicio a mayúsculas con guiones reemplazados por guiones bajos, y luego agrega `_IP`. Por ejemplo, `listmonk-app` se convierte en `LISTMONK_APP_IP`.

> **Advertencia: No use `sudo docker` en los Rediaccfiles.** El comando `sudo` restablece las variables de entorno, lo que significa que `DOCKER_HOST` se pierde y los comandos de Docker apuntarán al daemon del sistema en lugar del daemon aislado del repositorio. Esto rompe el aislamiento de contenedores y puede causar conflictos de puertos. Rediacc bloqueará la ejecución si detecta `sudo docker` sin `-E`.
>
> Use `renet compose` en sus Rediaccfiles -- automáticamente gestiona `DOCKER_HOST`, inyecta etiquetas de red para el descubrimiento de rutas y configura la red de servicios. Consulte [Red](/es/docs/networking) para detalles sobre cómo se exponen los servicios a través del proxy inverso. Si llama a Docker directamente, use `docker` sin `sudo` -- las funciones del Rediaccfile ya se ejecutan con privilegios suficientes. Si debe usar sudo, use `sudo -E docker` para preservar las variables de entorno.

### Ejemplo

```bash
#!/bin/bash

prep() {
    echo "Pulling latest images..."
    renet compose -- pull
}

up() {
    echo "Starting services..."
    renet compose -- up -d
}

down() {
    echo "Stopping services..."
    renet compose -- down
}
```

> `docker compose` también funciona ya que `DOCKER_HOST` se configura automáticamente, pero se prefiere `renet compose` porque adicionalmente inyecta las etiquetas `rediacc.*` necesarias para el descubrimiento de rutas del proxy inverso. Consulte [Red](/es/docs/networking) para más detalles.

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

Dado que cada repositorio ejecuta un daemon Docker aislado, los servicios usan `network_mode: host` y se vinculan a sus IPs de loopback asignadas:

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    environment:
      PGDATA: /var/lib/postgresql/data
      POSTGRES_PASSWORD: secret
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  api:
    image: my-api:latest
    network_mode: host
    environment:
      DATABASE_URL: postgresql://postgres:secret@${POSTGRES_IP}:5432/mydb
      LISTEN_ADDR: ${API_IP}:8080
```

## Iniciar Servicios

Monte el repositorio e inicie todos los servicios:

```bash
rdc repo up my-app -m server-1 --mount
```

| Opción | Descripción |
|--------|-------------|
| `--mount` | Montar el repositorio primero si no está montado |
| `--prep-only` | Ejecutar solo las funciones `prep()`, omitir `up()` |
| `--skip-router-restart` | Omitir el reinicio del servidor de rutas después de la operación |

La secuencia de ejecución es:
1. Montar el repositorio cifrado con LUKS (si se especifica `--mount`)
2. Iniciar el daemon Docker aislado
3. Generar automáticamente `.rediacc.json` a partir de archivos compose
4. Ejecutar `prep()` en todos los Rediaccfiles (orden A-Z, fallo rápido)
5. Ejecutar `up()` en todos los Rediaccfiles (orden A-Z)

## Detener Servicios

```bash
rdc repo down my-app -m server-1
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
rdc repo up-all -m server-1
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
rdc repo autostart enable my-app -m server-1
```

Se le solicitará la frase de contraseña del repositorio.

### Habilitar Todos

```bash
rdc repo autostart enable-all -m server-1
```

### Deshabilitar

```bash
rdc repo autostart disable my-app -m server-1
```

Esto elimina el archivo de clave y destruye el slot 1 de LUKS.

### Listar Estado

```bash
rdc repo autostart list -m server-1
```

## Ejemplo Completo

Este ejemplo despliega una aplicación web con PostgreSQL, Redis y un servidor API.

### 1. Configurar

```bash
curl -fsSL https://get.rediacc.com | sh
rdc config init production --ssh-key ~/.ssh/id_ed25519
rdc config add-machine prod-1 --ip 203.0.113.50 --user deploy
rdc config setup-machine prod-1
rdc repo create webapp -m prod-1 --size 10G
```

### 2. Montar y Preparar

```bash
rdc repo mount webapp -m prod-1
```

### 3. Crear los Archivos de la Aplicación

Dentro del repositorio, cree:

**docker-compose.yml:**

```yaml
services:
  postgres:
    image: postgres:16
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: webapp
      POSTGRES_USER: app
      POSTGRES_PASSWORD: changeme
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  redis:
    image: redis:7-alpine
    network_mode: host
    restart: unless-stopped
    command: redis-server --bind ${REDIS_IP} --port 6379

  api:
    image: myregistry/api:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://app:changeme@${POSTGRES_IP}:5432/webapp
      REDIS_URL: redis://${REDIS_IP}:6379
      LISTEN_ADDR: ${API_IP}:8080
```

**Rediaccfile:**

```bash
#!/bin/bash

prep() {
    mkdir -p data/postgres
    renet compose -- pull
}

up() {
    renet compose -- up -d

    echo "Waiting for PostgreSQL..."
    for i in $(seq 1 30); do
        if docker compose exec postgres pg_isready -q 2>/dev/null; then
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
rdc repo up webapp -m prod-1
```

### 5. Habilitar Inicio Automático

```bash
rdc repo autostart enable webapp -m prod-1
```
