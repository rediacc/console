---
title: Inicio rápido
description: Ejecute un servicio en contenedores en su servidor en minutos.
category: Guides
order: -1
language: es
sourceHash: "50b448b7b1e7b85b"
---

# Inicio rápido

Despliegue un entorno de contenedores cifrado y aislado en su propio servidor. Sin cuentas en la nube ni dependencias de SaaS. Todo se ejecuta en hardware que usted controla.

---

## Introducción

### Conceptos clave

Un repo es un único archivo cifrado en disco. Muévalo, haga una copia de seguridad, bifúrquelo. Es solo un archivo. Cuando se monta, se convierte en una carpeta con un daemon Docker dedicado y los datos de su aplicación dentro.

Piense en un repo como una unidad USB. Es algo en su mano, y cuando lo conecta se vuelve visible y accesible para el sistema. Sus aplicaciones y datos son completamente portátiles. Conecte y ejecute en cualquier máquina en cualquier proveedor de nube.

**Dos herramientas, dos roles:**

- **rdc** = CLI en su portátil (TypeScript, instalado globalmente)
- **renet** = orquestador en el servidor (binario Go, gestiona daemons/redes/aislamiento)
- RDC aprovisiona renet automáticamente durante `config machine setup`. No requiere configuración manual en el servidor.

> [Arquitectura](/en/docs/architecture) explica el modelo de seguridad. [rdc vs renet](/en/docs/rdc-vs-renet) explica qué herramienta usar en cada caso.

### 1. Instalar la CLI

```bash
curl -fsSL https://www.rediacc.com/install.sh | bash
rdc doctor     # Verificar: Node, clave SSH, renet, Docker
```

> Windows, Alpine, Arch: consulte [Instalación](/en/docs/installation). Requisitos completos del sistema: [Requisitos](/en/docs/requirements).

### 2. Configuración de clave SSH

rdc se conecta a través de SSH. El servidor debe confiar en su clave pública antes de que rdc pueda acceder a él.

```bash
# Generar una clave (omita si ya tiene una)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519

# Copiar la clave pública al servidor (pedirá contraseña)
ssh-copy-id -i ~/.ssh/id_ed25519 user@your-server-ip

# Indicar a rdc qué clave usar
rdc config ssh set --key ~/.ssh/id_ed25519
```

Ahora todos los comandos de rdc se autentican con esta clave. Sin contraseñas.

### 3. Agregar su servidor

```bash
rdc config machine add --name my-server --ip 192.168.1.100 --user muhammed
rdc config machine setup --name my-server  # Aprovisiona renet + crea almacén de datos
```

**Qué sucede:** Se escanea la clave del host SSH, se sube el binario de renet y se inicializa el almacén de datos cifrado en el servidor. Listo para repos.

> Dimensionamiento del almacén, Ceph RBD, proveedores de nube: [Configuración de máquina](/en/docs/setup). Fallos de SSH: [Solución de problemas](/en/docs/troubleshooting).

### 4. Archivo de configuración

```bash
rdc config show                            # Resumen legible
cat ~/.config/rediacc/rediacc.json         # JSON sin procesar: máquinas, repos, almacenamientos, clave SSH
```

**Un archivo = un entorno.** Cópielo a otro portátil y estará listo.

---

## Trabajar con un repo

### 1. Crear un repo

```bash
rdc repo create --name my-app -m my-server --size 2G  # Crear repo cifrado de 2 GB
```

Crea el volumen cifrado, lo monta e inicia su daemon Docker. El repo se registra en su configuración y está listo para usar.

> Redimensionar, eliminar, validación: [Repositorios](/en/docs/repositories).

### 2. Aplicar una plantilla

```bash
rdc repo template list                                        # Mostrar plantillas integradas
rdc repo template apply --name app-postgres -m my-server -r my-app  # Despliega docker-compose.yml + Rediaccfile
```

Las plantillas proporcionan un `docker-compose.yml`, `Rediaccfile` y archivos de soporte. Sin una plantilla (o su propio archivo compose), no hay nada que iniciar.

### 3. Iniciar el repo

```bash
rdc repo up --name my-app -m my-server  # Ejecutar Rediaccfile up()
rdc repo list -m my-server                           # Ver todos los repos en la máquina
rdc repo status --name my-app -m my-server  # Estado de montaje, Docker, tamaño, cifrado
```

`repo up` auto-monta si es necesario. No se requieren flags adicionales.

### 4. VS Code

```bash
rdc vscode connect -m my-server -r my-app              # Abre VS Code SSH, aterriza dentro del sandbox del repo
```

Está editando archivos *dentro* del volumen cifrado. `docker ps` solo muestra los contenedores de este repo. Guarde, compose up, itere.

### 5. `rdc repo up` vs `renet dev up`

| | `rdc repo up` | `renet dev up` |
|---|---|---|
| **Dónde se ejecuta** | Su portátil (CLI) | Dentro del sandbox de VS Code |
| **Qué hace** | SSH → auto-montaje → ejecuta Rediaccfile `up()` | Ejecuta Rediaccfile `up()` directamente |
| **Caso de uso** | CI/CD, automatización, operaciones remotas | Ciclo interno del desarrollador |
| **Aislamiento** | Orquesta desde afuera | Ya está dentro del sandbox |

**Flujo de demostración:** `rdc repo template apply` → `rdc vscode connect -m my-server -r my-app` → editar `docker-compose.yml` → `renet dev up` → ver la app ejecutándose → iterar.

> Estructura del Rediaccfile: [Servicios](/en/docs/services). Cuándo usar cada herramienta: [rdc vs renet](/en/docs/rdc-vs-renet).

### 6. Modelo de aislamiento

- **Usuario universal** (`rediacc`): Mismo UID en cada máquina. Mueva un repo a otro servidor y la propiedad de archivos simplemente funciona. Sin dolores de cabeza con `chown`.
- **Daemon Docker por repo**: Cada repo obtiene su propio daemon Docker aislado. `docker ps` solo muestra los contenedores de ESTE repo.
- **Sandbox con Landlock + OverlayFS**: La shell de VS Code tiene restricción de sistema de archivos. No puede leer otros repos. Las escrituras en `$HOME` son overlays por repo.

> Cómo funciona el aislamiento: [Arquitectura](/en/docs/architecture). Ciclo de vida del Rediaccfile: [Servicios](/en/docs/services).

### 7. Terminal, sincronización y túnel

**Terminal:**
```bash
rdc term connect -m my-server -r my-app                            # SSH al sandbox del repo
rdc term connect -m my-server -r my-app -c "curl localhost:3000"   # Ejecutar comando y salir
rdc term connect -m my-server                                   # SSH a la máquina (sin sandbox)
```

**Sincronización de archivos (rsync sobre SSH):**
```bash
rdc repo sync upload -m my-server -r my-app --local ./src       # Subir archivos locales al repo
rdc repo sync download -m my-server -r my-app --local ./backup  # Descargar archivos del repo a local
rdc repo sync download -m my-server -r my-app --local ./backup --dry-run  # Previsualizar primero
```

**Túnel (reenvío de puertos SSH al contenedor):**
```bash
rdc repo tunnel -m my-server -r my-app  # Auto-detectar contenedor y puerto
rdc repo tunnel -m my-server -r my-app --port 5432  # Túnel a Postgres
rdc repo tunnel -m my-server -r my-app --port 5432 --local 15432  # Puerto local personalizado
```

Ejecute tunnel → abra `localhost:3000` en el navegador → app en vivo desde el servidor remoto.

> Detalles de sincronización, terminal, VS Code: [Herramientas](/en/docs/tools).

---

## Fork y copia de seguridad

### 1. Grand y fork de repos

```bash
rdc repo fork --parent my-app -m my-server --tag experiment --up  # Clon CoW instantáneo + iniciar
rdc repo list -m my-server                                  # Muestra: my-app (grand) + my-app:experiment (fork)
rdc repo delete --name my-app:experiment -m my-server  # Eliminar fork, grand intacto
```

**Clon instantáneo, sin copia de datos.** CoW (copy-on-write). Microsegundos, sin datos copiados. Los bloques se comparten hasta que un lado escribe.

**Casos de uso:**
- **AI / ML:** Fork del dataset de producción, ejecutar experimento, descartar o promover
- **DevOps:** Fork → probar migración → eliminar si falla, promover si funciona
- **Copia de seguridad:** Fork = snapshot instantáneo, envíelo fuera del sitio

> Ciclo de vida del fork, forks entre máquinas: [Repositorios](/en/docs/repositories).

### 2. Push a otra máquina

```bash
# Enviar repo a otra máquina
rdc repo push --name my-app -m my-server --to backup-server

# Enviar y auto-desplegar en el destino
rdc repo push --name my-app -m my-server --to backup-server --up

# Enviar con checkpoint CRIU (migración en vivo, preserva estado de memoria)
rdc repo push --name my-app -m my-server --to new-server --checkpoint --up

# Enviar a una nueva máquina (auto-aprovisionamiento via proveedor de nube)
rdc repo push --name my-app -m my-server --to new-server --provision linode --up
```

### 3. Push a almacenamiento en la nube (OneDrive, Google Drive, S3)

```bash
# Importar su configuración de rclone como backend de almacenamiento
rdc config storage import --file ~/rclone.conf

# Listar almacenamientos disponibles
rdc storage list

# Enviar repo a almacenamiento en la nube
rdc repo push --name my-app -m my-server --to my-s3-backup

# Listar copias de seguridad en almacenamiento
rdc repo backup list --from my-s3-backup -m my-server
```

`--to` auto-detecta si el destino es una máquina o un backend de almacenamiento. Funciona con cualquier proveedor soportado por rclone: S3, R2, B2, OneDrive, Google Drive, SFTP, etc.

### 4. Pull desde remoto

```bash
# Traer repo desde una máquina en la nube a su servidor local
rdc repo pull --name my-app -m my-local-server --from cloud-server

# Traer desde almacenamiento en la nube
rdc repo pull --name my-app -m my-local-server --from my-s3-backup

# Traer e iniciar inmediatamente
rdc repo pull --name my-app -m my-local-server --from my-s3-backup --up
```

**¿Por qué pull?** Su máquina local está detrás de NAT. La nube no puede enviar hacia usted. Pero usted puede alcanzar la nube. Pull trae el repo a casa.

**Ciclo completo:** Crear en dev → push a la nube → pull en producción → `--up`. Un repo, cualquier máquina, cualquier nube.

> Programación, copias de seguridad automáticas, restauración: [Copia de seguridad y restauración](/en/docs/backup-restore).

---

## Proxy y SSL

### 1. Configuración de infraestructura

```bash
rdc config infra set -m my-server  # Configurar: dominio base, IPs públicas, rangos de puertos
rdc config infra show -m my-server  # Revisar configuración
rdc config infra push -m my-server  # Enviar configuración de proxy al remoto
```

**Cómo funciona el enrutamiento:**
- Traefik auto-descubre contenedores via las etiquetas `rediacc.service_name` y `rediacc.service_port`
- Rutas: `{service}-{networkId}.{baseDomain}` → IP del contenedor:puerto
- SSL: Let's Encrypt via desafío DNS-01 de Cloudflare (renovación automática, certificados wildcard)

### 2. Plantilla de proxy

```bash
rdc repo template apply --name proxy -m my-server -r infra  # Desplegar proxy en un repo
rdc repo up --name infra -m my-server  # Iniciar Traefik
```

Traefik ahora enruta el tráfico externo a todos los repos en esta máquina. Cada contenedor obtiene un endpoint HTTPS automáticamente.

```bash
# Navegar a https://my-app.example.com → enrutado al contenedor
# Reenvío TCP/UDP para bases de datos:
#   rediacc.tcp_ports=3306,5432 → puertos externos auto-asignados
```

> Reglas de enrutamiento, DNS, configuración TLS: [Redes](/en/docs/networking).

---

## Próximos pasos

- **[Guía de migración](/en/docs/migration)** - Incorporar proyectos existentes a repositorios Rediacc
- **[Monitoreo](/en/docs/monitoring)** - Salud de la máquina, contenedores, servicios, diagnósticos
- **[Referencia de la CLI](/en/docs/cli-application)** - Referencia completa de comandos
- **[Hoja de referencia](/en/docs/rdc-cheat-sheet)** - Búsqueda rápida de comandos
- **[Solución de problemas](/en/docs/troubleshooting)** - Soluciones para problemas comunes
- **[Reglas de Rediacc](/en/docs/rules-of-rediacc)** - Mejores prácticas del Rediaccfile y lista de verificación de despliegue
