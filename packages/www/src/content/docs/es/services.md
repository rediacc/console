---
title: "Servicios"
description: "Despliegue y gestione servicios en contenedores usando Rediaccfiles, red de servicios e inicio automatico."
category: "Guides"
order: 5
language: es
---

# Servicios

Esta pagina cubre como desplegar y gestionar servicios en contenedores: Rediaccfiles, red de servicios, inicio/detencion, operaciones masivas e inicio automatico.

## El Rediaccfile

El **Rediaccfile** es un script Bash que define como se preparan, inician y detienen sus servicios. Debe llamarse `Rediaccfile` o `rediaccfile` (insensible a mayusculas) y colocarse dentro del sistema de archivos montado del repositorio.

Los Rediaccfiles se descubren en dos ubicaciones:
1. La **raiz** de la ruta de montaje del repositorio
2. **Subdirectorios de primer nivel** de la ruta de montaje (no recursivo)

Los directorios ocultos (nombres que comienzan con `.`) se omiten.

### Funciones del Ciclo de Vida

Un Rediaccfile contiene hasta tres funciones:

| Funcion | Cuando se ejecuta | Proposito | Comportamiento en caso de error |
|---------|-------------------|-----------|--------------------------------|
| `prep()` | Antes de `up()` | Instalar dependencias, descargar imagenes, ejecutar migraciones | **Fallo rapido** -- si algun `prep()` falla, todo el proceso se detiene inmediatamente |
| `up()` | Despues de que todos los `prep()` se completen | Iniciar servicios (por ejemplo, `docker compose up -d`) | La falla del Rediaccfile raiz es **critica** (detiene todo). Las fallas en subdirectorios son **no criticas** (se registran, continua al siguiente) |
| `down()` | Al detener | Detener servicios (por ejemplo, `docker compose down`) | **Mejor esfuerzo** -- las fallas se registran pero siempre se intentan todos los Rediaccfiles |

Las tres funciones son opcionales. Si una funcion no esta definida, se omite silenciosamente.

### Orden de Ejecucion

- **Inicio (`up`):** Primero el Rediaccfile raiz, luego los subdirectorios en **orden alfabetico** (A a Z).
- **Detencion (`down`):** Subdirectorios en **orden alfabetico inverso** (Z a A), luego el raiz al final.

### Variables de Entorno

Cuando se ejecuta una funcion del Rediaccfile, las siguientes variables de entorno estan disponibles:

| Variable | Descripcion | Ejemplo |
|----------|-------------|---------|
| `REPOSITORY_PATH` | Ruta de montaje del repositorio | `/mnt/rediacc/repos/abc123` |
| `REPOSITORY_NAME` | GUID del repositorio | `a1b2c3d4-e5f6-...` |
| `REPOSITORY_NETWORK_ID` | ID de red (entero) | `2816` |
| `DOCKER_HOST` | Socket Docker del daemon aislado de este repositorio | `unix:///var/run/rediacc/docker-2816.sock` |
| `{SERVICE}_IP` | IP de loopback para cada servicio definido en `.rediacc.json` | `POSTGRES_IP=127.0.11.2` |

Las variables `{SERVICE}_IP` se generan automaticamente a partir de `.rediacc.json`. La convencion de nomenclatura convierte el nombre del servicio a mayusculas con guiones reemplazados por guiones bajos, y luego agrega `_IP`. Por ejemplo, `listmonk-app` se convierte en `LISTMONK_APP_IP`.

> **Advertencia: No use `sudo docker` en los Rediaccfiles.** El comando `sudo` restablece las variables de entorno, lo que significa que `DOCKER_HOST` se pierde y los comandos de Docker apuntaran al daemon del sistema en lugar del daemon aislado del repositorio. Esto rompe el aislamiento de contenedores y puede causar conflictos de puertos. Rediacc bloqueara la ejecucion si detecta `sudo docker` sin `-E`.
>
> Use `renet compose` en sus Rediaccfiles -- automaticamente gestiona `DOCKER_HOST`, inyecta etiquetas de red para el descubrimiento de rutas y configura la red de servicios. Consulte [Red](/es/docs/networking) para detalles sobre como se exponen los servicios a traves del proxy inverso. Si llama a Docker directamente, use `docker` sin `sudo` -- las funciones del Rediaccfile ya se ejecutan con privilegios suficientes. Si debe usar sudo, use `sudo -E docker` para preservar las variables de entorno.

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

> `docker compose` tambien funciona ya que `DOCKER_HOST` se configura automaticamente, pero se prefiere `renet compose` porque adicionalmente inyecta las etiquetas `rediacc.*` necesarias para el descubrimiento de rutas del proxy inverso. Consulte [Red](/es/docs/networking) para mas detalles.

### Diseno Multi-Servicio

Para proyectos con multiples grupos de servicios independientes, use subdirectorios:

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # Raiz: configuracion compartida
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

Orden de ejecucion para `up`: raiz, luego `backend`, `database`, `monitoring` (A-Z).
Orden de ejecucion para `down`: `monitoring`, `database`, `backend`, luego raiz (Z-A).

## Red de Servicios (.rediacc.json)

Cada repositorio obtiene una subred /26 (64 IPs) en el rango de loopback `127.x.x.x`. Los servicios se vinculan a IPs de loopback unicas para que puedan ejecutarse en los mismos puertos sin conflictos.

### El Archivo .rediacc.json

Mapea nombres de servicios a numeros de **slot**. Cada slot corresponde a una direccion IP unica dentro de la subred del repositorio.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

### Generacion Automatica desde Docker Compose

No necesita crear `.rediacc.json` manualmente. Cuando ejecuta `rdc repo up`, Rediacc automaticamente:

1. Escanea todos los directorios que contienen un Rediaccfile en busca de archivos compose (`docker-compose.yml`, `docker-compose.yaml`, `compose.yml` o `compose.yaml`)
2. Extrae los nombres de servicio de la seccion `services:`
3. Asigna el siguiente slot disponible a cualquier servicio nuevo
4. Guarda el resultado en `{repository}/.rediacc.json`

### Calculo de IP

La IP de un servicio se calcula a partir del ID de red del repositorio y el slot del servicio. El ID de red se distribuye entre el segundo, tercer y cuarto octeto de una direccion de loopback `127.x.y.z`. Cada servicio recibe un desplazamiento de `slot + 2` (los desplazamientos 0 y 1 estan reservados).

**Ejemplo** para ID de red `2816` (`0x0B00`), direccion base `127.0.11.0`:

| Servicio | Slot | Direccion IP |
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

| Opcion | Descripcion |
|--------|-------------|
| `--mount` | Montar el repositorio primero si no esta montado |
| `--prep-only` | Ejecutar solo las funciones `prep()`, omitir `up()` |

La secuencia de ejecucion es:
1. Montar el repositorio cifrado con LUKS (si se especifica `--mount`)
2. Iniciar el daemon Docker aislado
3. Generar automaticamente `.rediacc.json` a partir de archivos compose
4. Ejecutar `prep()` en todos los Rediaccfiles (orden A-Z, fallo rapido)
5. Ejecutar `up()` en todos los Rediaccfiles (orden A-Z)

## Detener Servicios

```bash
rdc repo down my-app -m server-1
```

| Opcion | Descripcion |
|--------|-------------|
| `--unmount` | Desmontar el repositorio cifrado despues de detener los servicios |

La secuencia de ejecucion es:
1. Ejecutar `down()` en todos los Rediaccfiles (orden inverso Z-A, mejor esfuerzo)
2. Detener el daemon Docker aislado (si se usa `--unmount`)
3. Desmontar y cerrar el volumen cifrado con LUKS (si se usa `--unmount`)

## Operaciones Masivas

Inicie o detenga todos los repositorios en una maquina a la vez:

```bash
rdc repo up-all -m server-1
```

| Opcion | Descripcion |
|--------|-------------|
| `--include-forks` | Incluir repositorios bifurcados |
| `--mount-only` | Solo montar, no iniciar contenedores |
| `--dry-run` | Mostrar lo que se haria |
| `--parallel` | Ejecutar operaciones en paralelo |
| `--concurrency <n>` | Maximo de operaciones concurrentes (predeterminado: 3) |

## Inicio Automatico al Arranque

Por defecto, los repositorios deben montarse e iniciarse manualmente despues de reiniciar el servidor. El **inicio automatico** configura los repositorios para montarse automaticamente, iniciar Docker y ejecutar el `up()` del Rediaccfile cuando el servidor arranca.

### Como Funciona

Cuando habilita el inicio automatico para un repositorio:

1. Se genera un archivo de clave LUKS aleatorio de 256 bytes y se agrega al slot 1 de LUKS del repositorio (el slot 0 permanece como la frase de contrasena del usuario)
2. El archivo de clave se almacena en `{datastore}/.credentials/keys/{guid}.key` con permisos `0600` (solo root)
3. Se instala un servicio systemd (`rediacc-autostart`) que se ejecuta al arranque para montar todos los repositorios habilitados e iniciar sus servicios

Al apagar, el servicio detiene graciosamente todos los servicios (`down()` del Rediaccfile), detiene los daemons Docker y cierra los volumenes LUKS.

> **Nota de seguridad:** Habilitar el inicio automatico almacena un archivo de clave LUKS en el disco del servidor. Cualquier persona con acceso root al servidor puede montar el repositorio sin la frase de contrasena. Evalue esto segun su modelo de amenazas.

### Habilitar

```bash
rdc repo autostart enable my-app -m server-1
```

Se le solicitara la frase de contrasena del repositorio.

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

Este ejemplo despliega una aplicacion web con PostgreSQL, Redis y un servidor API.

### 1. Configurar

```bash
curl -fsSL https://get.rediacc.com | sh
rdc context create-local production --ssh-key ~/.ssh/id_ed25519
rdc context add-machine prod-1 --ip 203.0.113.50 --user deploy
rdc context setup-machine prod-1
rdc repo create webapp -m prod-1 --size 10G
```

### 2. Montar y Preparar

```bash
rdc repo mount webapp -m prod-1
```

### 3. Crear los Archivos de la Aplicacion

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

### 5. Habilitar Inicio Automatico

```bash
rdc repo autostart enable webapp -m prod-1
```
