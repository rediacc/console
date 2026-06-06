---
title: "Referencia del Servidor"
description: "Organización de directorios, comandos de renet, servicios systemd y flujos de trabajo para el servidor remoto."
category: "Concepts"
order: 3
language: es
sourceHash: "4fb53bb4cb1512f6"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Referencia del Servidor

Conecta por SSH a un servidor Rediacc y aquí está lo que necesitas: la organización de directorios, los comandos `renet`, los servicios systemd y los flujos de trabajo que necesitarás.

La mayoría de los usuarios gestionan los servidores desde su estación de trabajo mediante `rdc` y nunca necesitan esta página. Está aquí para depuración avanzada o cuando necesitas trabajar directamente en el servidor.

Para la arquitectura de alto nivel, consulta [Arquitectura](/es/docs/architecture). Para conocer la diferencia entre `rdc` y `renet`, consulta [rdc vs renet](/es/docs/rdc-vs-renet).

## Organización de directorios

```
/mnt/rediacc/                          # Main datastore
├── repositories/                      # Encrypted disk images (LUKS)
│   └── {uuid}                         # Each is a loop device image
├── mounts/                            # Mount points for decrypted repos
│   └── {uuid}/
│       ├── .rediacc.json              # Service → IP slot mapping
│       ├── .rediacc/docker/           # Docker daemon data (images, containers)
│       └── {service-name}/            # Service directory
│           ├── docker-compose.yml     # Compose definition
│           ├── Rediaccfile            # Lifecycle hooks (bash)
│           └── data/                  # Persistent data
├── immovable/                         # Read-only shared content
├── .credentials/                      # Encrypted secrets
└── .backup-*/                         # BTRFS snapshots

/opt/rediacc/proxy/                    # Traefik reverse proxy
├── docker-compose.yml
├── config.env                         # CERTBOT_EMAIL, CF_DNS_API_TOKEN
├── letsencrypt/                       # ACME certificates
└── traefik/dynamic/                   # Dynamic route files

/run/rediacc/docker-{id}.sock          # Per-network Docker sockets
/var/lib/rediacc/router/               # Router state (port allocations)
```

## Comandos renet

`renet` es el binario del lado del servidor. Todos los comandos necesitan privilegios de root (`sudo`).

### Ciclo de vida de un repositorio

```bash
# List all repositories
renet repository list

# Show repository details
renet repository status --name {uuid}

# Start a repository (mount + run Rediaccfile up)
renet repository up --name {uuid} --network-id {id} --password-stdin

# Stop a repository (run Rediaccfile down)
renet repository down --name {uuid} --network-id {id}

# Create a new repository
renet repository create --name {uuid} --network-id {id} --size 2G --encrypted

# Fork (instant copy using BTRFS reflinks)
renet repository fork --source {uuid} --target {new-uuid}

# Expand a running repository (no downtime)
renet repository expand --name {uuid} --size 4G

# Delete a repository and all its data
renet repository delete --name {uuid} --network-id {id}
```

### Docker Compose

Ejecutar comandos compose contra el daemon de Docker de un repositorio concreto:

```bash
sudo renet compose -- up -d
sudo renet compose -- down
sudo renet compose -- logs -f
sudo renet compose -- config
```

Ejecutar comandos Docker directamente:

```bash
sudo renet docker --network-id {id} -- ps
sudo renet docker --network-id {id} -- logs -f {container}
sudo renet docker --network-id {id} -- exec -it {container} bash
```

También puedes usar el socket de Docker directamente:

```bash
DOCKER_HOST=unix:///run/rediacc/docker-{id}.sock docker ps
```

> Ejecuta siempre compose desde el directorio que contiene `docker-compose.yml`, o Docker no encontrará el archivo.

### Sandbox del sistema de archivos

```bash
# Comprobar compatibilidad con Landlock
renet sandbox-exec --detect

# Ejecutar un comando dentro de un sandbox Landlock (usado internamente)
renet sandbox-exec --allow-rw /path --allow-ro /usr --allow-exec /bin -- command
```

`sandbox-exec` aplica restricciones de sistema de archivos de Landlock LSM y luego ejecuta el comando indicado. Es invocado automáticamente por `sandbox-gateway` (el manejador SSH ForceCommand) para todas las conexiones a nivel de repositorio.

### Hub por usuario (entornos de desarrollo)

El Hub proporciona a cada usuario su propio daemon Docker para entornos de desarrollo, independiente de los daemons `FlavorRediacc` por repositorio.

```bash
# Instalar / eliminar las unidades systemd del Hub por usuario
sudo renet hub install
sudo renet hub uninstall

# Recolectar daemons Hub por usuario inactivos
sudo renet hub gc
```

Los daemons se ejecutan bajo uno de dos flavors, seleccionado con `--flavor`:

```bash
# Daemon aislado por repositorio (bridge=none, iptables=false) — el predeterminado
sudo renet daemon start-foreground --flavor=rediacc ...

# Daemon Hub por usuario (bridge=docker0, iptables=true, live-restore=true)
sudo renet daemon start-foreground --flavor=hub ...
```

El flavor `hub` habilita la red bridge normal para que los contenedores del usuario tengan conectividad de salida; el flavor `rediacc` fuerza el aislamiento de loopback entre repositorios. Los registros de auditoría del Hub se escriben en `/var/log/rediacc/hub/<user>.log`.

**Flags:**
- `--allow-rw`, `--allow-ro`, `--allow-exec`: reglas de ruta de Landlock
- `--home-overlay`: monta OverlayFS sobre el directorio home para aislar la escritura por repositorio
- `--sandbox-dir`: espacio de trabajo por repositorio (`<datastore>/.interim/sandbox/<name>/`)
- `--work-dir`: establece el directorio de trabajo y carga `.envrc` para el entorno del repositorio
- `--run-as`: elimina privilegios al usuario objetivo tras la configuración
- `--reset-home`: borra el overlay home por repositorio para empezar desde cero

**`sandbox-gateway`** es el manejador SSH ForceCommand configurado mediante `command=` en `authorized_keys`. La clave SSH de cada repositorio activa el gateway con el nombre del repositorio incorporado, que el cliente no puede falsificar. El gateway construye los argumentos de sandbox-exec y los ejecuta mediante sudo.

### Proxy y enrutamiento

```bash
renet proxy status          # Check Traefik + router health
renet proxy routes          # Show all configured routes
renet proxy refresh         # Refresh routes from running containers
renet proxy up / down       # Start/stop Traefik
renet proxy logs            # View proxy logs
```

Las rutas se descubren automáticamente a partir de las etiquetas de los contenedores. Consulta [Redes](/es/docs/networking) para saber cómo configurar las etiquetas de Traefik.

### Estado del sistema

```bash
renet ps                    # Overall system status
renet list all              # Everything: system, containers, repositories
renet list containers       # All containers across all Docker daemons
renet list repositories     # Repository status and disk usage
renet list system           # CPU, memory, disk, network
renet ips --network-id {id} # IP allocations for a network
```

### Gestión de daemons

Cada repositorio ejecuta su propio daemon de Docker. Puedes gestionarlos individualmente:

```bash
renet daemon status --network-id {id}    # Docker daemon health
renet daemon start  --network-id {id}    # Start daemon
renet daemon stop   --network-id {id}    # Stop daemon
renet daemon logs   --network-id {id}    # Daemon logs
```

### Copia de seguridad y restauración

Enviar copias de seguridad a otra máquina o al almacenamiento en la nube:

```bash
# Push to remote machine (SSH + rsync)
renet backup push --name {uuid} --network-id {id} --target machine \
  --dest-host {host} --dest-user {user} --dest-path /mnt/rediacc --dest {uuid}.backup

# Push to cloud storage (rclone)
renet backup push --name {uuid} --network-id {id} --target storage \
  --dest {uuid}.backup --rclone-backend {backend} --rclone-bucket {bucket}

# Pull from remote
renet backup pull --name {uuid} --network-id {id} --source machine \
  --src-host {host} --src-user {user} --src-path /mnt/rediacc --src {uuid}.backup

# List remote backups
renet backup list --source machine --src-host {host} --src-user {user} --src-path /mnt/rediacc
```

> La mayoría de los usuarios debería usar `rdc repo push/pull` en su lugar. Los comandos `rdc` gestionan automáticamente las credenciales y la resolución de máquinas.

### Puntos de control (CRIU)

Los puntos de control guardan el estado de los contenedores en ejecución para poder restaurarlos después:

```bash
renet checkpoint create    --network-id {id}   # Save running container state
renet checkpoint restore   --network-id {id}   # Restore from checkpoint
renet checkpoint validate  --network-id {id}   # Check checkpoint integrity
```

### Mantenimiento

```bash
renet prune --dry-run       # Preview orphaned networks and IPs
renet prune                 # Clean up orphaned resources
renet datastore status      # BTRFS datastore health
renet datastore validate    # Filesystem integrity check
renet datastore expand      # Expand the datastore online
```

## Servicios systemd

Cada repositorio crea estas unidades systemd:

| Unidad | Propósito |
|--------|-----------|
| `rediacc-docker-{id}.service` | Daemon de Docker aislado |
| `rediacc-docker-{id}.socket` | Activación del socket de la API de Docker |
| `rediacc-loopback-{id}.service` | Configuración del alias de IP de loopback |

Servicios globales compartidos por todos los repositorios:

| Unidad | Propósito |
|--------|-----------|
| `rediacc-router.service` | Descubrimiento de rutas (puerto 7111) |
| `rediacc-autostart.service` | Montaje de repositorios en el arranque |
| `rediacc-autostart-reconcile.service` | Reconciliador de inicio automático periódico (ejecutado por el timer siguiente) |
| `rediacc-autostart-reconcile.timer` | Activa `renet repository reconcile` aproximadamente cada 3 minutos para recuperar repositorios de inicio automático que se cayeron después del arranque |

## Flujos de trabajo habituales

### Desplegar un nuevo servicio

1. Crear un repositorio cifrado:
   ```bash
   renet repository create --name {uuid} --network-id {id} --size 2G --encrypted
   ```
2. Montarlo y añadir los archivos `docker-compose.yml`, `Rediaccfile` y `.rediacc.json`.
3. Iniciarlo:
   ```bash
   renet repository up --name {uuid} --network-id {id} --password-stdin
   ```

### Acceder a un contenedor en ejecución

```bash
sudo renet docker --network-id {id} -- exec -it {container} bash
```

### Encontrar qué socket de Docker ejecuta un contenedor

```bash
for sock in /run/rediacc/docker-*.sock; do
  result=$(DOCKER_HOST=unix://$sock docker ps --format '{{.Names}}' 2>/dev/null | grep {name})
  [ -n "$result" ] && echo "Found on: $sock"
done
```

### Recrear un servicio tras cambios de configuración

```bash
sudo renet compose -- up -d
```

Ejecuta esto desde el directorio con `docker-compose.yml`. Los contenedores modificados se recrean automáticamente.

### Comprobar todos los contenedores en todos los daemons

```bash
renet list containers
```

## Consejos

- Usa siempre `sudo` para los comandos `renet compose`, `renet repository` y `renet docker`, necesitan root para las operaciones de LUKS y Docker
- El separador `--` es obligatorio antes de pasar argumentos a `renet compose` y `renet docker`
- Ejecuta compose desde el directorio que contiene `docker-compose.yml`
- Las asignaciones de slots en `.rediacc.json` son estables, no las cambies tras el despliegue
- Usa las rutas `/run/rediacc/docker-{id}.sock` (systemd puede cambiar las rutas antiguas de `/var/run/`)
- Ejecuta `renet prune --dry-run` de vez en cuando para encontrar recursos huerfanos
- Las instantáneas BTRFS (`renet backup`) son rápidas y baratas, úsalas antes de hacer cambios arriesgados
- Los repositorios están cifrados con LUKS, perder la contraseña significa perder los datos
