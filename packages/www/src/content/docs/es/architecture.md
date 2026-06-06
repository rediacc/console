---
title: Arquitectura
description: >-
  Cómo funciona Rediacc: arquitectura de dos herramientas, detección de
  adaptadores, modelo de seguridad y estructura de configuración.
category: Concepts
order: 0
language: es
sourceHash: "6763cd925791d474"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Arquitectura

En pocas palabras: rdc en tu estación de trabajo, renet en tus servidores, comunicándose a través de SSH. Toda la arquitectura de Rediacc descansa sobre esa división. Esta página explica cómo las dos herramientas dividen responsabilidades, cómo la detección de adaptadores enruta el estado, cuál es el modelo de seguridad y cómo se estructura la configuración.

## Visión General del Stack Completo

El tráfico fluye desde internet a través de un proxy inverso hacia daemons Docker aislados, cada uno respaldado por almacenamiento cifrado:

![Arquitectura del Stack Completo](/img/arch-full-stack.svg)

Cada repositorio obtiene su propio daemon Docker, subred IP de loopback (/26 = 64 IPs) y volumen BTRFS cifrado con LUKS. El servidor de rutas descubre contenedores en ejecución en todos los daemons y alimenta la configuración de enrutamiento a Traefik.

## Arquitectura de Dos Herramientas

Rediacc utiliza dos binarios que trabajan juntos a través de SSH:

![Arquitectura de Dos Herramientas](/img/arch-two-tool.svg)

- **rdc** se ejecuta en tu estación de trabajo (macOS, Linux o Windows). Lee tu configuración local, se conecta a máquinas remotas mediante SSH e invoca comandos de renet.
- **renet** se ejecuta en el servidor remoto con privilegios de root. Gestiona imágenes de disco cifradas con LUKS, daemons Docker aislados, orquestación de servicios y configuración de proxy inverso.

Cada comando que ejecutas localmente se traduce en una llamada SSH que ejecuta renet en la máquina remota. Nunca necesitarás conectarte manualmente a los servidores por SSH.

Para una regla práctica orientada al operador, consulta [rdc vs renet](/en/docs/rdc-vs-renet). También puedes usar `rdc ops` para ejecutar un clúster de VMs local para pruebas, consulta [VMs Experimentales](/en/docs/experimental-vms).

## Config

Todo el estado de la CLI se almacena en archivos de configuración JSON planos bajo `~/.config/rediacc/`.

### Adaptador Local (Predeterminado)

El predeterminado para uso auto-hospedado. Todo el estado reside en un archivo de configuración en tu estación de trabajo (por ejemplo, `~/.config/rediacc/rediacc.json`).

- Conexiones SSH directas a las máquinas
- No se requieren servicios externos
- Un solo usuario, una sola estación de trabajo
- La configuración predeterminada se crea automáticamente en el primer uso de la CLI. Las configuraciones con nombre se crean con `rdc config init --name <name>`

### Adaptador Cloud (Experimental)

Se activa automáticamente cuando una configuración contiene los campos `apiUrl` y `token`. Utiliza la API de Rediacc para la gestión del estado y la colaboración en equipo.

- Estado almacenado en la API en la nube
- Equipos multiusuario con acceso basado en roles
- Consola web para gestión visual
- Se configura con `rdc auth login`

> **Nota:** Los comandos del adaptador cloud son experimentales. Habilítelos configurando `REDIACC_EXPERIMENTAL=1`.

Ambos adaptadores usan los mismos comandos de CLI. El adaptador solo afecta dónde se almacena el estado y cómo funciona la autenticación.

## El Usuario rediacc

Cuando ejecutas `rdc config machine setup`, renet crea un usuario del sistema llamado `rediacc` en el servidor remoto:

- **UID**: 7111
- **Shell**: `/sbin/nologin` (no puede iniciar sesión vía SSH)
- **Propósito**: Es propietario de los archivos del repositorio y ejecuta las funciones del Rediaccfile

El usuario `rediacc` no puede accederse directamente vía SSH. En su lugar, rdc se conecta como el usuario SSH que configuraste (por ejemplo, `deploy`), y renet ejecuta las operaciones del repositorio mediante `sudo -u rediacc /bin/sh -c '...'`. Esto significa:

1. Tu usuario SSH necesita privilegios de `sudo`
2. Todos los datos del repositorio son propiedad de `rediacc`, no de tu usuario SSH
3. Las funciones del Rediaccfile (`up()`, `down()`) se ejecutan como `rediacc`

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

Cuando un agente de IA entra en un repositorio mediante `rdc term connect -r <repo>`, se aplica el mismo aislamiento: la sesión se ejecuta como el usuario sin privilegios `rediacc` (UID 7111), en un espacio de nombres de montaje distinto, con `DOCKER_HOST` limitado al socket del daemon de ese único repositorio. El flujo de trabajo basado en bifurcación combina este aislamiento en tiempo de ejecución con una primitiva de clonación CoW: el agente opera sobre una bifurcación por tarea, nunca sobre repositorios grand (de producción). Consulta [Seguridad y salvaguardas para agentes de IA](/en/docs/ai-agents-safety) para conocer el modelo completo de sandbox, la semántica de las anulaciones y el límite de responsabilidad del desarrollador respecto a las credenciales de servicios externos.

### Estructura de Rutas del Daemon

Los datos y la configuración de Docker se almacenan dentro del punto de montaje del repositorio, manteniendo cada daemon completamente aislado del host y de otros repositorios.

**Estructura por repositorio:**
```
{datastore}/mounts/{guid}/.rediacc/docker/data/    # Raíz de datos de Docker
{datastore}/mounts/{guid}/.rediacc/docker/config/  # Configuración de Docker
```

**Estructura independiente** (daemons no vinculados a un punto de montaje de repositorio):
```
{datastore}/standalone/{N}/.rediacc/docker/data/
{datastore}/standalone/{N}/.rediacc/docker/config/
```

**Ruta de tiempo de ejecución compartida** (sin cambios):
```
/run/rediacc/docker-{N}.sock
```

Esta estructura unificada elimina las colisiones de montaje de solo lectura y lectura-escritura que ocurrían cuando las rutas del daemon estaban divididas entre el sistema de archivos del host y el volumen cifrado. Hemos tenido que resolver esa división más de una vez antes de establecernos en esto. Tanto los daemons por repositorio como los independientes siguen la misma estructura de directorios, por lo que las herramientas y los diagnósticos funcionan de forma idéntica en ambos casos.

## Cifrado LUKS

Los repositorios son imágenes de disco cifradas con LUKS almacenadas en el datastore del servidor (por defecto: `/mnt/rediacc`). Cada repositorio:

1. Tiene una frase de contraseña de cifrado generada aleatoriamente (la "credencial")
2. Se almacena como un archivo: `{datastore}/repos/{guid}.img`
3. Se monta mediante `cryptsetup` cuando se accede

La credencial se almacena en tu archivo de configuración pero **nunca** en el servidor. Sin la credencial, los datos del repositorio no pueden leerse. Cuando el inicio automático está habilitado, se almacena un archivo de clave LUKS secundario en el servidor para permitir el montaje automático al arrancar.

## Estructura de Configuración

Cada configuración es un archivo JSON almacenado en `~/.config/rediacc/`. La configuración predeterminada es `rediacc.json`; las configuraciones con nombre usan el nombre como nombre de archivo (por ejemplo, `production.json`). Los campos se organizan por propósito: `resources` contiene las implementaciones, `credentials` contiene los secretos, `account` contiene los valores predeterminados en la nube, `infra` contiene TLS/DNS, y `encryption` contiene el estado de cifrado en reposo por campo. El discriminador de nivel superior `schemaVersion: 2` ancla la compatibilidad futura.

```json
{
  "schemaVersion": 2,
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "version": 47,
  "defaults": {
    "language": "en",
    "machine": "prod-1",
    "nextNetworkId": 2880,
    "universalUser": "rediacc"
  },
  "credentials": {
    "ssh": {
      "privateKey": "-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END OPENSSH PRIVATE KEY-----",
      "publicKey": "ssh-ed25519 AAAA...",
      "knownHosts": "..."
    },
    "cfDnsApiToken": "cf-token-xxxxxxxxxxxx"
  },
  "resources": {
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
  },
  "infra": {
    "certEmail": "admin@example.com",
    "cfDnsZoneId": "..."
  },
  "encryption": {
    "mode": "plaintext"
  }
}
```

**Buckets clave:**

| Bucket | Contenido |
|---|---|
| `schemaVersion` | Discriminador (actualmente `2`). Los cargadores rechazan versiones desconocidas. |
| `id` / `version` | UUID inmutable + contador monotónico; se utiliza para bloqueos optimistas en el almacén de configuración remota. |
| `defaults.*` | Valores predeterminados de tiempo de ejecución no sensibles (`machine`, `language`, `pruneGraceDays`, `universalUser`, `nextNetworkId`). |
| `credentials.ssh` | Pareja de claves SSH en línea + `knownHosts`. Reemplaza el antiguo `ssh.privateKeyPath` (sin más indirección de ruta de archivo; el contenido se resuelve en el momento de la carga y se almacena en línea). |
| `credentials.cfDnsApiToken` | Token ACME de DNS-01 de Cloudflare. |
| `credentials.masterPasswordVerifier` | Presente solo cuando `encryption.mode === "master-password"`. |
| `resources.machines.*` | Detalles de conexión SSH por máquina. |
| `resources.storages.*` | Credenciales de copia de seguridad fuera del sitio compatibles con rclone. |
| `resources.repositories.*` | GUID por repositorio + credencial LUKS + clave SSH para acceso de agente aislado de sandbox. |
| `infra.acmeCertCache.*` | Traefik acme.json en caché, gzip+base64, indexado por dominio. |
| `encryption.mode` | `"plaintext"` (predeterminado) o `"master-password"`. |
| `encryption.encryptedFields` | Cuando se cifra, un mapa de blob AES-GCM por puntero (`/resources/repositories/webapp/credential` → `{ciphertext, nonce, tag}`). Una solicitud de desbloqueo por sesión descifra a medida que se leen los campos. |
| `remote` | Presente solo cuando la configuración se sincroniza con el almacén de configuración cifrada; consulta [Almacén de configuración cifrada](/en/docs/config-storage). |

**Edita de forma segura con la CLI, no con `vim`:**

```bash
# Ediciones de campo único direccionadas por puntero (con compuerta de conocimiento para rutas sensibles)
rdc config field set --pointer /resources/machines/prod-1/port --new 2222
rdc config field set --pointer /credentials/cfDnsApiToken --current "$OLD" --new "$NEW"

# Editor completo con proyección JSONC redactada (solo para humanos)
rdc config edit

# Volcado JSONC de solo lectura, seguro para scripts y agentes
rdc config edit --dump

# Inspecciona cada mutación + rechazo + revelación en el registro de auditoría
rdc config audit log --since 24h
rdc config audit verify
```

> Este archivo contiene datos sensibles (claves privadas SSH, credenciales LUKS, tokens de Cloudflare). Se almacena con permisos `0600` (solo lectura/escritura para el propietario). No lo compartas ni lo incluyas en control de versiones. Cuando cualquier comando `rdc` lo lee, los campos sensibles se [redactan por defecto](/en/docs/ai-agents-safety): el texto plano solo aparece con `--reveal` en un TTY interactivo humano.

### Envelope v2 y aplicación en el lado del servidor

Cuando la configuración se sincroniza con el [almacén de configuración cifrada](/en/docs/config-storage), la CLI envuelve cada campo sensible en un compromiso HMAC por campo y lleva esos compromisos en el envase de texto plano. El servidor solo ve diagramas hexadecimales: nunca los valores: pero puede aplicar compuertas de conocimiento en cada escritura:

- **Verificación de precondición**: en `PUT /configs/<id>`, el cliente envía los diagramas que afirma conocer para las rutas que desea mutar. El servidor compara con los compromisos del envase almacenado. Discrepancia → `409 precondition_failed` con `mismatchedPaths`. Conocimiento cero: el servidor nunca ve texto plano.
- **Anti-degradación**: el nuevo envase debe comprometerse con cada ruta sensible con la que se comprometió el envase anterior. Un agente no puede eliminar una ruta de los compromisos para eludir una precondición futura.
- **Fijación de versión de envase**: el servidor rechaza envases que faltan `envelopeVersion: 2` con `400 unsupported_envelope_version`. Sin ventana de aceptación dual.
- **Cifrado por campo en reposo** (lado del cliente): cuando `encryption.mode === "master-password"`, cada secreto se convierte en un blob individual AES-GCM codificado por la contraseña maestra. Las lecturas no desencadenan una solicitud a menos que el comando realmente toque un secreto (por lo que `rdc machine list` permanece sin solicitudes).

La clave de compromiso (FCK) se deriva en el lado del cliente desde la CEK mediante `HKDF-SHA256(ikm=CEK, salt=fckSalt, info="rediacc-config-fck-v1")` con una sal por configuración. Rotar `fckSalt` invalida todos los compromisos anteriores, forzando un recálculo completo: útil al rotar CEK.
