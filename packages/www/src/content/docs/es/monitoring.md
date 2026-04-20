---
title: Monitoreo
description: >-
  Monitoree el estado de las máquinas, contenedores, servicios, repositorios y
  ejecute diagnósticos.
category: Guides
order: 9
language: es
sourceHash: "1b60f9a60324f737"
sourceCommit: "5c97ef070ea0c474b03651ceea03433b3f48abcd"
---

# Monitoreo

Rediacc proporciona comandos de monitoreo integrados para inspeccionar el estado de las máquinas, contenedores en ejecución, servicios, estado de repositorios y diagnósticos del sistema.

## Estado de la Máquina

Obtenga un informe completo del estado de una máquina:

```bash
rdc machine health --name server-1
```

Esto reporta:
- **Sistema**: tiempo de actividad, uso de disco, uso del datastore
- **Contenedores**: conteos de en ejecución, saludables, no saludables
- **Almacenamiento**: estado SMART
- **Problemas**: problemas identificados

Use `--output json` para salida legible por máquinas.

## Listar Contenedores

Vea todos los contenedores en ejecución en todos los repositorios de una máquina:

```bash
rdc machine containers --name server-1
```

| Columna | Descripción |
|---------|-------------|
| Name | Nombre del contenedor |
| Status | Tiempo de actividad o motivo de salida |
| State | En ejecución, detenido, etc. |
| Health | Saludable, no saludable, ninguno |
| CPU | Porcentaje de uso de CPU |
| Memory | Uso de memoria / límite |
| Repository | Qué repositorio es propietario del contenedor |

Opciones:
- `--health-check`, Realizar verificaciones de estado activas en los contenedores
- `--output json`, Salida JSON legible por máquinas

La salida JSON incluye todos los detalles del contenedor (`labels`, `port_mappings`, `image`, `id`) además de `repository` (nombre resuelto), `repository_guid` (GUID original), `domain` y `autoRoute`.

## Listar Servicios

Vea los servicios systemd relacionados con Rediacc en una máquina:

```bash
rdc machine services --name server-1
```

| Columna | Descripción |
|---------|-------------|
| Name | Nombre del servicio |
| State | Activo, inactivo, fallido |
| Sub-state | En ejecución, muerto, etc. |
| Restarts | Conteo de reinicios |
| Memory | Uso de memoria del servicio |
| Repository | Repositorio asociado |

Opciones:
- `--stability-check`, Marcar servicios inestables (fallidos, >3 reinicios, reinicio automático)
- `--output json`, Salida JSON legible por máquinas

La salida JSON incluye todos los detalles del servicio con `repository` (nombre resuelto) y `repository_guid` (GUID original).

## Listar Repositorios

Vea los repositorios en una máquina con estadísticas detalladas:

```bash
rdc machine repos --name server-1
```

| Columna | Descripción |
|---------|-------------|
| Name | Nombre del repositorio |
| Size | Tamaño de la imagen de disco |
| Mount | Montado o desmontado |
| Docker | Daemon Docker en ejecución o detenido |
| Containers | Conteo de contenedores |
| Disk Usage | Uso de disco real dentro del repositorio |
| Modified | Hora de última modificación |

Opciones:
- `--search <text>`, Filtrar por nombre o ruta de montaje
- `--output json`, Salida JSON legible por máquinas

La salida JSON incluye `name` (resuelto) y `guid` (GUID original), y anida para cada repositorio los arreglos `containers` (con `domain`, `autoRoute`, `repository`/`repository_guid`) y `services`.

## Salud del Almacenamiento

Inspeccione la fragmentación de BTRFS y el uso compartido de reflinks en todos los repositorios de una máquina:

```bash
rdc machine query --name server-1 --storage-health
```

| Columna | Descripción |
|---------|-------------|
| Size | Tamaño del archivo de imagen LUKS (cómo se ve el repositorio) |
| Unique | Datos únicos reales que pertenecen solo a este repositorio |
| Shared | Bloques de datos reutilizados entre repositorios mediante reflinks de BTRFS (copias gratuitas) |
| Extents | Número de extents de archivos (mayor = más fragmentado) |
| Frag | Nivel de fragmentación: bajo, moderado o alto |

El resumen muestra el ahorro total de los reflinks de BTRFS:

```
14 repos, 224.3 GB virtual size
Unique data: 323.7 MB | Shared: 224.0 GB | Efficiency: 99.9%
```

- **Tamaño virtual** es la suma de todos los tamaños de imagen de repositorio. Esto es lo que parecen los repositorios, pero cuenta doble los bloques compartidos mediante reflinks.
- **Datos únicos** es el almacenamiento real consumido por datos de repositorio que existen en un solo repositorio. Esto es lo que liberaría al eliminar un repositorio.
- **Compartido** son datos reutilizados entre repositorios mediante reflinks de BTRFS. Bifurcar un repositorio crea copias reflink que comparten bloques hasta que cualquiera de los lados escribe nuevos datos, momento en que los bloques divergen.
- **Eficiencia** es el porcentaje de datos reutilizados mediante reflinks. Mayor es mejor. Una máquina con muchas bifurcaciones del mismo repositorio padre mostrará eficiencia cercana al 100%.

Los repositorios con alta fragmentación y cero bloques compartidos pueden defragmentarse de forma segura con `btrfs filesystem defragment`. Los repositorios con bloques compartidos NO deben defragmentarse porque la defragmentación reemplaza los bloques compartidos con copias únicas, aumentando el uso del disco.

El escaneo se ejecuta en paralelo y tarda entre 5 y 15 segundos según el número y tamaño de los repositorios. Cuando no se especifica `--storage-health`, aparece una sugerencia de una línea después de la salida de la consulta como recordatorio.

## Scrub de BTRFS

Rediacc programa automáticamente un scrub semanal de BTRFS en cada máquina. El scrub lee cada bloque de datos en el datastore, verifica los checksums y reporta cualquier corrupción. Esto detecta la corrupción silenciosa de datos (bitrot) antes de que se propague a los respaldos y bifurcaciones.

El scrub se ejecuta todos los domingos a las 02:00 hora local (zona horaria de la máquina) con un retraso aleatorio de hasta 1 hora. Se ejecuta con la prioridad de E/S más baja (`ionice idle`, `nice 19`) para no interferir con los servicios en ejecución. En máquinas respaldadas por SSD, espere aproximadamente 8 minutos por cada 100 GB de datastore.

El temporizador del scrub se instala automáticamente en el primer inicio del daemon después de una actualización de renet. Cuando la política de scrub cambia en una versión futura de renet, se actualiza sola en el siguiente inicio del daemon sin ninguna acción del usuario.

### Estado del scrub

El resultado del último scrub se guarda fuera del volumen BTRFS (en `/var/lib/rediacc/scrub-last-result.json`) para que permanezca legible incluso si el volumen tiene problemas. La salida de `rdc machine query --system` incluye un campo `scrub_status`:

```json
"scrub_status": {
  "last_run_human": "3 days ago",
  "status": "ok",
  "total_errors": 0,
  "uncorrectable": 0,
  "duration_seconds": 312
}
```

| Estado | Significado |
|--------|-------------|
| `ok` | El último scrub se completó sin errores |
| `never_run` | El scrub aún no se ha ejecutado (el temporizador acaba de instalarse) |
| `overdue` | El último scrub fue hace más de 14 días |
| `errors_found` | El scrub encontró discrepancias de checksum (revise los conteos `total_errors` y `uncorrectable`) |
| `failed` | El proceso de scrub salió con un código distinto de cero |

Si `uncorrectable` es mayor que cero, los bloques afectados no se pueden reparar automáticamente (BTRFS de un solo disco no tiene copia redundante). Restaure el repositorio afectado desde el respaldo más reciente.

### Scrub manual

Para ejecutar un scrub inmediatamente (por ejemplo, después de un corte de energía o una migración de disco):

```bash
rdc term connect -m server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

El resultado se guarda en el mismo archivo JSON y es visible de inmediato en el siguiente `rdc machine query --system`.

## Estado del Vault

Obtenga una visión general completa de una máquina incluyendo información de despliegue:

```bash
rdc machine vault-status --name server-1
```

Esto proporciona:
- Nombre del host y tiempo de actividad
- Uso de memoria, disco y datastore
- Total de repositorios, conteo de montados, conteo de Docker en ejecución
- Información detallada por repositorio

Use `--output json` para salida legible por máquinas.

## Probar Conexión

> **Solo adaptador cloud.** Con el adaptador local, use `rdc term connect -m server-1 -c "hostname"` para verificar la conectividad.

Verifique la conectividad SSH a una máquina:

```bash
rdc machine test-connection --ip 203.0.113.50 --user deploy
```

Reporta:
- Estado de la conexión (exitosa/fallida)
- Método de autenticación utilizado
- Configuración de la clave SSH
- Estado del despliegue de la clave pública
- Entrada de hosts conocidos

Opciones:
- `--port <number>`, Puerto SSH (predeterminado: 22)
- `--save -m server-1`, Guardar la clave del host verificada en la configuración de la máquina

## Diagnósticos (doctor)

Ejecute una verificación de diagnóstico completa de su entorno Rediacc:

```bash
rdc doctor
```

| Categoría | Verificaciones |
|----------|--------|
| **Entorno** | Versión de Node.js, versión de la CLI, modo SEA, instalación de Go, disponibilidad de Docker |
| **Renet** | Ubicación del binario, versión, CRIU, rsync, activos embebidos SEA |
| **Configuración** | Configuración activa, adaptador, máquinas, clave SSH |
| **Virtualización** | Verifica si su sistema puede ejecutar máquinas virtuales locales (`rdc ops`) |

Cada verificación reporta **OK**, **Advertencia** o **Error**. Use esto como primer paso al resolver cualquier problema.

Códigos de salida: `0` = todo pasó, `1` = advertencias, `2` = errores.
