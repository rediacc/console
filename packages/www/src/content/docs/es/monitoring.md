---
title: Monitoreo
description: >-
  Monitoree el estado de máquinas, contenedores, servicios, repositorios y
  ejecute diagnósticos.
category: Guides
order: 9
language: es
sourceHash: "e2f5d37c534fc40d"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Monitoreo

Rediacc proporciona comandos de monitoreo para inspeccionar el estado de las máquinas, contenedores en ejecución, servicios, estado de repositorios y diagnósticos del sistema.

## Estado de la Máquina

Obtenga un informe de estado completo de una máquina:

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
| Quota | El tamaño máximo del repositorio (su techo de crecimiento, establecido en la creación o mediante resize/auto-grow) |
| Allocated | Lo que la imagen sparse ocupa actualmente en el pool |
| Unique | Datos únicos reales que pertenecen solo a este repositorio |
| Shared | Bloques de datos reutilizados entre repositorios mediante reflinks de BTRFS (copias gratuitas) |
| Reclaimable | La diferencia entre lo asignado y lo usado que [`repo trim`](/es/docs/repositories#recuperar-espacio-trim) puede devolver al pool. Muestra `-` para repositorios desmontados |
| Discards | Si el volumen cifrado pasa los descartes (`on` para cualquier repositorio montado con una versión actual) |
| Divergence | Porcentaje de la imagen que es único de este repositorio y no compartido (mayor significa más recuperable si se elimina) |
| Frag | Extents por GB en la imagen copy-on-write (solo informativo) |

La cuota y la asignación son números distintos a propósito: un repositorio con una cuota de 20 GB que almacena 6 GB de datos solo le cuesta al pool lo que tiene asignado. El pool puede por lo tanto comprometer una cuota total mayor de la que tiene físicamente, y la columna Reclaimable muestra cuánto de la asignación de cada repositorio ya no está en uso y puede recuperarse mediante trim.

Por debajo de la tabla, un resumen del pool reporta el nivel de llenado del datastore y cuánto espacio están anclando los snapshots de respaldo:

```
Pool: 265.4 GB used, 95.2 GB free (73.6% full)
Backup snapshots pin 2.1 GB (1 active, 0 stale; stale ones are removed by 'rdc machine prune')
```

Mientras se ejecuta un respaldo, su snapshot sigue referenciando todos los bloques que comparte con los repositorios activos, por lo que las eliminaciones y los trims liberan menos espacio en el pool hasta que ese ciclo de respaldo termina y el snapshot se elimina. Los snapshots obsoletos de respaldos interrumpidos se eliminan automáticamente por el mantenedor de almacenamiento en pocos minutos.

El resumen muestra el ahorro total de los reflinks de BTRFS:

```
14 repos, 224.3 GB virtual size
Unique data: 323.7 MB | Shared: 224.0 GB | Efficiency: 99.9%
```

- **Tamaño virtual** es la suma de todos los tamaños de imagen de repositorio. Esto es lo que parecen los repositorios, pero cuenta doble los bloques compartidos mediante reflinks.
- **Datos únicos** es el almacenamiento real consumido por datos de repositorio que existen en un solo repositorio. Esto es lo que liberaría al eliminar un repositorio.
- **Compartido** son datos reutilizados entre repositorios mediante reflinks de BTRFS. Bifurcar un repositorio crea copias reflink que comparten bloques hasta que cualquiera de los lados escribe nuevos datos, momento en que los bloques divergen.
- **Eficiencia** es el porcentaje de datos reutilizados mediante reflinks. Mayor es mejor. Una máquina con muchas bifurcaciones del mismo repositorio padre mostrará eficiencia cercana al 100%.

La columna Frag es solo informativa. Cuenta los extents del archivo de imagen copy-on-write, no los archivos que lee tu aplicación dentro de él, por lo que aparece alta bajo cargas de trabajo de escritura aleatoria normales (bases de datos, capas de contenedores) y no predice el rendimiento de lectura en almacenamiento respaldado por SSD. Rediacc deliberadamente no ofrece un comando de defragmentación: `btrfs filesystem defragment` descomparte los forks y snapshots reflinkeados, lo que en un pool casi lleno puede inflar el uso de forma considerable mientras los benchmarks no muestran ninguna ganancia de lectura medible. Para las mediciones completas y el razonamiento, consulta [Tu número de fragmentación parece aterrador. Medí lo que cuesta.](/es/blog/i-benchmarked-btrfs-fragmentation).

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

## Visión General de la Máquina

Obtenga una visión general completa de una máquina incluyendo información de despliegue:

```bash
rdc machine query --name server-1
```

Esto proporciona:
- Nombre del host y tiempo de actividad
- Uso de memoria, disco y datastore
- Total de repositorios, conteo de montados, conteo de Docker en ejecución
- Información detallada por repositorio

Use `--output json` para salida legible por máquinas.

## Probar Conexión

Verifique la conectividad SSH a una máquina:

```bash
rdc term connect -m server-1 -c "hostname"
```

El comando imprime el nombre de host remoto si tiene éxito, o un error de
conexión en caso contrario, lo que verifica el DNS, el puerto SSH y la
autenticación por clave en un solo paso.

## Diagnósticos (doctor)

Ejecuta una verificación de diagnóstico completa de tu entorno Rediacc:

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

## Comprobaciones de disponibilidad de servicios

Durante `repo up`, renet espera a que los servicios HTTP acepten conexiones antes de declararlos listos. La espera tiene en cuenta las comprobaciones de estado:

- Los contenedores que Docker reporta como **sanos** se aceptan de inmediato, sin sonda TCP.
- Los contenedores que aún están dentro del `start_period` de su comprobación de estado registran una nota informativa, no una advertencia; el proxy sigue reintentando hasta que estén disponibles.
- Los servicios de Compose sin ningún contenedor en ejecución (por ejemplo, detrás de un perfil inactivo) se omiten.
- Todo lo demás se sondea por TCP durante un máximo de 15 segundos (modifique este valor con `REDIACC_READINESS_TIMEOUT`, en segundos).

Definir una [comprobación de estado de Docker](https://docs.docker.com/reference/dockerfile/#healthcheck) en servicios de arranque lento le proporciona a renet una señal de disponibilidad fiable y elimina el ruido de sondas en la salida del despliegue.
