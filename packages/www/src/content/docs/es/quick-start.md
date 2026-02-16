---
title: "Guía de Inicio Rápido"
description: "Guía paso a paso para desplegar infraestructura cifrada y aislada en sus propios servidores usando Rediacc en modo local."
category: "Core Concepts"
order: 0
language: es
---

# Guía de Inicio Rápido

Esta guía le muestra cómo desplegar infraestructura cifrada y aislada en sus propios servidores usando Rediacc en **modo local**. Al finalizar, tendrá un repositorio completamente operativo ejecutando servicios en contenedores en una máquina remota, todo gestionado desde su estación de trabajo.

El modo local significa que todo se ejecuta en infraestructura que usted controla. Sin cuentas en la nube, sin dependencias de SaaS. Su estación de trabajo orquesta servidores remotos a través de SSH, y todo el estado se almacena localmente en su máquina y en los propios servidores.

## Descripción General de la Arquitectura

Rediacc utiliza una arquitectura de dos herramientas:

```
Su Estación de Trabajo                 Servidor Remoto
┌──────────────┐        SSH        ┌──────────────────────────┐
│              │ ──────────────▶   │  renet (binario Go)      │
│  rdc (CLI)   │                   │    ├── Cifrado LUKS      │
│              │ ◀──────────────   │    ├── Daemon Docker      │
│  config.json │    stdout/stderr  │    ├── Ejec. Rediaccfile  │
└──────────────┘                   │    └── Proxy Traefik      │
                                   └──────────────────────────┘
```

- **rdc** se ejecuta en su estación de trabajo (macOS o Linux). Lee su configuración local, se conecta a máquinas remotas mediante SSH e invoca comandos de renet.
- **renet** se ejecuta en el servidor remoto con privilegios de root. Gestiona imágenes de disco cifradas con LUKS, daemons Docker aislados, orquestación de servicios y configuración de proxy inverso.

Cada comando que escribe localmente se traduce en una llamada SSH que ejecuta renet en la máquina remota. Nunca necesitará conectarse manualmente a los servidores por SSH.

## Lo Que Necesitará

Antes de comenzar, asegúrese de tener lo siguiente:

**En su estación de trabajo:**
- macOS o Linux con un cliente SSH
- Un par de claves SSH (por ejemplo, `~/.ssh/id_ed25519` o `~/.ssh/id_rsa`)

**En el servidor remoto:**
- Ubuntu 20.04+ o Debian 11+ (otras distribuciones de Linux pueden funcionar pero no están probadas)
- Una cuenta de usuario con privilegios de `sudo`
- Su clave pública SSH agregada a `~/.ssh/authorized_keys`
- Al menos 20 GB de espacio libre en disco (más dependiendo de sus cargas de trabajo)

## Paso 1: Instalar rdc

Instale la CLI de Rediacc en su estación de trabajo:

```bash
curl -fsSL https://get.rediacc.com | sh
```

Esto descarga el binario `rdc` en `$HOME/.local/bin/`. Asegúrese de que este directorio esté en su PATH. Verifique la instalación:

```bash
rdc --help
```

> Para actualizar posteriormente, ejecute `rdc update`.

## Paso 2: Crear un Contexto Local

Un **contexto** es una configuración con nombre que almacena sus credenciales SSH, definiciones de máquinas y mapeos de repositorios. Piense en él como un espacio de trabajo del proyecto.

```bash
rdc context create-local my-infra --ssh-key ~/.ssh/id_ed25519
```

| Opción | Requerido | Descripción |
|--------|-----------|-------------|
| `--ssh-key <path>` | Sí | Ruta a su clave privada SSH. La tilde (`~`) se expande automáticamente. |
| `--renet-path <path>` | No | Ruta personalizada al binario renet en las máquinas remotas. Por defecto usa la ubicación de instalación estándar. |

Esto crea un contexto local llamado `my-infra` y lo almacena en `~/.rediacc/config.json`.

> Puede tener múltiples contextos (por ejemplo, `production`, `staging`, `dev`). Cambie entre ellos con la bandera `--context` en cualquier comando.

## Paso 3: Agregar una Máquina

Registre su servidor remoto como una máquina en el contexto:

```bash
rdc context add-machine server-1 --ip 203.0.113.50 --user deploy
```

| Opción | Requerido | Predeterminado | Descripción |
|--------|-----------|----------------|-------------|
| `--ip <address>` | Sí | - | Dirección IP o nombre de host del servidor remoto. |
| `--user <username>` | Sí | - | Nombre de usuario SSH en el servidor remoto. |
| `--port <port>` | No | `22` | Puerto SSH. |
| `--datastore <path>` | No | `/mnt/rediacc` | Ruta en el servidor donde Rediacc almacena los repositorios cifrados. |

Después de agregar la máquina, rdc ejecuta automáticamente `ssh-keyscan` para obtener las claves del host del servidor. También puede ejecutar esto manualmente:

```bash
rdc context scan-keys server-1
```

Para ver todas las máquinas registradas:

```bash
rdc context machines
```

## Paso 4: Configurar la Máquina

Aprovisione el servidor remoto con todas las dependencias requeridas:

```bash
rdc context setup-machine server-1
```

Este comando:
1. Sube el binario renet al servidor mediante SFTP
2. Instala Docker, containerd y cryptsetup (si no están presentes)
3. Crea el directorio del datastore y lo prepara para repositorios cifrados

| Opción | Requerido | Predeterminado | Descripción |
|--------|-----------|----------------|-------------|
| `--datastore <path>` | No | `/mnt/rediacc` | Directorio del datastore en el servidor. |
| `--datastore-size <size>` | No | `95%` | Cantidad de disco disponible a asignar para el datastore. |
| `--debug` | No | `false` | Habilitar salida detallada para resolución de problemas. |

> La configuración solo necesita ejecutarse una vez por máquina. Es seguro volver a ejecutarla si es necesario.

## Paso 5: Crear un Repositorio

Un **repositorio** es una imagen de disco cifrada con LUKS en el servidor remoto. Cuando se monta, proporciona:
- Un sistema de archivos aislado para los datos de su aplicación
- Un daemon Docker dedicado (separado del Docker del host)
- IPs de loopback únicas para cada servicio dentro de una subred /26

Cree un repositorio:

```bash
rdc repo create my-app -m server-1 --size 10G
```

| Opción | Requerido | Descripción |
|--------|-----------|-------------|
| `-m, --machine <name>` | Sí | Máquina destino donde se creará el repositorio. |
| `--size <size>` | Sí | Tamaño de la imagen de disco cifrada (por ejemplo, `5G`, `10G`, `50G`). |

La salida mostrará tres valores generados automáticamente:

- **GUID del Repositorio** -- Un UUID que identifica la imagen de disco cifrada en el servidor.
- **Credencial** -- Una frase de contraseña aleatoria utilizada para cifrar/descifrar el volumen LUKS.
- **ID de Red** -- Un número entero (comenzando en 2816, incrementando en 64) que determina la subred IP para los servicios de este repositorio.

> **Almacene la credencial de forma segura.** Es la clave de cifrado de su repositorio. Si se pierde, los datos no se pueden recuperar. La credencial se almacena en su `config.json` local pero no se almacena en el servidor.

## Paso 6: El Rediaccfile

El **Rediaccfile** es un script Bash que define cómo se preparan, inician y detienen sus servicios. Es el mecanismo principal para la gestión del ciclo de vida de los servicios.

### ¿Qué es un Rediaccfile?

Un Rediaccfile es un script Bash simple que contiene hasta tres funciones: `prep()`, `up()` y `down()`. Debe llamarse `Rediaccfile` o `rediaccfile` (insensible a mayúsculas) y colocarse dentro del sistema de archivos montado del repositorio.

Los Rediaccfiles se descubren en dos ubicaciones:
1. La **raíz** de la ruta de montaje del repositorio
2. **Subdirectorios de primer nivel** de la ruta de montaje (no recursivo)

Los directorios ocultos (nombres que comienzan con `.`) se omiten.

### Funciones del Ciclo de Vida

| Función | Cuándo se ejecuta | Propósito | Comportamiento en caso de error |
|---------|-------------------|-----------|--------------------------------|
| `prep()` | Antes de `up()` | Instalar dependencias, descargar imágenes, ejecutar migraciones | **Fallo rápido** -- si algún `prep()` falla, todo el proceso se detiene inmediatamente. |
| `up()` | Después de que todos los `prep()` se completen | Iniciar servicios (por ejemplo, `docker compose up -d`) | La falla del Rediaccfile raíz es **crítica** (detiene todo). Las fallas en subdirectorios son **no críticas** (se registran, continúa al siguiente). |
| `down()` | Al detener | Detener servicios (por ejemplo, `docker compose down`) | **Mejor esfuerzo** -- las fallas se registran pero siempre se intentan todos los Rediaccfiles. |

Las tres funciones son opcionales. Si una función no está definida en un Rediaccfile, se omite silenciosamente.

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

Las variables `{SERVICE}_IP` se generan automáticamente a partir de `.rediacc.json` (ver Paso 7). La convención de nomenclatura convierte el nombre del servicio a mayúsculas con guiones reemplazados por guiones bajos, y luego agrega `_IP`. Por ejemplo, `listmonk-app` se convierte en `LISTMONK_APP_IP`.

### Ejemplo de Rediaccfile

Un Rediaccfile simple para una aplicación web:

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

Para proyectos con múltiples grupos de servicios independientes, use subdirectorios:

```
/mnt/rediacc/repos/my-app/
├── Rediaccfile              # Raíz: configuración compartida (ej., crear redes Docker)
├── docker-compose.yml       # Archivo compose raíz
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

## Paso 7: Red de Servicios (.rediacc.json)

Cada repositorio obtiene una subred /26 (64 IPs) en el rango de loopback `127.x.x.x`. Los servicios se vinculan a IPs de loopback únicas para que puedan ejecutarse en los mismos puertos sin conflictos. Por ejemplo, dos instancias de PostgreSQL pueden escuchar en el puerto 5432, cada una en una IP diferente.

### El Archivo .rediacc.json

El archivo `.rediacc.json` mapea nombres de servicios a números de **slot**. Cada slot corresponde a una dirección IP única dentro de la subred del repositorio.

```json
{
  "services": {
    "api": {"slot": 0},
    "postgres": {"slot": 1},
    "redis": {"slot": 2}
  }
}
```

Los servicios se escriben en orden alfabético.

### Generación Automática desde Docker Compose

No necesita crear `.rediacc.json` manualmente. Cuando ejecuta `rdc repo up`, Rediacc automáticamente:

1. Escanea todos los directorios que contienen un Rediaccfile en busca de archivos compose (`docker-compose.yml`, `docker-compose.yaml`, `compose.yml` o `compose.yaml`).
2. Extrae los nombres de servicio de la sección `services:` de cada archivo compose.
3. Asigna el siguiente slot disponible a cualquier servicio nuevo.
4. Guarda el resultado en `{repository}/.rediacc.json`.

### Cálculo de IP

La IP de un servicio se calcula a partir del ID de red del repositorio y el slot del servicio:

```
IP Base = 127.{networkID / 65536}.{(networkID / 256) % 256}.{networkID % 256}
IP del Servicio = 127.{(networkID + slot + 2) / 65536}.{((networkID + slot + 2) / 256) % 256}.{(networkID + slot + 2) % 256}
```

Los primeros dos desplazamientos (0 y 1) están reservados para la dirección de red y la puerta de enlace. Los slots de servicio comienzan en el desplazamiento 2.

**Ejemplo** para ID de red `2816`:

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

Las variables `${POSTGRES_IP}` y `${API_IP}` se exportan automáticamente desde `.rediacc.json` cuando se ejecuta el Rediaccfile.

## Paso 8: Iniciar Servicios

Monte el repositorio e inicie todos los servicios:

```bash
rdc repo up my-app -m server-1 --mount
```

| Opción | Requerido | Descripción |
|--------|-----------|-------------|
| `-m, --machine <name>` | Sí | Máquina destino. |
| `--mount` | No | Montar el repositorio primero si no está montado. Sin esta bandera, el repositorio ya debe estar montado. |
| `--prep-only` | No | Ejecutar solo las funciones `prep()`, omitir `up()`. Útil para pre-descargar imágenes o ejecutar migraciones. |

La secuencia de ejecución es:

1. Montar el repositorio cifrado con LUKS (si se especifica `--mount`)
2. Iniciar el daemon Docker aislado para este repositorio
3. Generar automáticamente `.rediacc.json` a partir de archivos compose
4. Ejecutar `prep()` en todos los Rediaccfiles (orden A-Z, fallo rápido)
5. Ejecutar `up()` en todos los Rediaccfiles (orden A-Z)

## Paso 9: Detener Servicios

Detenga todos los servicios en un repositorio:

```bash
rdc repo down my-app -m server-1
```

| Opción | Requerido | Descripción |
|--------|-----------|-------------|
| `-m, --machine <name>` | Sí | Máquina destino. |
| `--unmount` | No | Desmontar el repositorio cifrado después de detener los servicios. Esto también detiene el daemon Docker aislado y cierra el volumen LUKS. |

La secuencia de ejecución es:

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
rdc repo resize my-app -m server-1 --size 20G    # Establecer tamaño exacto
rdc repo expand my-app -m server-1 --size 5G      # Agregar 5G al tamaño actual
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

Esto crea una nueva copia cifrada con su propio GUID e ID de red. La bifurcación comparte la misma credencial LUKS que el repositorio padre.

### Validar un Repositorio

Verifique la integridad del sistema de archivos de un repositorio:

```bash
rdc repo validate my-app -m server-1
```

## Inicio Automático al Arranque

Por defecto, los repositorios deben montarse e iniciarse manualmente después de reiniciar el servidor. El **inicio automático** configura los repositorios para montarse automáticamente, iniciar Docker y ejecutar el `up()` del Rediaccfile cuando el servidor arranca.

### Cómo Funciona

Cuando habilita el inicio automático para un repositorio:

1. Se genera un archivo de clave LUKS aleatorio de 256 bytes y se agrega al slot 1 de LUKS del repositorio (el slot 0 permanece como la frase de contraseña del usuario).
2. El archivo de clave se almacena en `{datastore}/.credentials/keys/{guid}.key` con permisos `0600` (solo root).
3. Se instala un servicio systemd (`rediacc-autostart`) que se ejecuta al arranque para montar todos los repositorios habilitados e iniciar sus servicios.

Al apagar o reiniciar el sistema, el servicio detiene graciosamente todos los servicios (`down()` del Rediaccfile), detiene los daemons Docker y cierra los volúmenes LUKS.

> **Nota de seguridad:** Habilitar el inicio automático almacena un archivo de clave LUKS en el disco del servidor. Cualquier persona con acceso root al servidor puede montar el repositorio sin la frase de contraseña. Este es un compromiso entre conveniencia (arranque automático) y seguridad (requerir entrada manual de la frase de contraseña). Evalúe esto según su modelo de amenazas.

### Habilitar Inicio Automático

```bash
rdc repo autostart enable my-app -m server-1
```

Se le solicitará la frase de contraseña del repositorio. Esto es necesario para autorizar la adición del archivo de clave al volumen LUKS.

### Habilitar Inicio Automático para Todos los Repositorios

```bash
rdc repo autostart enable-all -m server-1
```

### Deshabilitar Inicio Automático

```bash
rdc repo autostart disable my-app -m server-1
```

Esto elimina el archivo de clave y destruye el slot 1 de LUKS. El repositorio ya no se montará automáticamente al arranque.

### Listar Estado del Inicio Automático

```bash
rdc repo autostart list -m server-1
```

Muestra qué repositorios tienen el inicio automático habilitado y si el servicio systemd está instalado.

## Ejemplo Completo: Desplegar una Aplicación Web

Este ejemplo de extremo a extremo despliega una aplicación web con PostgreSQL, Redis y un servidor API.

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

Conéctese por SSH al servidor y cree los archivos de la aplicación dentro del repositorio montado. La ruta de montaje se muestra en la salida (típicamente `/mnt/rediacc/repos/{guid}`).

### 3. Crear los Archivos de la Aplicación

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

Esto hará lo siguiente:
1. Generar automáticamente `.rediacc.json` con slots para `api`, `postgres` y `redis`
2. Ejecutar `prep()` para crear directorios y descargar imágenes
3. Ejecutar `up()` para iniciar todos los contenedores

### 5. Habilitar Inicio Automático

```bash
rdc repo autostart enable webapp -m prod-1
```

Después de reiniciar el servidor, el repositorio se montará automáticamente e iniciará todos los servicios.

## Comprender la Configuración del Contexto

Toda la configuración del contexto se almacena en `~/.rediacc/config.json`. Aquí hay un ejemplo anotado de cómo se ve este archivo después de completar los pasos anteriores:

```json
{
  "contexts": {
    "production": {
      "name": "production",
      "mode": "local",
      "apiUrl": "local://",
      "ssh": {
        "privateKeyPath": "/home/you/.ssh/id_ed25519"
      },
      "machines": {
        "prod-1": {
          "ip": "203.0.113.50",
          "user": "deploy",
          "port": 22,
          "datastore": "/mnt/rediacc",
          "knownHosts": "203.0.113.50 ssh-ed25519 AAAA..."
        }
      },
      "repositories": {
        "webapp": {
          "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
          "credential": "base64-encoded-random-passphrase",
          "networkId": 2816
        }
      }
    }
  }
}
```

**Campos clave:**

| Campo | Descripción |
|-------|-------------|
| `mode` | `"local"` para modo local, `"s3"` para contextos respaldados por S3. |
| `apiUrl` | `"local://"` indica modo local (sin API remota). |
| `ssh.privateKeyPath` | Ruta a la clave privada SSH utilizada para todas las conexiones de máquinas. |
| `machines.<name>.knownHosts` | Claves de host SSH de `ssh-keyscan`, utilizadas para verificar la identidad del servidor. |
| `repositories.<name>.repositoryGuid` | UUID que identifica la imagen de disco cifrada en el servidor. |
| `repositories.<name>.credential` | Frase de contraseña de cifrado LUKS. **No se almacena en el servidor.** |
| `repositories.<name>.networkId` | ID de red que determina la subred IP (2816 + n*64). Asignado automáticamente. |

> Este archivo contiene datos sensibles (rutas de claves SSH, credenciales LUKS). Se almacena con permisos `0600` (solo lectura/escritura para el propietario). No lo comparta ni lo incluya en control de versiones.

## Resolución de Problemas

### La Conexión SSH Falla

- Verifique que puede conectarse manualmente: `ssh -i ~/.ssh/id_ed25519 deploy@203.0.113.50`
- Ejecute `rdc context scan-keys server-1` para actualizar las claves del host
- Compruebe que el puerto SSH coincide: `--port 22`

### La Configuración de la Máquina Falla

- Asegúrese de que el usuario tenga acceso sudo sin contraseña, o configure `NOPASSWD` para los comandos requeridos
- Verifique el espacio de disco disponible en el servidor
- Ejecute con `--debug` para salida detallada: `rdc context setup-machine server-1 --debug`

### La Creación del Repositorio Falla

- Verifique que la configuración se completó: el directorio del datastore debe existir
- Compruebe el espacio de disco en el servidor
- Asegúrese de que el binario renet esté instalado (ejecute la configuración nuevamente si es necesario)

### Los Servicios No Inician

- Verifique la sintaxis del Rediaccfile: debe ser Bash válido
- Asegúrese de que los archivos de `docker compose` usen `network_mode: host`
- Verifique que las imágenes Docker sean accesibles (considere `docker compose pull` en `prep()`)
- Revise los registros de contenedores: conéctese por SSH al servidor y use `docker -H unix:///var/run/rediacc/docker-{networkId}.sock logs {container}`

### Errores de Permiso Denegado

- Las operaciones de repositorio requieren root en el servidor (renet se ejecuta mediante `sudo`)
- Verifique que su usuario esté en el grupo `sudo`
- Compruebe que el directorio del datastore tenga los permisos correctos

## Próximos Pasos

- **Referencia de la CLI** -- Consulte la página de [Aplicación CLI](/es/docs/cli-application) para la referencia completa de comandos.
- **Respaldo y Recuperación** -- Configure respaldos externos a almacenamiento compatible con S3 para recuperación ante desastres.
- **Proxy Inverso** -- Configure Traefik para HTTPS con certificados automáticos de Let's Encrypt.
- **Checkpoint/Restauración CRIU** -- Realice checkpoints de contenedores en ejecución para migración instantánea o reversión.
