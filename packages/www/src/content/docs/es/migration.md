---
title: "Guía de migración"
description: "Migrar proyectos existentes a repositorios cifrados de Rediacc."
category: "Guides"
order: 11
language: es
---

# Guía de migración

Migre un proyecto existente — archivos, servicios Docker, bases de datos — desde un servidor tradicional o un entorno de desarrollo local a un repositorio cifrado de Rediacc.

## Requisitos previos

- CLI `rdc` instalado ([Instalación](/es/docs/installation))
- Una máquina agregada y aprovisionada ([Configuración](/es/docs/setup))
- Suficiente espacio en disco en el servidor para su proyecto (verifique con `rdc machine status`)

## Paso 1: Crear un repositorio

Cree un repositorio cifrado con tamaño suficiente para su proyecto. Asigne espacio adicional para imágenes Docker y datos de contenedores.

```bash
rdc repo create my-project -m server-1 --size 20G
```

> **Consejo:** Puede redimensionar más tarde con `rdc repo resize` si es necesario, pero el repositorio debe estar desmontado primero. Es más fácil comenzar con suficiente espacio.

## Paso 2: Subir sus archivos

Use `rdc sync upload` para transferir los archivos de su proyecto al repositorio.

```bash
# Vista previa de lo que se transferirá (sin cambios)
rdc sync upload -m server-1 -r my-project --local ./my-project --dry-run

# Subir archivos
rdc sync upload -m server-1 -r my-project --local ./my-project
```

El repositorio debe estar montado antes de subir archivos. Si aún no lo está:

```bash
rdc repo mount my-project -m server-1
```

Para sincronizaciones posteriores donde desea que el remoto coincida exactamente con su directorio local:

```bash
rdc sync upload -m server-1 -r my-project --local ./my-project --mirror
```

> La opción `--mirror` elimina archivos en el remoto que no existen localmente. Use `--dry-run` primero para verificar.

## Paso 3: Corregir la propiedad de archivos

Los archivos subidos llegan con el UID de su usuario local (por ejemplo, 1000). Rediacc usa un usuario universal (UID 7111) para que VS Code, sesiones de terminal y herramientas tengan acceso consistente. Ejecute el comando de propiedad para convertir:

```bash
rdc repo ownership my-project -m server-1
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

- **Después de subir archivos** — para convertir su UID local a 7111
- **Después de iniciar contenedores** — si desea que los directorios de volúmenes Docker se excluyan automáticamente. Si los contenedores aún no se han iniciado, no hay volúmenes que excluir y se cambia la propiedad de todos los directorios (lo cual está bien — los contenedores recrearán sus datos en el primer inicio)

### Modo forzado

Para omitir la detección de volúmenes Docker y cambiar la propiedad de todo, incluidos los directorios de datos de contenedores:

```bash
rdc repo ownership my-project -m server-1 --force
```

> **Advertencia:** Esto puede romper contenedores en ejecución. Deténgalos primero con `rdc repo down` si es necesario.

### UID personalizado

Para establecer un UID diferente al predeterminado 7111:

```bash
rdc repo ownership my-project -m server-1 --uid 1000
```

## Paso 4: Configurar su Rediaccfile

Cree un `Rediaccfile` en la raíz de su proyecto. Este script Bash define cómo se preparan, inician y detienen sus servicios.

```bash
#!/bin/bash

prep() {
    docker compose pull
}

up() {
    docker compose up -d
}

down() {
    docker compose down
}
```

Las tres funciones del ciclo de vida:

| Función | Propósito | Comportamiento ante errores |
|---------|-----------|---------------------------|
| `prep()` | Descargar imágenes, ejecutar migraciones, instalar dependencias | Fallo rápido: cualquier fallo detiene todo |
| `up()` | Iniciar servicios | Fallo en raíz es crítico; fallos en subdirectorios se registran y continúan |
| `down()` | Detener servicios | Mejor esfuerzo: siempre intenta todo |

> **Importante:** Use `docker` directamente en su Rediaccfile — nunca `sudo docker`. El comando `sudo` restablece las variables de entorno, lo que causa que `DOCKER_HOST` se pierda y los contenedores se creen en el Docker daemon del sistema en lugar del daemon aislado del repositorio. Las funciones del Rediaccfile ya se ejecutan con privilegios suficientes. Vea [Servicios](/es/docs/services#environment-variables) para más detalles.

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
    network_mode: host
    restart: unless-stopped
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD: secret
    command: -c listen_addresses=${POSTGRES_IP} -c port=5432

  redis:
    image: redis:7-alpine
    network_mode: host
    restart: unless-stopped
    command: redis-server --bind ${REDIS_IP} --port 6379

  app:
    image: my-app:latest
    network_mode: host
    restart: unless-stopped
    environment:
      DATABASE_URL: postgresql://postgres:secret@${POSTGRES_IP}:5432/mydb
      REDIS_URL: redis://${REDIS_IP}:6379
      LISTEN_ADDR: ${APP_IP}:8080
```

Cambios principales:

1. **Agregar `network_mode: host`** a cada servicio
2. **Eliminar las asignaciones de `ports:`** (no son necesarias con red de host)
3. **Vincular servicios a variables de entorno `${SERVICE_IP}`** (inyectadas automáticamente por Rediacc)
4. **Referenciar otros servicios por su IP** en lugar de nombres DNS de Docker (por ejemplo, `${POSTGRES_IP}` en lugar de `postgres`)

Las variables `{SERVICE}_IP` se generan automáticamente a partir de los nombres de servicio de su archivo compose. La convención de nombres: mayúsculas, guiones reemplazados por guiones bajos, con sufijo `_IP`. Por ejemplo, `listmonk-app` se convierte en `LISTMONK_APP_IP`.

Vea [Red de servicios](/es/docs/services#service-networking-rediaccjson) para detalles sobre la asignación de IP y `.rediacc.json`.

## Paso 6: Iniciar servicios

Monte el repositorio (si no está montado ya) e inicie todos los servicios:

```bash
rdc repo up my-project -m server-1 --mount
```

Esto hará:
1. Montar el repositorio cifrado
2. Iniciar el Docker daemon aislado
3. Generar automáticamente `.rediacc.json` con las asignaciones de IP de servicios
4. Ejecutar `prep()` de todos los Rediaccfiles
5. Ejecutar `up()` de todos los Rediaccfiles

Verifique que sus contenedores estén ejecutándose:

```bash
rdc machine containers server-1
```

## Paso 7: Habilitar inicio automático (Opcional)

Por defecto, los repositorios deben montarse e iniciarse manualmente después de un reinicio del servidor. Habilite el inicio automático para que sus servicios arranquen automáticamente:

```bash
rdc repo autostart enable my-project -m server-1
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
3. Ejecute la corrección de propiedad — los directorios de datos de MariaDB y la aplicación se excluyen automáticamente

### Node.js / Python con Redis

```
my-api/
├── Rediaccfile
├── docker-compose.yml
├── src/                    # Código fuente de la aplicación
├── node_modules/           # Dependencias
└── redis-data/             # Persistencia de Redis (UID 999 en ejecución)
```

1. Suba su proyecto (considere excluir `node_modules` y descargarlos en `prep()`)
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
rdc repo ownership my-project -m server-1
```

### El contenedor no inicia

Verifique que los servicios se vinculen a su IP asignada, no a `0.0.0.0` o `localhost`:

```bash
# Verificar IPs asignadas
rdc term server-1 my-project -c "cat .rediacc.json"

# Verificar logs del contenedor
rdc term server-1 my-project -c "docker logs <container-name>"
```

### Conflicto de puertos entre repositorios

Cada repositorio obtiene IPs de loopback únicas. Si ve conflictos de puertos, verifique que su `docker-compose.yml` use `${SERVICE_IP}` para la vinculación en lugar de `0.0.0.0`. Los servicios vinculados a `0.0.0.0` escuchan en todas las interfaces y entrarán en conflicto con otros repositorios.

### La corrección de propiedad rompe contenedores

Si ejecutó `rdc repo ownership --force` y un contenedor dejó de funcionar, los archivos de datos del contenedor fueron modificados. Detenga el contenedor, elimine su directorio de datos y reinícielo — el contenedor lo recreará:

```bash
rdc repo down my-project -m server-1
# Eliminar el directorio de datos del contenedor (por ejemplo, database/data)
rdc repo up my-project -m server-1
```
