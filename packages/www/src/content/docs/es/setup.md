---
title: "Configuración de Máquinas"
description: "Cree una configuración, agregue máquinas, aprovisione servidores y configure la infraestructura."
category: "Guides"
tags:
  - getting-started
  - operations
subcategory: setup
order: 3
language: es
sourceHash: "a0f69282724c27ea"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
---

# Configuración de Máquinas

Cuatro pasos para que su primera máquina funcione: crear una configuración, registrar el servidor, aprovisionarlo y opcionalmente configurar la infraestructura para tráfico público.

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
rdc machine add server-1 --ip 203.0.113.50 --user deploy
```

| Opción | Requerido | Predeterminado | Descripción |
|--------|-----------|----------------|-------------|
| `--ip <address>` | Sí | - | Dirección IP o nombre de host del servidor remoto |
| `--user <username>` | Sí | - | Nombre de usuario SSH en el servidor remoto |
| `--port <port>` | No | `22` | Puerto SSH |
| `--datastore <path>` | No | `/mnt/rediacc` | Ruta en el servidor donde Rediacc almacena los repositorios cifrados |

Después de agregar la máquina, rdc ejecuta automáticamente `ssh-keyscan` para obtener las claves del host del servidor. También puede ejecutar esto manualmente:

```bash
rdc machine scan-keys server-1
```

Para ver todas las máquinas registradas:

```bash
rdc machine list
```

## Paso 3: Configurar la Máquina

Aprovisione el servidor remoto con todas las dependencias requeridas:

```bash
rdc machine setup server-1
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

## Backends de Datastore

El datastore es el pool de almacenamiento por máquina que contiene las imágenes cifradas de los repositorios. `machine setup` crea un datastore **local** por defecto: un sistema de archivos BTRFS respaldado por loop en el disco propio del servidor, dimensionado mediante `--datastore-size` (por defecto `95%` del disco disponible). Este es el backend correcto para casi cualquier despliegue de una sola máquina y no necesita nada más allá del servidor.

### Dimensionamiento del datastore

`--datastore-size` acepta un porcentaje (`95%`) o un tamaño absoluto (`50G`, `1T`). El datastore puede ampliarse en línea más tarde:

```bash
rdc datastore resize ds-server-1 --size 200G
```

Los repositorios dentro del datastore se dimensionan de forma independiente en el momento de `repo create` y pueden expandirse mientras están en ejecución, por lo que no necesitas sobredimensionar el datastore de antemano.

### Backend Ceph RBD

Para almacenamiento compartido, de escalado horizontal o de respaldo para Kubernetes, inicializa el datastore en un clúster Ceph externo en su lugar. El datastore vive entonces en una imagen RBD (BTRFS encima, sin capa LUKS por imagen), y las bifurcaciones usan clones copy-on-write de RBD en lugar de reflinks de BTRFS.

```bash
# 1. Registrar la referencia Ceph de la máquina (pool + imagen RBD, no secreta)

# 2. Inicializar el datastore en el backend Ceph
rdc datastore create ds-server-1 -m server-1 --backend ceph --pool rbd --image datastore-server1 --size 100G
```

Los keyrings de Ceph permanecen en las máquinas; el archivo de configuración solo contiene las referencias no secretas de pool e imagen. Ceph es también la capa de almacenamiento que consumen los clústeres de Kubernetes a través de ceph-csi. Consulta la guía [Kubernetes](/es/docs/kubernetes) para clústeres y volúmenes persistentes, y [Arquitectura](/es/docs/architecture) para la comparación entre ambos backends.

## Gestión de Claves del Host

Si las claves SSH de un servidor cambian (por ejemplo, después de una reinstalación), actualice las claves almacenadas:

```bash
rdc machine scan-keys server-1
```

Esto actualiza el campo `knownHosts` en su configuración para esa máquina.

## Probar Conectividad SSH

Después de agregar una máquina, verifique que sea alcanzable:

```bash
rdc term connect server-1 -c "hostname"
```

Esto abre una conexión SSH a la máquina y ejecuta el comando. Si tiene éxito, su configuración SSH es correcta.

Para diagnósticos más detallados, ejecute:

```bash
rdc doctor
```

> **Consejo**: Para verificar la conectividad SSH, ejecute `rdc term connect <machine> -c "hostname"` o use `ssh` directamente.

## Configuración de Infraestructura

Para máquinas que necesitan servir tráfico públicamente, configure los ajustes de infraestructura:

### Establecer Infraestructura

```bash
rdc machine infra set server-1 \
  --public-ipv4 203.0.113.50 \
  --base-domain example.com \
  --cert-email admin@example.com \
  --cf-dns-token your-cloudflare-api-token
```

| Opción | Alcance | Descripción |
|--------|---------|-------------|
| `--public-ipv4 <ip>` | Machine | Dirección IPv4 pública, los puntos de entrada del proxy solo se crean para familias de direcciones configuradas |
| `--public-ipv6 <ip>` | Machine | Dirección IPv6 pública, los puntos de entrada del proxy solo se crean para familias de direcciones configuradas |
| `--base-domain <domain>` | Machine | Dominio base para aplicaciones (por ejemplo, `example.com`) |
| `--cert-email <email>` | Config | Correo electrónico para certificados TLS de Let's Encrypt (compartido entre máquinas) |
| `--cf-dns-token <token>` | Config | Token de la API DNS de Cloudflare para desafíos ACME DNS-01 (compartido entre máquinas) |
| `--tcp-ports <ports>` | Machine | Puertos TCP adicionales separados por comas para redirigir (por ejemplo, `25,143,465,587,993`) |
| `--udp-ports <ports>` | Machine | Puertos UDP adicionales separados por comas para redirigir (por ejemplo, `53`) |

Las opciones de alcance Machine se almacenan por máquina. Las opciones de alcance Config (`--cert-email`, `--cf-dns-token`) son compartidas entre todas las máquinas en la configuración. Configúrelas una vez y se aplican en todas partes.

### Ver Infraestructura

```bash
rdc machine infra show server-1
```

### Enviar al Servidor

Genere y despliegue la configuración del proxy inverso Traefik en el servidor:

```bash
rdc machine infra push server-1
```

Este comando:
1. Despliega el binario renet en la máquina remota
2. Configura el proxy inverso Traefik, el enrutador y los servicios systemd
3. Crea registros DNS de Cloudflare para el subdominio de la máquina (`server-1.example.com` y `*.server-1.example.com`) si se ha establecido `--cf-dns-token`

El paso de DNS es automático e idempotente: crea registros faltantes, actualiza registros con IPs cambiadas y omite registros que ya son correctos. Si no se ha configurado un token de Cloudflare, se omite el DNS con una advertencia. Los registros DNS de comodín por repositorio (para rutas automáticas) se crean automáticamente cuando ejecuta `rdc repo up`.

## Aprovisionamiento en la Nube

En lugar de crear VMs manualmente, puede configurar un proveedor de nube y dejar que `rdc` aprovisione máquinas automáticamente usando [OpenTofu](https://opentofu.org/).

### Requisitos Previos

Instale OpenTofu: [opentofu.org/docs/intro/install](https://opentofu.org/docs/intro/install/)

Asegúrese de que su configuración SSH tenga una clave registrada con `rdc`:

```bash
# Lee el archivo de clave e inserta el contenido en /credentials/ssh.
rdc config ssh set --key ~/.ssh/id_ed25519
```

### Agregar un Proveedor de Nube

```bash
rdc machine provider add my-linode \
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
5. Configura el proxy Traefik y DNS de Cloudflare (detecta automáticamente el dominio base de máquinas hermanas, o pase `--base-domain` explícitamente)

| Opción | Descripción |
|--------|-------------|
| `--provider <name>` | Nombre del proveedor de nube (de `add-provider`) |
| `--region <region>` | Anula la región predeterminada del proveedor |
| `--type <type>` | Anula el tipo de instancia predeterminado |
| `--image <image>` | Anula la imagen de SO predeterminada |
| `--base-domain <domain>` | Dominio base para la infraestructura. Se detecta automáticamente de máquinas hermanas si no se especifica |
| `--no-infra` | Omitir completamente la configuración de infraestructura (proxy + DNS) |
| `--debug` | Muestra salida detallada del aprovisionamiento |

### Desaprovisionar una Máquina

```bash
rdc machine deprovision prod-2
```

Destruye la VM mediante OpenTofu y la elimina de su configuración. Requiere confirmación a menos que se use `--force`. Solo funciona para máquinas creadas con `machine provision`.

### Listar Proveedores

```bash
rdc machine provider list
```

## Establecer Valores Predeterminados

Configure valores predeterminados para no tener que especificarlos en cada comando:

```bash
rdc config field set --pointer /defaults/machine --new '"server-1"'   # Máquina predeterminada
rdc config set team my-team                   # Equipo predeterminado para el almacén de configuración
```

Después de establecer una máquina predeterminada, puede omitir `-m server-1` en los comandos:

```bash
rdc repo create my-app -m my-server --size 10G
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
