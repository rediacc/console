---
title: Guía de migración
description: Migrar proyectos existentes a repositorios cifrados de Rediacc.
category: Guides
order: 11
language: es
sourceHash: "4517142676f9fa8f"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Guía de migración

Migre un proyecto existente, archivos, servicios Docker, bases de datos, desde un servidor tradicional o un entorno de desarrollo local a un repositorio cifrado de Rediacc.

## Requisitos previos

- CLI `rdc` instalado ([Instalación](/es/docs/installation))
- Una máquina agregada y aprovisionada ([Configuración](/es/docs/setup))
- Suficiente espacio en disco en el servidor para su proyecto (verifique con `rdc machine query`)

## Paso 1: Crear un repositorio

Cree un repositorio cifrado con tamaño suficiente para su proyecto. Asigne espacio adicional para imágenes Docker y datos de contenedores.

```bash
rdc repo create --name my-project -m server-1 --size 20G
```

> **Consejo:** Puede redimensionar más tarde con `rdc repo resize` si es necesario, pero el repositorio debe estar desmontado primero. Es más fácil comenzar con suficiente espacio.

## Paso 2: Subir sus archivos

Use `rdc repo sync upload` para transferir los archivos de su proyecto al repositorio.

```bash
# Vista previa de lo que se transferirá (sin cambios)
rdc repo sync upload -m server-1 -r my-project --local ./my-project --dry-run

# Subir archivos
rdc repo sync upload -m server-1 -r my-project --local ./my-project
```

El repositorio debe estar montado antes de subir archivos. Si aún no lo está:

```bash
rdc repo mount --name my-project -m server-1
```

Para sincronizaciones posteriores donde desea que el remoto coincida exactamente con su directorio local:

```bash
rdc repo sync upload -m server-1 -r my-project --local ./my-project --mirror
```

> La opción `--mirror` elimina archivos en el remoto que no existen localmente. Use `--dry-run` primero para verificar.

## Paso 3: Corregir la propiedad de archivos

Los archivos subidos llegan con el UID de su usuario local (por ejemplo, 1000). Rediacc usa un usuario universal (UID 7111) para que VS Code, sesiones de terminal y herramientas tengan acceso consistente. Ejecute el comando de propiedad para convertir:

```bash
rdc repo ownership --name my-project -m server-1
```

### Exclusión compatible con Docker

Si hay contenedores Docker en ejecución (o se han ejecutado), el comando de propiedad detecta automáticamente sus directorios de datos escribibles y **los omite**. Esto evita romper contenedores que administran sus propios archivos con UIDs diferentes (por ejemplo, MariaDB usa UID 999, Nextcloud usa UID 33).

El comando informa lo que hace:

```
Excluding Docker volume: database/data
Excluding Docker volume: redis/data
Ownership set to UID 7111 (245 changed, 4 skipped, 0 errors)
```

### Cuándo ejecutar

- **Después de subir archivos**, para convertir su UID local a 7111
- **Después de iniciar contenedores**, si desea que los directorios de volúmenes Docker se excluyan automáticamente. Si los contenedores aún no se han iniciado, no hay volúmenes que excluir y se cambia la propiedad de todos los directorios (lo cual está bien, los contenedores recrearán sus datos en el primer inicio)

### Modo forzado

Para omitir la detección de volúmenes Docker y cambiar la propiedad de todo, incluidos los directorios de datos de contenedores:

```bash
rdc repo ownership --name my-project -m server-1
```

> **Advertencia:** Esto puede romper contenedores en ejecución. Deténgalos primero con `rdc repo down` si es necesario.

### UID personalizado

Para establecer un UID diferente al predeterminado 7111:

```bash
rdc repo ownership --name my-project -m server-1 --uid 1000
```

> **Precaución:** `7111` es el UID universal de Rediacc utilizado en todas partes (coincide con el usuario `rediacc` integrado en la imagen del devcontainer). Solo anúlelo con `--uid` para compatibilidad con versiones anteriores con archivos propiedad de un UID externo específico; **no** es un destino de migración. Los nuevos repositorios deben mantener el valor predeterminado.

## Paso 4: Configurar su Rediaccfile

Cree un `Rediaccfile` en la raíz de su proyecto. Este script Bash define cómo se inician y detienen sus servicios.

```bash
#!/bin/bash

up() {
    renet compose -- up -d
}

down() {
    renet compose -- down
}
```

Las dos funciones del ciclo de vida:

| Función | Propósito | Comportamiento ante errores |
|---------|-----------|---------------------------|
| `up()` | Iniciar servicios | Fallo en raíz es crítico; fallos en subdirectorios se registran y continúan |
| `down()` | Detener servicios | Mejor esfuerzo: siempre intenta todo |

> **Importante:** Use siempre `renet compose --` en lugar de `docker compose` en su Rediaccfile. El wrapper `renet compose` impone la red de host, las capacidades de checkpoint/restore de CRIU, la asignación de IP y el descubrimiento de servicios requeridos por renet-proxy. Usar `docker compose` directamente omite todo esto y será rechazado durante la validación.
>
> Nunca use `sudo docker` tampoco, `sudo` restablece las variables de entorno, incluyendo `DOCKER_HOST`, lo que causa que los contenedores se creen en el Docker daemon del sistema en lugar del daemon aislado del repositorio. Las funciones del Rediaccfile ya se ejecutan con privilegios suficientes.

Vea [Servicios](/es/docs/services) para detalles completos sobre Rediaccfiles, diseños multi-servicio y orden de ejecución.

## Paso 5: Configurar la red de servicios

Rediacc ejecuta un Docker daemon aislado por repositorio. Los servicios usan `network_mode: host` y se vinculan a IPs de loopback únicas para que puedan usar puertos estándar sin conflictos entre repositorios.

### Adaptar su docker-compose.yml

**Antes (tradicional):**

```yaml
services:
  postgres:
    image: postgres:16
    ports:
      - "5432:5432"
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  app:
    image: my-app:latest
    ports:
      - "8080:8080"
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
```

**Después (Rediacc):**

```yaml
services:
  postgres:
    image: postgres:16
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret

  redis:
    image: redis:7-alpine

  app:
    image: my-app:latest
    environment:
      DATABASE_URL: postgresql://postgres:secret@postgres:5432/mydb
      REDIS_URL: redis://redis:6379
      LISTEN_ADDR: 0.0.0.0:8080
```

Cambios principales:

1. **Eliminar las asignaciones de `ports:`** - `renet compose` usa red de host y elimina las asignaciones de puertos automáticamente
2. **Eliminar `network_mode: host`** - `renet compose` lo agrega automáticamente
3. **Las políticas de reinicio son seguras de mantener** - renet las elimina automáticamente para compatibilidad con CRIU y el watchdog del router recupera automáticamente los contenedores detenidos
4. **Usar nombres de servicio para conexiones entre servicios** (p. ej. `postgres`, `redis`) - renet inyecta cada nombre de servicio como un nombre de host resolvible. No incruste IPs directas en cadenas de conexión que se almacenen en bases de datos o archivos de configuración; use el nombre del servicio para mantener el aislamiento de forks
5. **El binding es automático** - el kernel reescribe `bind()` a la IP de loopback correcta. Los servicios pueden usar `0.0.0.0` o `localhost`

Las variables `{SERVICE}_IP` siguen disponibles si las necesitas, pero el binding explícito ya no es necesario. El binding ocurre automáticamente. La convención de nombres: mayúsculas, guiones reemplazados por guiones bajos, sufijo `_IP`. Por ejemplo, `listmonk-app` se convierte en `LISTMONK_APP_IP`.

Vea [Red de servicios](/es/docs/services#service-networking-rediaccjson) para detalles sobre la asignación de IP y `.rediacc.json`.

## Paso 6: Iniciar servicios

Monte el repositorio (si no está montado ya) e inicie todos los servicios:

```bash
rdc repo up --name my-project -m server-1
```

Esto hará:
1. Montar el repositorio cifrado
2. Iniciar el Docker daemon aislado
3. Generar automáticamente `.rediacc.json` con las asignaciones de IP de servicios
4. Ejecutar `up()` de todos los Rediaccfiles

Verifique que sus contenedores estén ejecutándose:

```bash
rdc machine containers --name server-1
```

## Paso 7: Habilitar inicio automático (Opcional)

Por defecto, los repositorios deben montarse e iniciarse manualmente después de un reinicio del servidor. Habilite el inicio automático para que sus servicios arranquen automáticamente:

```bash
rdc repo autostart enable --name my-project -m server-1
```

Se le pedirá la frase de contraseña del repositorio.

> **Nota de seguridad:** El inicio automático almacena un archivo de clave LUKS en el servidor. Cualquier persona con acceso root puede montar el repositorio sin la frase de contraseña. Vea [Inicio automático](/es/docs/services#autostart-on-boot) para más detalles.

## Escenarios comunes de migración

### WordPress / PHP con base de datos

```
my-wordpress/
├── Rediaccfile
├── docker-compose.yml
├── app/                    # Archivos de WordPress (UID 33 en ejecución)
├── database/data/          # Datos de MariaDB (UID 999 en ejecución)
└── wp-content/uploads/     # Archivos subidos por usuarios
```

1. Suba los archivos de su proyecto
2. Inicie los servicios primero (`rdc repo up`) para que los contenedores creen sus directorios de datos
3. Ejecute la corrección de propiedad, los directorios de datos de MariaDB y la aplicación se excluyen automáticamente

### Node.js / Python con Redis

```
my-api/
├── Rediaccfile
├── docker-compose.yml
├── src/                    # Código fuente de la aplicación
├── node_modules/           # Dependencias
└── redis-data/             # Persistencia de Redis (UID 999 en ejecución)
```

1. Suba su proyecto (considere excluir `node_modules` y descargarlos en `up()`)
2. Ejecute la corrección de propiedad después de que los contenedores hayan iniciado

### Proyecto Docker personalizado

Para cualquier proyecto con servicios Docker:

1. Subir archivos del proyecto
2. Adaptar `docker-compose.yml` (vea el Paso 5)
3. Crear un `Rediaccfile` con funciones de ciclo de vida
4. Ejecutar la corrección de propiedad
5. Iniciar servicios

## Solución de problemas

### Permiso denegado después de subir

Los archivos aún tienen su UID local. Ejecute el comando de propiedad:

```bash
rdc repo ownership --name my-project -m server-1
```

### El contenedor no inicia

Compruebe que los servicios estén en ejecución y revise sus registros:

```bash
# Verificar IPs asignadas
rdc term connect -m server-1 -r my-project -c "cat .rediacc.json"

# Verificar logs del contenedor
rdc term connect -m server-1 -r my-project -c "docker logs <container-name>"
```

### Conflicto de puertos entre repositorios

Cada repositorio obtiene IPs de loopback únicas y el kernel reescribe automáticamente las llamadas `bind()` a la IP correcta. Los conflictos de puertos entre repositorios no ocurren. Si observas un comportamiento inesperado, verifica que los servicios se inicien mediante `renet compose` (no `docker compose`). Para conectarte a otros servicios, usa el nombre del servicio (p. ej. `postgres`) en lugar de IPs directas. Los nombres de servicio se resuelven correctamente en cada fork.

### La corrección de propiedad rompe contenedores

Si ejecutaste `rdc repo ownership` y un contenedor dejó de funcionar, los archivos de datos del contenedor tuvieron su propietario cambiado. Detén el contenedor, elimina su directorio de datos y reinícialo. El contenedor lo recreará:

```bash
rdc repo down --name my-project -m server-1
# Eliminar el directorio de datos del contenedor (por ejemplo, database/data)
rdc repo up --name my-project -m server-1
```
