---
title: "Configuración de Máquinas"
description: "Cree una configuración, agregue máquinas, aprovisione servidores y configure la infraestructura."
category: "Guides"
order: 3
language: es
sourceHash: "5256e189c350ee18"
---

# Configuración de Máquinas

Esta página le guía a través de la configuración de su primera máquina: crear una configuración, registrar un servidor, aprovisionarlo y opcionalmente configurar la infraestructura para acceso público.

## Paso 1: Crear una Configuración

Una **configuración** es un archivo de configuración con nombre que almacena sus credenciales SSH, definiciones de máquinas y mapeos de repositorios. Piense en ella como un espacio de trabajo del proyecto.

```bash
rdc config init my-infra --ssh-key ~/.ssh/id_ed25519
```

| Opción | Requerido | Descripción |
|--------|-----------|-------------|
| `--ssh-key <path>` | Sí | Ruta a su clave privada SSH. La tilde (`~`) se expande automáticamente. |
| `--renet-path <path>` | No | Ruta personalizada al binario renet en las máquinas remotas. Por defecto usa la ubicación de instalación estándar. |

Esto crea una configuración llamada `my-infra` y la almacena en `~/.config/rediacc/my-infra.json`. La configuración predeterminada (cuando no se da nombre) se almacena como `~/.config/rediacc/rediacc.json`.

> Puede tener múltiples configuraciones (por ejemplo, `production`, `staging`, `dev`). Cambie entre ellas con la bandera `--config` en cualquier comando.

## Paso 2: Agregar una Máquina

Registre su servidor remoto como una máquina en la configuración:

```bash
rdc config add-machine server-1 --ip 203.0.113.50 --user deploy
```

| Opción | Requerido | Predeterminado | Descripción |
|--------|-----------|----------------|-------------|
| `--ip <address>` | Sí | - | Dirección IP o nombre de host del servidor remoto |
| `--user <username>` | Sí | - | Nombre de usuario SSH en el servidor remoto |
| `--port <port>` | No | `22` | Puerto SSH |
| `--datastore <path>` | No | `/mnt/rediacc` | Ruta en el servidor donde Rediacc almacena los repositorios cifrados |

Después de agregar la máquina, rdc ejecuta automáticamente `ssh-keyscan` para obtener las claves del host del servidor. También puede ejecutar esto manualmente:

```bash
rdc config scan-keys server-1
```

Para ver todas las máquinas registradas:

```bash
rdc config machines
```

## Paso 3: Configurar la Máquina

Aprovisione el servidor remoto con todas las dependencias requeridas:

```bash
rdc config setup-machine server-1
```

Este comando:
1. Sube el binario renet al servidor mediante SFTP
2. Instala Docker, containerd y cryptsetup (si no están presentes)
3. Crea el usuario del sistema `rediacc` (UID 7111)
4. Crea el directorio del datastore y lo prepara para repositorios cifrados

| Opción | Requerido | Predeterminado | Descripción |
|--------|-----------|----------------|-------------|
| `--datastore <path>` | No | `/mnt/rediacc` | Directorio del datastore en el servidor |
| `--datastore-size <size>` | No | `95%` | Cantidad de disco disponible a asignar para el datastore |
| `--debug` | No | `false` | Habilitar salida detallada para resolución de problemas |

> La configuración solo necesita ejecutarse una vez por máquina. Es seguro volver a ejecutarla si es necesario.

## Gestión de Claves del Host

Si las claves SSH de un servidor cambian (por ejemplo, después de una reinstalación), actualice las claves almacenadas:

```bash
rdc config scan-keys server-1
```

Esto actualiza el campo `knownHosts` en su configuración para esa máquina.

## Probar Conectividad SSH

Después de agregar una máquina, verifique que sea alcanzable:

```bash
rdc term server-1 -c "hostname"
```

Esto abre una conexión SSH a la máquina y ejecuta el comando. Si tiene éxito, su configuración SSH es correcta.

Para diagnósticos más detallados, ejecute:

```bash
rdc doctor
```

> **Solo adaptador cloud**: El comando `rdc machine test-connection` proporciona diagnósticos SSH detallados pero requiere el adaptador cloud. Para el adaptador local, use `rdc term` o `ssh` directamente.

## Configuración de Infraestructura

Para máquinas que necesitan servir tráfico públicamente, configure los ajustes de infraestructura:

### Establecer Infraestructura

```bash
rdc config set-infra server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| Opción | Alcance | Descripción |
|--------|---------|-------------|
| `--public-ipv4 <ip>` | Machine | Public IPv4 address — proxy entrypoints are only created for configured address families |
| `--public-ipv6 <ip>` | Machine | Public IPv6 address — proxy entrypoints are only created for configured address families |
| `--base-domain <domain>` | Machine | Dominio base para aplicaciones (por ejemplo, `example.com`) |
| `--cert-email <email>` | Config | Correo electrónico para certificados TLS de Let's Encrypt (compartido entre máquinas) |
| `--cf-dns-token <token>` | Config | Token de la API DNS de Cloudflare para desafíos ACME DNS-01 (compartido entre máquinas) |
| `--tcp-ports <ports>` | Machine | Puertos TCP adicionales separados por comas para redirigir (por ejemplo, `25,143,465,587,993`) |
| `--udp-ports <ports>` | Machine | Puertos UDP adicionales separados por comas para redirigir (por ejemplo, `53`) |

Las opciones de alcance Machine se almacenan por máquina. Las opciones de alcance Config (`--cert-email`, `--cf-dns-token`) son compartidas entre todas las máquinas en la configuración — configúrelas una vez y se aplican en todas partes.

### Ver Infraestructura

```bash
rdc config show-infra server-1
```

### Enviar al Servidor

Genere y despliegue la configuración del proxy inverso Traefik en el servidor:

```bash
rdc config push-infra server-1
```

Este comando:
1. Despliega el binario renet en la máquina remota
2. Configura el proxy inverso Traefik, el enrutador y los servicios systemd
3. Crea registros DNS de Cloudflare para el subdominio de la máquina (`server-1.example.com` y `*.server-1.example.com`) si se ha establecido `--cf-dns-token`

El paso de DNS es automático e idempotente: crea registros faltantes, actualiza registros con IPs cambiadas y omite registros que ya son correctos. Si no se ha configurado un token de Cloudflare, se omite el DNS con una advertencia. Per-repo wildcard DNS records (for auto-routes) are created automatically when you run `rdc repo up`.

## Aprovisionamiento en la Nube

En lugar de crear VMs manualmente, puede configurar un proveedor de nube y dejar que `rdc` aprovisione máquinas automáticamente usando [OpenTofu](https://opentofu.org/).

### Requisitos Previos

Instale OpenTofu: [opentofu.org/docs/intro/install](https://opentofu.org/docs/intro/install/)

Asegúrese de que su configuración SSH incluya una clave pública:

```bash
rdc config set-ssh --private-key ~/.ssh/id_ed25519 --public-key ~/.ssh/id_ed25519.pub
```

### Agregar un Proveedor de Nube

```bash
rdc config add-provider my-linode \
  --provider linode/linode \
  --token $LINODE_API_TOKEN \
  --region us-east \
  --type g6-standard-2
```

| Opción | Requerido | Descripción |
|--------|-----------|-------------|
| `--provider <source>` | Sí* | Fuente de proveedor conocido (por ejemplo, `linode/linode`, `hetznercloud/hcloud`) |
| `--source <source>` | Sí* | Fuente de proveedor OpenTofu personalizada (para proveedores desconocidos) |
| `--token <token>` | Sí | Token de API para el proveedor de nube |
| `--region <region>` | No | Región predeterminada para nuevas máquinas |
| `--type <type>` | No | Tipo/tamaño de instancia predeterminado |
| `--image <image>` | No | Imagen de SO predeterminada |
| `--ssh-user <user>` | No | Nombre de usuario SSH (predeterminado: `root`) |

\* Se requiere `--provider` o `--source`. Use `--provider` para proveedores conocidos (valores predeterminados integrados). Use `--source` con las banderas adicionales `--resource`, `--ipv4-output`, `--ssh-key-attr` para proveedores personalizados.

### Aprovisionar una Máquina

```bash
rdc machine provision prod-2 --provider my-linode
```

Este único comando:
1. Crea una VM en el proveedor de nube mediante OpenTofu
2. Espera la conectividad SSH
3. Registra la máquina en su configuración
4. Instala renet y todas las dependencias
5. Configures Traefik proxy and Cloudflare DNS (auto-detects base domain from sibling machines, or pass `--base-domain` explicitly)

| Opción | Descripción |
|--------|-------------|
| `--provider <name>` | Nombre del proveedor de nube (de `add-provider`) |
| `--region <region>` | Anula la región predeterminada del proveedor |
| `--type <type>` | Anula el tipo de instancia predeterminado |
| `--image <image>` | Anula la imagen de SO predeterminada |
| `--base-domain <domain>` | Base domain for infrastructure. Auto-detected from sibling machines if not specified |
| `--no-infra` | Skip infrastructure configuration (proxy + DNS) entirely |
| `--debug` | Muestra salida detallada del aprovisionamiento |

### Desaprovisionar una Máquina

```bash
rdc machine deprovision prod-2
```

Destruye la VM mediante OpenTofu y la elimina de su configuración. Requiere confirmación a menos que se use `--force`. Solo funciona para máquinas creadas con `machine provision`.

### Listar Proveedores

```bash
rdc config providers
```

## Establecer Valores Predeterminados

Configure valores predeterminados para no tener que especificarlos en cada comando:

```bash
rdc config set machine server-1    # Máquina predeterminada
rdc config set team my-team        # Equipo predeterminado (adaptador cloud, experimental)
```

Después de establecer una máquina predeterminada, puede omitir `-m server-1` en los comandos:

```bash
rdc repo create my-app --size 10G   # Usa la máquina predeterminada
```

## Múltiples Configuraciones

Gestione múltiples entornos con configuraciones con nombre:

```bash
# Crear configuraciones separadas
rdc config init production --ssh-key ~/.ssh/id_prod
rdc config init staging --ssh-key ~/.ssh/id_staging

# Usar una configuración específica
rdc repo list -m server-1 --config production
rdc repo list -m staging-1 --config staging
```

Ver todas las configuraciones:

```bash
rdc config list
```

Mostrar detalles de la configuración actual:

```bash
rdc config show
```
