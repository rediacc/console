---
title: Arquitectura
description: >-
  Cómo funciona Rediacc: arquitectura de dos herramientas, detección de adaptadores,
  modelo de seguridad y estructura de configuración.
category: Concepts
order: 0
language: es
sourceHash: 5a717ddac450cb81
---

# Arquitectura

Esta página explica cómo funciona Rediacc internamente: la arquitectura de dos herramientas, la detección de adaptadores, el modelo de seguridad y la estructura de configuración.

## Visión General del Stack Completo

El tráfico fluye desde internet a través de un proxy inverso, hacia daemons Docker aislados, cada uno respaldado por almacenamiento cifrado:

![Arquitectura del Stack Completo](/img/arch-full-stack.svg)

Cada repositorio obtiene su propio daemon Docker, subred IP de loopback (/26 = 64 IPs) y volumen BTRFS cifrado con LUKS. El servidor de rutas descubre contenedores en ejecución en todos los daemons y alimenta la configuración de enrutamiento a Traefik.

## Arquitectura de Dos Herramientas

Rediacc utiliza dos binarios que trabajan juntos a través de SSH:

![Arquitectura de Dos Herramientas](/img/arch-two-tool.svg)

- **rdc** se ejecuta en su estación de trabajo (macOS, Linux o Windows). Lee su configuración local, se conecta a máquinas remotas mediante SSH e invoca comandos de renet.
- **renet** se ejecuta en el servidor remoto con privilegios de root. Gestiona imágenes de disco cifradas con LUKS, daemons Docker aislados, orquestación de servicios y configuración de proxy inverso.

Cada comando que escribe localmente se traduce en una llamada SSH que ejecuta renet en la máquina remota. Nunca necesitará conectarse manualmente a los servidores por SSH.

Para una regla práctica orientada al operador, consulte [rdc vs renet](/es/docs/rdc-vs-renet). También puede usar `rdc ops` para ejecutar un clúster de VMs local para pruebas — consulte [VMs Experimentales](/es/docs/experimental-vms).

## Config & Stores

Todo el estado de la CLI se almacena en archivos de configuración JSON planos en `~/.config/rediacc/`. Los stores le permiten sincronizar estas configuraciones con backends externos para respaldo, uso compartido o acceso desde múltiples dispositivos. Las credenciales del store se guardan por separado en `~/.config/rediacc/.credentials.json`.

![Config & Stores](/img/arch-operating-modes.svg)

### Adaptador Local (Predeterminado)

El predeterminado para uso auto-hospedado. Todo el estado reside en un archivo de configuración en su estación de trabajo (por ejemplo, `~/.config/rediacc/rediacc.json`).

- Conexiones SSH directas a las máquinas
- No se requieren servicios externos
- Un solo usuario, una sola estación de trabajo
- La configuración predeterminada se crea automáticamente en el primer uso de la CLI. Las configuraciones con nombre se crean con `rdc config init <name>`

### Adaptador Cloud (Experimental)

Se activa automáticamente cuando una configuración contiene los campos `apiUrl` y `token`. Utiliza la API de Rediacc para la gestión del estado y la colaboración en equipo.

- Estado almacenado en la API en la nube
- Equipos multiusuario con acceso basado en roles
- Consola web para gestión visual
- Se configura con `rdc auth login`

> **Nota:** Los comandos del adaptador cloud son experimentales. Habilítelos con `rdc --experimental <command>` o configurando `REDIACC_EXPERIMENTAL=1`.

### Estado de Recursos S3 (Opcional)

Cuando una configuración incluye ajustes de S3 (endpoint, bucket, clave de acceso), el estado de los recursos se almacena en un bucket compatible con S3. Esto funciona junto con el adaptador local, combinando la operación auto-hospedada con portabilidad entre estaciones de trabajo.

- Estado de recursos almacenado en un bucket S3/R2 como `state.json`
- Cifrado AES-256-GCM con una contraseña maestra
- Portable: cualquier estación de trabajo con las credenciales del bucket puede gestionar la infraestructura
- Se configura mediante `rdc config init <name> --s3-endpoint <url> --s3-bucket <bucket> --s3-access-key-id <key>`

Todos los adaptadores usan los mismos comandos de CLI. El adaptador solo afecta dónde se almacena el estado y cómo funciona la autenticación.

## El Usuario rediacc

Cuando ejecuta `rdc config setup-machine`, renet crea un usuario del sistema llamado `rediacc` en el servidor remoto:

- **UID**: 7111
- **Shell**: `/sbin/nologin` (no puede iniciar sesión vía SSH)
- **Propósito**: Es propietario de los archivos del repositorio y ejecuta las funciones del Rediaccfile

El usuario `rediacc` no puede accederse directamente vía SSH. En su lugar, rdc se conecta como el usuario SSH que usted configuró (por ejemplo, `deploy`), y renet ejecuta las operaciones del repositorio mediante `sudo -u rediacc /bin/sh -c '...'`. Esto significa:

1. Su usuario SSH necesita privilegios de `sudo`
2. Todos los datos del repositorio son propiedad de `rediacc`, no de su usuario SSH
3. Las funciones del Rediaccfile (`prep()`, `up()`, `down()`) se ejecutan como `rediacc`

Esta separación asegura que los datos del repositorio tengan una propiedad consistente independientemente de qué usuario SSH los gestione.

## Aislamiento de Docker

Cada repositorio obtiene su propio daemon Docker aislado. Cuando se monta un repositorio, renet inicia un proceso `dockerd` dedicado con un socket único:

![Aislamiento de Docker](/img/arch-docker-isolation.svg)

```
/var/run/rediacc/docker-{networkId}.sock
```

Por ejemplo, un repositorio con ID de red `2816` usa:
```
/var/run/rediacc/docker-2816.sock
```

Esto significa:
- Los contenedores de diferentes repositorios no pueden verse entre sí
- Cada repositorio tiene su propia caché de imágenes, redes y volúmenes
- El daemon Docker del host (si existe) está completamente separado

Las funciones del Rediaccfile tienen automáticamente `DOCKER_HOST` configurado al socket correcto.

## Cifrado LUKS

Los repositorios son imágenes de disco cifradas con LUKS almacenadas en el datastore del servidor (por defecto: `/mnt/rediacc`). Cada repositorio:

1. Tiene una frase de contraseña de cifrado generada aleatoriamente (la "credencial")
2. Se almacena como un archivo: `{datastore}/repos/{guid}.img`
3. Se monta mediante `cryptsetup` cuando se accede

La credencial se almacena en su archivo de configuración pero **nunca** en el servidor. Sin la credencial, los datos del repositorio no pueden leerse. Cuando el inicio automático está habilitado, se almacena un archivo de clave LUKS secundario en el servidor para permitir el montaje automático al arrancar.

## Estructura de Configuración

Cada configuración es un archivo JSON plano almacenado en `~/.config/rediacc/`. La configuración predeterminada es `rediacc.json`; las configuraciones con nombre usan el nombre como nombre de archivo (por ejemplo, `production.json`). Aquí hay un ejemplo anotado:

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "version": 1,
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
  "storages": {
    "backblaze": {
      "provider": "b2",
      "vaultContent": { "...": "..." }
    }
  },
  "repositories": {
    "webapp": {
      "repositoryGuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "credential": "base64-encoded-random-passphrase",
      "networkId": 2816
    }
  },
  "nextNetworkId": 2880,
  "universalUser": "rediacc"
}
```

**Campos clave:**

| Campo | Descripción |
|-------|-------------|
| `id` | Identificador único para este archivo de configuración |
| `version` | Versión del esquema del archivo de configuración |
| `ssh.privateKeyPath` | Clave privada SSH utilizada para todas las conexiones de máquinas |
| `machines.<name>.user` | Nombre de usuario SSH para conectarse a la máquina |
| `machines.<name>.knownHosts` | Claves de host SSH de `ssh-keyscan` |
| `repositories.<name>.repositoryGuid` | UUID que identifica la imagen de disco cifrada |
| `repositories.<name>.credential` | Frase de contraseña de cifrado LUKS (**no se almacena en el servidor**) |
| `repositories.<name>.networkId` | Determina la subred IP (2816 + n*64), asignado automáticamente |
| `nextNetworkId` | Contador global para asignar IDs de red |
| `universalUser` | Sobreescribe el usuario del sistema por defecto (`rediacc`) |

> Este archivo contiene datos sensibles (rutas de claves SSH, credenciales LUKS). Se almacena con permisos `0600` (solo lectura/escritura para el propietario). No lo comparta ni lo incluya en control de versiones.
