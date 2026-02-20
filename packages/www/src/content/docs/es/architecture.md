---
title: Arquitectura
description: >-
  Como funciona Rediacc: arquitectura de dos herramientas, modos de operacion,
  modelo de seguridad y estructura de configuracion.
category: Guides
order: 2
language: es
sourceHash: 8f910f7827c8e958
---

# Arquitectura

Si no tienes claro que herramienta usar, consulta [rdc vs renet](/es/docs/rdc-vs-renet).

Esta pagina explica como funciona Rediacc internamente: la arquitectura de dos herramientas, los modos de operacion, el modelo de seguridad y la estructura de configuracion.

## Arquitectura de Dos Herramientas

Rediacc utiliza dos binarios que trabajan juntos a traves de SSH:

![Arquitectura de Dos Herramientas](/img/arch-two-tool.svg)

- **rdc** se ejecuta en su estacion de trabajo (macOS, Linux o Windows). Lee su configuracion local, se conecta a maquinas remotas mediante SSH e invoca comandos de renet.
- **renet** se ejecuta en el servidor remoto con privilegios de root. Gestiona imagenes de disco cifradas con LUKS, daemons Docker aislados, orquestacion de servicios y configuracion de proxy inverso.

Cada comando que escribe localmente se traduce en una llamada SSH que ejecuta renet en la maquina remota. Nunca necesitara conectarse manualmente a los servidores por SSH.

## Modos de Operacion

Rediacc soporta tres modos, cada uno determina donde se almacena el estado y como se ejecutan los comandos.

![Modos de Operacion](/img/arch-operating-modes.svg)

### Modo Local

El modo predeterminado para uso auto-hospedado. Todo el estado reside en `~/.rediacc/config.json` en su estacion de trabajo.

- Conexiones SSH directas a las maquinas
- No se requieren servicios externos
- Un solo usuario, una sola estacion de trabajo
- El contexto se crea con `rdc context create-local`

### Modo Cloud (Experimental)

Utiliza la API de Rediacc para la gestion del estado y la colaboracion en equipo.

- Estado almacenado en la API en la nube
- Equipos multiusuario con acceso basado en roles
- Consola web para gestion visual
- El contexto se crea con `rdc context create`

> **Nota:** Los comandos del modo cloud son experimentales. Habilitelos con `rdc --experimental <command>` o configurando `REDIACC_EXPERIMENTAL=1`.

### Modo S3

Almacena el estado cifrado en un bucket compatible con S3. Combina la naturaleza auto-hospedada del modo local con la portabilidad entre estaciones de trabajo.

- Estado almacenado en un bucket S3/R2 como `state.json`
- Cifrado AES-256-GCM con una contrasena maestra
- Portable: cualquier estacion de trabajo con las credenciales del bucket puede gestionar la infraestructura
- El contexto se crea con `rdc context create-s3`

Los tres modos utilizan los mismos comandos de CLI. El modo solo afecta donde se almacena el estado y como funciona la autenticacion.

## El Usuario rediacc

Cuando ejecuta `rdc context setup-machine`, renet crea un usuario del sistema llamado `rediacc` en el servidor remoto:

- **UID**: 7111
- **Shell**: `/sbin/nologin` (no puede iniciar sesion via SSH)
- **Proposito**: Es propietario de los archivos del repositorio y ejecuta las funciones del Rediaccfile

El usuario `rediacc` no puede accederse directamente via SSH. En su lugar, rdc se conecta como el usuario SSH que usted configuro (por ejemplo, `deploy`), y renet ejecuta las operaciones del repositorio mediante `sudo -u rediacc /bin/sh -c '...'`. Esto significa:

1. Su usuario SSH necesita privilegios de `sudo`
2. Todos los datos del repositorio son propiedad de `rediacc`, no de su usuario SSH
3. Las funciones del Rediaccfile (`prep()`, `up()`, `down()`) se ejecutan como `rediacc`

Esta separacion asegura que los datos del repositorio tengan una propiedad consistente independientemente de que usuario SSH los gestione.

## Aislamiento de Docker

Cada repositorio obtiene su propio daemon Docker aislado. Cuando se monta un repositorio, renet inicia un proceso `dockerd` dedicado con un socket unico:

![Aislamiento de Docker](/img/arch-docker-isolation.svg)

```
/var/run/rediacc/docker-{networkId}.sock
```

Por ejemplo, un repositorio con ID de red `2816` usa:
```
/var/run/rediacc/docker-2816.sock
```

Esto significa:
- Los contenedores de diferentes repositorios no pueden verse entre si
- Cada repositorio tiene su propia cache de imagenes, redes y volumenes
- El daemon Docker del host (si existe) esta completamente separado

Las funciones del Rediaccfile tienen automaticamente `DOCKER_HOST` configurado al socket correcto.

## Cifrado LUKS

Los repositorios son imagenes de disco cifradas con LUKS almacenadas en el datastore del servidor (por defecto: `/mnt/rediacc`). Cada repositorio:

1. Tiene una frase de contrasena de cifrado generada aleatoriamente (la "credencial")
2. Se almacena como un archivo: `{datastore}/repos/{guid}.img`
3. Se monta mediante `cryptsetup` cuando se accede

La credencial se almacena en su `config.json` local pero **nunca** en el servidor. Sin la credencial, los datos del repositorio no pueden leerse. Cuando el inicio automatico esta habilitado, se almacena un archivo de clave LUKS secundario en el servidor para permitir el montaje automatico al arrancar.

## Estructura de Configuracion

Toda la configuracion se almacena en `~/.rediacc/config.json`. Aqui hay un ejemplo anotado:

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

| Campo | Descripcion |
|-------|-------------|
| `mode` | `"local"`, `"s3"`, u omitido para modo cloud |
| `apiUrl` | `"local://"` para modo local, URL de la API para modo cloud |
| `ssh.privateKeyPath` | Clave privada SSH utilizada para todas las conexiones de maquinas |
| `machines.<name>.user` | Nombre de usuario SSH para conectarse a la maquina |
| `machines.<name>.knownHosts` | Claves de host SSH de `ssh-keyscan` |
| `repositories.<name>.repositoryGuid` | UUID que identifica la imagen de disco cifrada |
| `repositories.<name>.credential` | Frase de contrasena de cifrado LUKS (**no se almacena en el servidor**) |
| `repositories.<name>.networkId` | Determina la subred IP (2816 + n*64), asignado automaticamente |
| `nextNetworkId` | Contador global para asignar IDs de red |
| `universalUser` | Sobreescribe el usuario del sistema por defecto (`rediacc`) |

> Este archivo contiene datos sensibles (rutas de claves SSH, credenciales LUKS). Se almacena con permisos `0600` (solo lectura/escritura para el propietario). No lo comparta ni lo incluya en control de versiones.
