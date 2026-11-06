---
title: Monitoreo
description: >-
  Monitoree el estado de máquinas, contenedores, servicios, repositorios y
  ejecute diagnósticos.
category: Guides
tags:
  - operations
subcategory: operations
order: 9
language: es
sourceHash: "acef592a7065cac7"
sourceCommit: "9f58d83e01b4d46f8ce31af467a203b4d195e801"
---

# Monitoreo

Rediacc proporciona comandos de monitoreo para inspeccionar el estado de las máquinas, contenedores en ejecución, servicios, estado de repositorios y diagnósticos del sistema.

## Estado de la Máquina

Obtenga un informe de estado completo de una máquina:

```bash
rdc machine health server-1
```

Esto reporta:
- **Sistema**: tiempo de actividad, memoria (advertencia por encima del 80 %, error por encima del 90 %), uso de disco y del datastore (advertencia por encima del 85 %, error por encima del 95 %)
- **Contenedores**: conteos de en ejecución, saludables y no saludables; un contenedor en bucle de `Restarting` es crítico
- **Servicios**: unidades de systemd fallidas (un error) y unidades que se reinician sin parar (crítico)
- **Almacenamiento**: estado de salud SMART (un disco que falla es crítico) y temperatura del disco
- **Repositorios**: repositorios de inicio automático que no están montados y el uso del sistema de archivos de cada repositorio (advertencia por encima del 85 %, error por encima del 95 %)
- **Copias de seguridad**: repositorios sin copia en más de 10 días, atrasados respecto a su programación o destino, o cuya última verificación falló
- **Licencias**: licencias de repositorio caducadas, ausentes, que no coinciden o no válidas, y licencias que deben renovarse
- **Procesos de renet**: demonios que siguen ejecutando un binario de renet reemplazado
- **Salud del repositorio**: el resultado de `health()` de cada repositorio montado (véase abajo)
- **Certificados**: certificados del proxy próximos a caducar y CNAME de desafío ACME compartidos
- **Problemas**: problemas identificados

El código de salida es el veredicto: `0` sin hallazgos (un repositorio sin comprobación `health()` se lista como «sin comprobación», nunca se cuenta como saludable), `1` advertencia, `2` error, `3` crítico (un disco que falla, o un contenedor o servicio en bucle de reinicios). Use `--output json` para salida legible por máquinas; incluye `repo_health` (un informe por repositorio) y `findings`, cada uno con un código, una gravedad (`info`, `warning`, `error` o `critical`), un sujeto, un detalle y, cuando existe una solución, `fix` (véase [Reparación](#repair)).

## Salud del repositorio

Un Rediaccfile puede definir una función `health()` que comprueba los servicios del propio repositorio ([Servicios](/es/docs/services)): salida `0` ok, `1` advertencia, `2` error. Ejecútela para un repositorio:

```bash
rdc repo health my-app@server-1
```

El comando termina con el peor nivel de todos los Rediaccfiles del repositorio. Un repositorio en el que ningún Rediaccfile define `health()` imprime **sin comprobación** y termina con `0`; nunca se informa como saludable. Un `health()` que agota el tiempo, es terminado o sale con cualquier otro código es un error, igual que no poder alcanzar la máquina (salida `2`).

`rdc machine health` ejecuta el `health()` de cada repositorio montado en una sola llamada e incorpora el peor nivel a su propio código de salida, con un hallazgo por repositorio como advertencia (`repo.health.warning`) o error (`repo.health.error`). Los repositorios sin comprobación se enumeran, no se evalúan. Cuando el renet de la máquina es anterior a las comprobaciones de salud de repositorio, el resultado es una advertencia, `renet.repo-health.unsupported`, hasta que `rdc machine setup` lo actualice.

## Caducidad de certificados y desafíos ACME

`rdc machine health` lee los certificados ACME del proxy e informa `cert.expiry.near` para cada uno a menos de 21 días de caducar (una advertencia) o a menos de 7 días (un error). El proxy renueva con 30 días de antelación, así que un certificado con menos de 21 días significa que su renovación lleva fallando al menos nueve días.

También informa `acme.challenge.cname-shared` cuando el registro `_acme-challenge.<name>` del nombre de un certificado sigue un CNAME hacia un nombre que no es a su vez un nombre `_acme-challenge.`, o cuando dos nombres terminan en el mismo nombre. Un registro comodín que es un CNAME produce esta forma: todos los desafíos llegan a un solo nombre y las renovaciones colisionan. Una delegación deliberada (por ejemplo, `_acme-challenge.mail.example.com` apuntando a `_acme-challenge.mail.example.io`) no se informa; añada cualquier otra delegación prevista a `ACME_DELEGATED_NAMES` (una lista separada por comas de nombres de certificado) en el `config.env` del proxy. Un nombre cuya cadena de desafío no pudo resolverse (ningún resolvedor DNS respondió por él) se informa como `acme.challenge.unknown`, una advertencia, porque la comprobación no se ejecutó para él.

## Reparación

Cada hallazgo lleva un código y, cuando existe una solución segura, un `fix` con `action`, una `class` de seguridad y `window_only`. `rdc machine health` sigue siendo de solo lectura; `rdc machine repair` es el comando que actúa:

```bash
rdc machine repair server-1 --dry-run     # list what would run
rdc machine repair server-1               # run the auto-safe fixes, then re-check
rdc machine repair server-1 --code cert.expiry.near
```

| Clase | Significado |
|---|---|
| `auto-safe` | Se ejecuta por defecto: reiniciar un contenedor o Traefik, recortar y depurar, escribir el ancla ACME |
| `auto-with-backup` | Solo se ejecuta con `--with-backup`, tras una instantánea correcta del repositorio; si la instantánea falla, se cancela la solución |
| `operator-only` | Nunca se ejecuta. El comando imprime el comando exacto que debe ejecutarse a mano. Todo lo que borra datos con nombre o gasta dinero está aquí |

`window_only` es una condición añadida a la clase: la solución se ejecuta solo dentro de la ventana de mantenimiento de la máquina, `HH:MM-HH:MM` en UTC (puede cruzar la medianoche). Una máquina sin ventana nunca ejecuta estas soluciones por sí sola; `--window-override` las ejecuta a mano. Fije o borre la ventana con:

```bash
rdc machine repair server-1 --set-window 00:00-03:00
rdc machine repair server-1 --set-window off
```

Cada solución comprueba primero que su hallazgo sigue presente, así que una segunda ejecución no tiene nada que hacer. Las soluciones que actúan sobre lo mismo se ejecutan una vez (un reinicio de Traefik cubre todos los certificados). Cada solución se registra en el diario de la máquina con la etiqueta `rediacc-repair` y en el JSON `actions` (`code`, `subject`, `action`, `class`, `result`, `before`, `after`), y la ejecución termina con una nueva comprobación completa. El código de salida es `0` cuando no queda nada, `1` cuando quedan advertencias o elementos operator-only, y `2` cuando queda un error o un hallazgo crítico, o falló una solución. `rdc machine repair` nunca sale con `3`; solo `rdc machine health` lo hace.

| Hallazgo | Solución | Clase |
|---|---|---|
| `datastore.usage.high`, `repo.disk.high` | Recortar y luego depurar contenedores detenidos, volúmenes anónimos huérfanos e imágenes sin usar | auto-safe |
| `container.unhealthy`, `container.restart-loop` | Reiniciar el contenedor | auto-safe |
| `renet.binary.replaced` | Reiniciar los supervisores de repositorio afectados (`rdc machine restart-services --include-docker`, limitado a ellos) | auto-safe, solo en ventana |
| `cert.expiry.near` | Reiniciar Traefik para que reintente la renovación | auto-safe |
| `acme.challenge.cname-shared` | Escribir el ancla ACME (abajo) | auto-safe (operator-only cuando se declara una delegación y no existe un token de Cloudflare utilizable) |
| `repo.health.warning`, `repo.health.error` | Ejecutar el `repair()` del repositorio ([Servicios](/es/docs/services)) | la clase que declara el Rediaccfile |
| `repo.unmounted`, `service.failed`, `service.restart-loop`, `backup.*`, `license.*`, `renet.repo-health.unsupported` | Se imprime como el comando que hay que ejecutar | operator-only |

Los hallazgos sin solución (fallos SMART, temperatura, memoria, el disco del sistema, una verificación fallida) se informan y se dejan al operador.

La depuración nunca toca el hub: los contenedores con la etiqueta `rediacc.hub.*` y los volúmenes con la etiqueta `rediacc.hub.user` o con nombre `rediacc-hub-home-*` quedan excluidos, de modo que el directorio personal de un usuario del hub sobrevive a cada recuperación de espacio. Un residuo que el recorte y la depuración no pueden liberar (volúmenes con nombre, datos grandes de aplicaciones) sigue siendo una decisión del operador.

### Reparación de repositorios

```bash
rdc repo repair my-app@server-1 --dry-run
rdc repo repair my-app@server-1
```

`rdc repo repair` ejecuta las funciones `repair()` del repositorio con las mismas clases: `auto-safe` se ejecuta, `auto-with-backup` necesita `--with-backup`, y un `repair()` sin declarar (`operator-only`) se ejecuta solo después de responder a su pregunta o con `--yes`. Después `health()` se ejecuta de nuevo y el código de salida sigue el nivel en que termina: `0` ok o sin comprobación, `1` advertencia, `2` error o un `repair()` fallido.

### El ancla ACME

Un registro DNS comodín que es un CNAME hace que todos los nombres `_acme-challenge.<host>` lo sigan, así que todos los desafíos llegan a un solo nombre y las renovaciones colisionan (`acme.challenge.cname-shared`). La solución escribe un registro TXT con el valor `rediacc-acme-anchor` en cada `_acme-challenge.<name>` en colisión mediante el token de Cloudflare del proxy y luego reinicia Traefik. Un registro explícito saca el nombre del alcance del comodín, de modo que el desafío llega adonde corresponde. La solución solo añade registros y un ancla existente se deja como está. Un nombre de desafío que ya es un CNAME no puede tener un registro TXT a su lado: Cloudflare rechaza la escritura y la solución recurre al mismo plan alternativo que para una zona que su token no puede escribir (siguiente párrafo).

Los nombres incluidos en `ACME_DELEGATED_NAMES` (una lista separada por comas de nombres de certificado en el `config.env` del proxy) son delegaciones deliberadas: nunca se anclan ni se informan. Cuando el proxy no tiene un token de Cloudflare utilizable, la solución recurre a `LEGO_DISABLE_CNAME_SUPPORT=true` en `config.env`, pero solo cuando no se ha declarado ningún nombre delegado, porque esa variable desactiva el seguimiento de CNAME para todos los nombres; con una delegación declarada, el hallazgo sigue siendo operator-only. La misma solución se ejecuta en cada instalación del proxy (`rdc machine infra push`) y por sí sola con `renet proxy acme-fix` en la máquina.

## Listar Contenedores

Vea todos los contenedores en ejecución en todos los repositorios de una máquina:

```bash
rdc machine status server-1 --containers
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
rdc machine status server-1 --services
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
rdc machine status server-1 --repositories
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
rdc machine status server-1 --storage-health
```

| Columna | Descripción |
|---------|-------------|
| Quota | El tamaño máximo del repositorio (su techo de crecimiento, establecido en la creación o mediante resize/auto-grow) |
| Allocated | Lo que la imagen sparse ocupa actualmente en el pool |
| Unique | Datos únicos reales que pertenecen solo a este repositorio |
| Shared | Bloques de datos reutilizados entre repositorios mediante reflinks de BTRFS (copias gratuitas) |
| Reclaimable | La diferencia entre lo asignado y lo usado que [`repo trim`](/es/docs/repositories#reclaim-space-trim) puede devolver al pool. Muestra `-` para repositorios desmontados |
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

El resultado del último scrub se guarda fuera del volumen BTRFS (en `/var/lib/rediacc/scrub-last-result.json`) para que permanezca legible incluso si el volumen tiene problemas. La salida de `rdc machine status --system` incluye un campo `scrub_status`:

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
rdc term connect server-1 -c "sudo renet maintenance scrub --datastore /mnt/rediacc"
```

El resultado se guarda en el mismo archivo JSON y es visible de inmediato en el siguiente `rdc machine status --system`.

## Visión General de la Máquina

Obtenga una visión general completa de una máquina incluyendo información de despliegue:

```bash
rdc machine status server-1
```

Esto proporciona:
- Nombre del host y tiempo de actividad
- Uso de memoria, disco y datastore
- Total de repositorios, conteo de montados, conteo de repositorios cuyo daemon Docker responde
- Información detallada por repositorio

Use `--output json` para salida legible por máquinas.

## Probar Conexión

Verifique la conectividad SSH a una máquina:

```bash
rdc term connect server-1 -c "hostname"
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
