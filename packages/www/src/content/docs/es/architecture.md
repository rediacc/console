---
title: Arquitectura
description: >-
  Cómo funciona Rediacc: arquitectura de dos herramientas, modos de operación,
  modelo de seguridad y estructura de configuración.
category: Concepts
order: 0
language: es
sourceHash: 58ba0da9645bb9dd
---

# Arquitectura

Si no tienes claro qué herramienta usar, consulta [rdc vs renet](/es/docs/rdc-vs-renet).

Esta página explica cómo funciona Rediacc internamente: la arquitectura de dos herramientas, los modos de operación, el modelo de seguridad y la estructura de configuración.

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

## Modos de Operación

Rediacc soporta tres modos, cada uno determina dónde se almacena el estado y cómo se ejecutan los comandos.

![Modos de Operación](/img/arch-operating-modes.svg)

### Modo Local

El modo predeterminado para uso auto-hospedado. Todo el estado reside en `~/.rediacc/config.json` en su estación de trabajo.

- Conexiones SSH directas a las máquinas
- No se requieren servicios externos
- Un solo usuario, una sola estación de trabajo
- El contexto se crea con `rdc context create-local`

### Modo Cloud (Experimental)

Utiliza la API de Rediacc para la gestión del estado y la colaboración en equipo.

- Estado almacenado en la API en la nube
- Equipos multiusuario con acceso basado en roles
- Consola web para gestión visual
- El contexto se crea con `rdc context create`

> **Nota:** Los comandos del modo cloud son experimentales. Habilítelos con `rdc --experimental <command>` o configurando `REDIACC_EXPERIMENTAL=1`.

### Modo S3

Almacena el estado cifrado en un bucket compatible con S3. Combina la naturaleza auto-hospedada del modo local con la portabilidad entre estaciones de trabajo.

- Estado almacenado en un bucket S3/R2 como `state.json`
- Cifrado AES-256-GCM con una contraseña maestra
- Portable: cualquier estación de trabajo con las credenciales del bucket puede gestionar la infraestructura
- El contexto se crea con `rdc context create-s3`

Los tres modos utilizan los mismos comandos de CLI. El modo solo afecta dónde se almacena el estado y cómo funciona la autenticación.

## El Usuario rediacc

Cuando ejecuta `rdc context setup-machine`, renet crea un usuario del sistema llamado `rediacc` en el servidor remoto:

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

La credencial se almacena en su `config.json` local pero **nunca** en el servidor. Sin la credencial, los datos del repositorio no pueden leerse. Cuando el inicio automático está habilitado, se almacena un archivo de clave LUKS secundario en el servidor para permitir el montaje automático al arrancar.

## Estructura de Configuración

Toda la configuración se almacena en `~/.rediacc/config.json`. Aquí hay un ejemplo anotado:

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
      }
    }
  },
  "nextNetworkId": 2880,
  "universalUser": "rediacc"
}
```

**Campos clave:**

| Campo | Descripción |
|-------|-------------|
| `mode` | `"local"`, `"s3"`, u omitido para modo cloud |
| `apiUrl` | `"local://"` para modo local, URL de la API para modo cloud |
| `ssh.privateKeyPath` | Clave privada SSH utilizada para todas las conexiones de máquinas |
| `machines.<name>.user` | Nombre de usuario SSH para conectarse a la máquina |
| `machines.<name>.knownHosts` | Claves de host SSH de `ssh-keyscan` |
| `repositories.<name>.repositoryGuid` | UUID que identifica la imagen de disco cifrada |
| `repositories.<name>.credential` | Frase de contraseña de cifrado LUKS (**no se almacena en el servidor**) |
| `repositories.<name>.networkId` | Determina la subred IP (2816 + n*64), asignado automáticamente |
| `nextNetworkId` | Contador global para asignar IDs de red |
| `universalUser` | Sobreescribe el usuario del sistema por defecto (`rediacc`) |

> Este archivo contiene datos sensibles (rutas de claves SSH, credenciales LUKS). Se almacena con permisos `0600` (solo lectura/escritura para el propietario). No lo comparta ni lo incluya en control de versiones.
