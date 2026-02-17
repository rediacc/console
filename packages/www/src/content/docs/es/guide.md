---
title: "Guia Paso a Paso"
description: "Despliegue infraestructura cifrada y aislada en sus propios servidores usando Rediacc en modo local."
category: "Getting Started"
order: 2
language: es
---

# Guia Paso a Paso

Esta guia le muestra como desplegar infraestructura cifrada y aislada en sus propios servidores usando Rediacc en **modo local**. Al finalizar, tendra un repositorio completamente operativo ejecutando servicios en contenedores en una maquina remota, todo gestionado desde su estacion de trabajo.

El modo local significa que todo se ejecuta en infraestructura que usted controla. Sin cuentas en la nube, sin dependencias de SaaS. Su estacion de trabajo orquesta servidores remotos a traves de SSH, y todo el estado se almacena localmente en su maquina y en los propios servidores.

## Descripcion General de la Arquitectura

Rediacc utiliza una arquitectura de dos herramientas:

```
Su Estacion de Trabajo                 Servidor Remoto
┌──────────────┐        SSH        ┌──────────────────────────┐
│              │ ──────────────▶   │  renet (Go binary)       │
│  rdc (CLI)   │                   │    ├── LUKS encryption   │
│              │ ◀──────────────   │    ├── Docker daemon     │
│  config.json │    stdout/stderr  │    ├── Rediaccfile exec  │
└──────────────┘                   │    └── Traefik proxy     │
                                   └──────────────────────────┘
```

- **rdc** se ejecuta en su estacion de trabajo (macOS o Linux). Lee su configuracion local, se conecta a maquinas remotas mediante SSH e invoca comandos de renet.
- **renet** se ejecuta en el servidor remoto con privilegios de root. Gestiona imagenes de disco cifradas con LUKS, daemons Docker aislados, orquestacion de servicios y configuracion de proxy inverso.

Cada comando que escribe localmente se traduce en una llamada SSH que ejecuta renet en la maquina remota. Nunca necesitara conectarse manualmente a los servidores por SSH.

## Paso 1: Crear un Contexto Local

Un **contexto** es una configuracion con nombre que almacena sus credenciales SSH, definiciones de maquinas y mapeos de repositorios. Piense en el como un espacio de trabajo del proyecto.

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

| Opcion | Requerido | Descripcion |
|--------|-----------|-------------|
| `--ssh-key <path>` | Si | Ruta a su clave privada SSH. La tilde (`~`) se expande automaticamente. |
| `--renet-path <path>` | No | Ruta personalizada al binario renet en las maquinas remotas. Por defecto usa la ubicacion de instalacion estandar. |

Esto crea un contexto local llamado `my-infra` y lo almacena en `~/.rediacc/config.json`.

> Puede tener multiples contextos (por ejemplo, `production`, `staging`, `dev`). Cambie entre ellos con la bandera `--context` en cualquier comando.

## Paso 2: Agregar una Maquina

Registre su servidor remoto como una maquina en el contexto:

```bash
rdc context add-machine server-1 --ip 203.0.113.50 --user deploy
```

| Opcion | Requerido | Predeterminado | Descripcion |
|--------|-----------|----------------|-------------|
| `--ip <address>` | Si | - | Direccion IP o nombre de host del servidor remoto. |
| `--user <username>` | Si | - | Nombre de usuario SSH en el servidor remoto. |
| `--port <port>` | No | `22` | Puerto SSH. |
| `--datastore <path>` | No | `/mnt/rediacc` | Ruta en el servidor donde Rediacc almacena los repositorios cifrados. |

Despues de agregar la maquina, rdc ejecuta automaticamente `ssh-keyscan` para obtener las claves del host del servidor. Tambien puede ejecutar esto manualmente:

```bash
rdc context scan-keys server-1
```

Para ver todas las maquinas registradas:

```bash
rdc context machines
```

## Paso 3: Configurar la Maquina

Aprovisione el servidor remoto con todas las dependencias requeridas:

```bash
rdc context setup-machine server-1
```

Este comando:
1. Sube el binario renet al servidor mediante SFTP
2. Instala Docker, containerd y cryptsetup (si no estan presentes)
3. Crea el directorio del datastore y lo prepara para repositorios cifrados

| Opcion | Requerido | Predeterminado | Descripcion |
|--------|-----------|----------------|-------------|
| `--datastore <path>` | No | `/mnt/rediacc` | Directorio del datastore en el servidor. |
| `--datastore-size <size>` | No | `95%` | Cantidad de disco disponible a asignar para el datastore. |
| `--debug` | No | `false` | Habilitar salida detallada para resolucion de problemas. |

> La configuracion solo necesita ejecutarse una vez por maquina. Es seguro volver a ejecutarla si es necesario.

## Paso 4: Crear un Repositorio

Un **repositorio** es una imagen de disco cifrada con LUKS en el servidor remoto. Cuando se monta, proporciona:
- Un sistema de archivos aislado para los datos de su aplicacion
- Un daemon Docker dedicado (separado del Docker del host)
- IPs de loopback unicas para cada servicio dentro de una subred /26

Cree un repositorio:

```bash
rdc repo create my-app -m server-1 --size 10G
```

| Opcion | Requerido | Descripcion |
|--------|-----------|-------------|
| `-m, --machine <name>` | Si | Maquina destino donde se creara el repositorio. |
| `--size <size>` | Si | Tamano de la imagen de disco cifrada (por ejemplo, `5G`, `10G`, `50G`). |

La salida mostrara tres valores generados automaticamente:

- **GUID del Repositorio** -- Un UUID que identifica la imagen de disco cifrada en el servidor.
- **Credencial** -- Una frase de contrasena aleatoria utilizada para cifrar/descifrar el volumen LUKS.
- **ID de Red** -- Un numero entero (comenzando en 2816, incrementando en 64) que determina la subred IP para los servicios de este repositorio.

> **Almacene la credencial de forma segura.** Es la clave de cifrado de su repositorio. Si se pierde, los datos no se pueden recuperar. La credencial se almacena en su `config.json` local pero no se almacena en el servidor.

## Paso 5: El Rediaccfile

El **Rediaccfile** es un script Bash que define como se preparan, inician y detienen sus servicios. Es el mecanismo principal para la gestion del ciclo de vida de los servicios.

### Que es un Rediaccfile?

Un Rediaccfile es un script Bash simple que contiene hasta tres funciones: `prep()`, `up()` y `down()`. Debe llamarse `Rediaccfile` o `rediaccfile` (insensible a mayusculas) y colocarse dentro del sistema de archivos montado del repositorio.

Los Rediaccfiles se descubren en dos ubicaciones:
1. La **raiz** de la ruta de montaje del repositorio
2. **Subdirectorios de primer nivel** de la ruta de montaje (no recursivo)

Los directorios ocultos (nombres que comienzan con `.`) se omiten.

### Funciones del Ciclo de Vida

| Funcion | Cuando se ejecuta | Proposito | Comportamiento en caso de error |
|---------|-------------------|-----------|--------------------------------|
| `prep()` | Antes de `up()` | Instalar dependencias, descargar imagenes, ejecutar migraciones | **Fallo rapido** -- si algun `prep()` falla, todo el proceso se detiene inmediatamente. |
| `up()` | Despues de que todos los `prep()` se completen | Iniciar servicios (por ejemplo, `docker compose up -d`) | La falla del Rediaccfile raiz es **critica** (detiene todo). Las fallas en subdirectorios son **no criticas** (se registran, continua al siguiente). |
| `down()` | Al detener | Detener servicios (por ejemplo, `docker compose down`) | **Mejor esfuerzo** -- las fallas se registran pero siempre se intentan todos los Rediaccfiles. |

Las tres funciones son opcionales. Si una funcion no esta definida en un Rediaccfile, se omite silenciosamente.

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

Las variables `{SERVICE}_IP` se generan automaticamente a partir de `.rediacc.json` (ver Paso 6). La convencion de nomenclatura convierte el nombre del servicio a mayusculas con guiones reemplazados por guiones bajos, y luego agrega `_IP`. Por ejemplo, `listmonk-app` se convierte en `LISTMONK_APP_IP`.

### Ejemplo de Rediaccfile

Un Rediaccfile simple para una aplicacion web:

```bash
#!/bin/bash

prep() {
    echo "Pulling latest images..."
    docker compose pull
}

up() {
    echo "Starting services..."
    docker compose up -d
}

down() {
    echo "Stopping services..."
    docker compose down
}
```

### Ejemplo Multi-Servicio

Para proyectos con multiples grupos de servicios independientes, use subdirectorios:

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # Raiz: configuracion compartida (ej., crear redes Docker)
├── docker-compose.yml       # Archivo compose raiz
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

## Paso 6: Red de Servicios (.rediacc.json)

Cada repositorio obtiene una subred /26 (64 IPs) en el rango de loopback `127.x.x.x`. Los servicios se vinculan a IPs de loopback unicas para que puedan ejecutarse en los mismos puertos sin conflictos. Por ejemplo, dos instancias de PostgreSQL pueden escuchar en el puerto 5432, cada una en una IP diferente.

### El Archivo .rediacc.json

El archivo `.rediacc.json` mapea nombres de servicios a numeros de **slot**. Cada slot corresponde a una direccion IP unica dentro de la subred del repositorio.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

Los servicios se escriben en orden alfabetico.

### Generacion Automatica desde Docker Compose

No necesita crear `.rediacc.json` manualmente. Cuando ejecuta `rdc repo up`, Rediacc automaticamente:

1. Escanea todos los directorios que contienen un Rediaccfile en busca de archivos compose (`docker-compose.yml`, `docker-compose.yaml`, `compose.yml` o `compose.yaml`).
2. Extrae los nombres de servicio de la seccion `services:` de cada archivo compose.
3. Asigna el siguiente slot disponible a cualquier servicio nuevo.
4. Guarda el resultado en `{repository}/.rediacc.json`.

### Calculo de IP

La IP de un servicio se calcula a partir del ID de red del repositorio y el slot del servicio. El ID de red se distribuye entre el segundo, tercer y cuarto octeto de una direccion de loopback `127.x.y.z`. Cada servicio recibe un desplazamiento de `slot + 2` sumado al ID de red (los desplazamientos 0 y 1 estan reservados para la direccion de red y la puerta de enlace).

Por ejemplo, con el ID de red `2816` (`0x0B00`), la direccion base es `127.0.11.0` y los servicios comienzan en `127.0.11.2`.

**Ejemplo** para ID de red `2816`:

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

Las variables `${POSTGRES_IP}` y `${API_IP}` se exportan automaticamente desde `.rediacc.json` cuando se ejecuta el Rediaccfile.

## Paso 7: Iniciar Servicios

Monte el repositorio e inicie todos los servicios:

```bash
rdc repo up my-app -m server-1 --mount
```

| Opcion | Requerido | Descripcion |
|--------|-----------|-------------|
| `-m, --machine <name>` | Si | Maquina destino. |
| `--mount` | No | Montar el repositorio primero si no esta montado. Sin esta bandera, el repositorio ya debe estar montado. |
| `--prep-only` | No | Ejecutar solo las funciones `prep()`, omitir `up()`. Util para pre-descargar imagenes o ejecutar migraciones. |

La secuencia de ejecucion es:

1. Montar el repositorio cifrado con LUKS (si se especifica `--mount`)
2. Iniciar el daemon Docker aislado para este repositorio
3. Generar automaticamente `.rediacc.json` a partir de archivos compose
4. Ejecutar `prep()` en todos los Rediaccfiles (orden A-Z, fallo rapido)
5. Ejecutar `up()` en todos los Rediaccfiles (orden A-Z)

## Paso 8: Detener Servicios

Detenga todos los servicios en un repositorio:

```bash
rdc repo down my-app -m server-1
```

| Opcion | Requerido | Descripcion |
|--------|-----------|-------------|
| `-m, --machine <name>` | Si | Maquina destino. |
| `--unmount` | No | Desmontar el repositorio cifrado despues de detener los servicios. Esto tambien detiene el daemon Docker aislado y cierra el volumen LUKS. |

La secuencia de ejecucion es:

1. Ejecutar `down()` en todos los Rediaccfiles (orden inverso Z-A, mejor esfuerzo)
2. Detener el daemon Docker aislado (si se usa `--unmount`)
3. Desmontar y cerrar el volumen cifrado con LUKS (si se usa `--unmount`)

## Otras Operaciones Comunes

### Montar y Desmontar (sin iniciar servicios)

```bash
rdc repo mount my-app -m server-1     # Descifrar y montar
rdc repo unmount my-app -m server-1   # Desmontar y re-cifrar
```

### Verificar Estado del Repositorio

```bash
rdc repo status my-app -m server-1
```

### Listar Todos los Repositorios

```bash
rdc repo list -m server-1
```

### Redimensionar un Repositorio

```bash
rdc repo resize my-app -m server-1 --size 20G    # Establecer tamano exacto
rdc repo expand my-app -m server-1 --size 5G      # Agregar 5G al tamano actual
```

### Eliminar un Repositorio

```bash
rdc repo delete my-app -m server-1
```

> Esto destruye permanentemente la imagen de disco cifrada y todos los datos dentro de ella.

### Bifurcar un Repositorio

Cree una copia de un repositorio existente en su estado actual:

```bash
rdc repo fork my-app -m server-1 --tag my-app-staging
```

Esto crea una nueva copia cifrada con su propio GUID e ID de red. La bifurcacion comparte la misma credencial LUKS que el repositorio padre.

### Validar un Repositorio

Verifique la integridad del sistema de archivos de un repositorio:

```bash
rdc repo validate my-app -m server-1
```

## Ejemplo Completo: Desplegar una Aplicacion Web

Este ejemplo de extremo a extremo despliega una aplicacion web con PostgreSQL, Redis y un servidor API.

### 1. Configurar el Entorno

```bash
# Instalar rdc
curl -fsSL https://get.rediacc.com | sh

# Crear un contexto local
rdc context create-local production --ssh-key ~/.ssh/id_ed25519

# Registrar su servidor
rdc context add-machine prod-1 --ip 203.0.113.50 --user deploy

# Aprovisionar el servidor
rdc context setup-machine prod-1

# Crear un repositorio cifrado (10 GB)
rdc repo create webapp -m prod-1 --size 10G
```

### 2. Montar y Preparar el Repositorio

```bash
rdc repo mount webapp -m prod-1
```

Conectese por SSH al servidor y cree los archivos de la aplicacion dentro del repositorio montado. La ruta de montaje se muestra en la salida (tipicamente `/mnt/rediacc/repos/{guid}`).

### 3. Crear los Archivos de la Aplicacion

Dentro del repositorio, cree los siguientes archivos:

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
    echo "Creating data directories..."
    mkdir -p data/postgres

    echo "Pulling images..."
    docker compose pull
}

up() {
    echo "Starting webapp services..."
    docker compose up -d

    echo "Waiting for PostgreSQL to be ready..."
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
    echo "Stopping webapp services..."
    docker compose down
}
```

### 4. Iniciar Todo

```bash
rdc repo up webapp -m prod-1
```

Esto hara lo siguiente:
1. Generar automaticamente `.rediacc.json` con slots para `api`, `postgres` y `redis`
2. Ejecutar `prep()` para crear directorios y descargar imagenes
3. Ejecutar `up()` para iniciar todos los contenedores

### 5. Habilitar Inicio Automatico

```bash
rdc repo autostart enable webapp -m prod-1
```

Despues de reiniciar el servidor, el repositorio se montara automaticamente e iniciara todos los servicios.
