---
title: "Respaldo y Restauración"
description: "Respalde repositorios cifrados en almacenamiento compatible con rclone, restaure en cualquier máquina y automatice con estrategias de respaldo nombradas y temporizadores systemd."
category: Guides
order: 7
language: es
sourceHash: "7ff112c2ec14c35f"
sourceCommit: "3fb35b9a33c7e8ec6753ecd56231f2018e8f4803"
---

# Respaldo y Restauración

Rediacc respalda repositorios cifrados en almacenamiento externo y los restaura en la misma máquina o en máquinas diferentes. Los respaldos están cifrados; se requiere la credencial LUKS del repositorio para restaurar.

## Configurar Almacenamiento

Antes de enviar respaldos, registre un proveedor de almacenamiento. Rediacc admite cualquier almacenamiento compatible con rclone: S3, B2, Google Drive y muchos más.

### Importar desde rclone

Si ya tiene un remote de rclone configurado:

```bash
rdc config storage import --file rclone.conf
```

Esto importa configuraciones de almacenamiento desde un archivo de configuración rclone a la configuración actual. Tipos compatibles: S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob y Swift.

### Ver Almacenamientos

```bash
rdc config storage list
```

## Enviar un Respaldo

Envíe un respaldo del repositorio al almacenamiento externo:

```bash
rdc repo push --name my-app -m server-1 --to my-storage
```

El respaldo queda en la carpeta `hot/` del almacenamiento cuando el repositorio está montado al momento del push, y en `cold/` cuando está desmontado. Es el mismo esquema que usan los respaldos programados, por lo que `rdc repo backup list` muestra todos los respaldos en una sola tabla.

| Opción | Descripción |
|--------|-------------|
| `--to <storage>` | Ubicación de almacenamiento destino |
| `--to-machine <machine>` | Máquina destino para respaldo de máquina a máquina |
| `--dest <filename>` | Nombre de archivo de destino personalizado |
| `--checkpoint` | Crear un checkpoint CRIU antes de enviar (para contenedores con etiqueta `rediacc.checkpoint=true`). El destino se restaura automáticamente con `repo up` |
| `--force` | Sobreescribir un respaldo existente |
| `--bwlimit <limit>` | Límite de ancho de banda para la transferencia rsync (p. ej. `10M`, `500K`) |
| `--tag <tag>` | Etiquetar el respaldo |
| `-w, --watch` | Observar el progreso de la operación |
| `--debug` | Habilitar salida detallada |
| `--skip-router-restart` | Omitir el reinicio del servidor de rutas después de la operación |

## Descargar / Restaurar un Respaldo

Descargue un respaldo del repositorio desde almacenamiento externo:

```bash
rdc repo pull --name my-app -m server-1 --from my-storage
```

Pull siempre verifica que el repositorio de destino esté montado antes de escribir. Si no está montado, la operación se cancela.

| Opción | Descripción |
|--------|-------------|
| `--from <storage>` | Ubicación de almacenamiento de origen |
| `--from-machine <machine>` | Máquina de origen para restauración de máquina a máquina |
| `--force` | Sobreescribir respaldo local existente |
| `--bwlimit <limit>` | Límite de ancho de banda para la transferencia rsync (p. ej. `10M`, `500K`) |
| `-w, --watch` | Observar el progreso de la operación |
| `--debug` | Habilitar salida detallada |
| `--skip-router-restart` | Omitir el reinicio del servidor de rutas después de la operación |

## Listar Respaldos

Ver los respaldos disponibles en una ubicación de almacenamiento:

```bash
rdc repo backup list --from my-storage -m server-1
```

La salida es una tabla unificada que combina ambas [carpetas de respaldos programados](#respaldos-programados) (`hot/` y `cold/`) para que vea cada respaldo en una sola vista:

| Columna | Significado |
|---|---|
| `Mode` | `hot` o `cold`. En qué carpeta de respaldos programados vive esta entrada |
| `Name` | Nombre del repositorio resuelto desde su configuración local (recurre al GUID para repositorios no presentes en la configuración) |
| `GUID` | El GUID del repositorio en disco |
| `Size` | Tamaño legible del archivo de respaldo |
| `Modified` | Marca de tiempo UTC del backend de almacenamiento |

Para profundizar en un solo modo, pase `--path`:

```bash
rdc repo backup list --from my-storage -m server-1 --path hot
rdc repo backup list --from my-storage -m server-1 --path cold
```

### Disposición de almacenamiento

Los respaldos programados se escriben en subcarpetas por modo dentro de la carpeta configurada del almacenamiento, así el mismo almacenamiento aloja limpiamente tanto el flujo horario como el semanal sin mezclarlos:

```text
<bucket>/<folder>/
├── hot/
│   ├── <guid-1>
│   ├── <guid-2>
│   └── ...
└── cold/
    ├── <guid-1>
    ├── <guid-3>
    └── ...
```

Un repositorio puede aparecer tanto en `hot/` como en `cold/` (el cronograma horario lo captura; el cronograma semanal lo vuelve a capturar). El listado combinado muestra ambas filas para que pueda ver qué flujos cubren qué repositorios.

## Sincronización Masiva

Envíe o descargue todos los repositorios a la vez:

### Enviar Todos al Almacenamiento

```bash
rdc repo push --to my-storage -m server-1
```

### Descargar Todos desde el Almacenamiento

```bash
rdc repo pull --from my-storage -m server-1
```

| Opción | Descripción |
|--------|-------------|
| `--to <storage>` | Almacenamiento destino (dirección de envío) |
| `--from <storage>` | Almacenamiento de origen (dirección de descarga) |
| `--repo <name>` | Sincronizar repositorios específicos (repetible) |
| `--override` | Sobreescribir respaldos existentes |
| `--debug` | Habilitar salida detallada |
| `--skip-router-restart` | Omitir el reinicio del servidor de rutas después de la operación |

## Respaldos Programados

Rediacc utiliza estrategias de respaldo nombradas. Cada estrategia define un cronograma, modo de respaldo, límite de ancho de banda opcional y filtros de archivo. Vincula nombres de estrategia a máquinas para controlar qué respaldos se ejecutan donde.

### Modos de Respaldo

| Modo | Comportamiento | Tiempo de inactividad |
|------|---------------|----------------------|
| `hot` | Snapshot de BTRFS tomado mientras los servicios están en ejecución (consistente ante fallos) | Ninguno |
| `cold` | Servicios detenidos, snapshot tomado, servicios reiniciados, snapshot cargado (consistente a nivel de aplicación) | Ventana de stop+start por repositorio, paralelizada entre repositorios. Véase "Estimación del tiempo de inactividad del respaldo en frío" abajo. |

Use `hot` para servicios que toleran snapshots consistentes ante fallos. Use `cold` cuando necesite consistencia garantizada y pueda aceptar un breve reinicio.

### Semántica del Respaldo en Frío

Un respaldo frío ejecuta tres fases por repositorio incluido: **detener - snapshot - iniciar**. Comprender los límites de las garantías ayuda a los operadores a detectar fallos parciales a tiempo.

**Lo que el respaldo frío garantiza:**

- Antes del snapshot, cada contenedor en ejecución en cada repositorio incluido se detiene de forma controlada mediante el hook `down()` del Rediaccfile, y el Docker daemon por repositorio queda en reposo. El snapshot es por lo tanto consistente a nivel de aplicación, no solo consistente ante fallos.
- El conjunto de IDs de contenedor que estaban en ejecución antes del snapshot se persiste en un archivo sidecar en `/var/run/rediacc/cold-backup-<guid>.running.json`. Esta es la fuente de verdad de "qué debe volver a estar activo cuando terminemos."
- Después del snapshot, se invoca el hook `up()` del Rediaccfile del repositorio para restaurar el stack completo de compose.
- Un archivo sidecar de estado por ejecución en `/var/run/rediacc/cold-backup-<guid>.status.json` registra la fase, resultado y cualquier error de cada intento.

**Lo que el respaldo frío NO garantiza:**

- `up()` es de mejor esfuerzo. Puede fallar por razones fuera del control del respaldo frío (una condición `depends_on: service_healthy` aún esperando, un error de sintaxis en el archivo compose, un fallo de red transitorio al descargar una imagen). Cuando falla, el respaldo frío registra el error a nivel de error, escribe el sidecar de estado y pasa al siguiente repositorio.
- Cuando `up()` falla, se activa un **reinicio directo de respaldo**: se lee el sidecar de ejecución y cada ID de contenedor registrado se reinicia mediante la API de Docker directamente (sin compose). Esto pone los servicios de vuelta en marcha incluso si el flujo de compose tiene un problema, aunque sin volver a ejecutar ningún hook de Rediaccfile.
- Si incluso el respaldo falla para algunos IDs de contenedor (por ejemplo, el propio Docker daemon está caído), el sidecar se **deja en su lugar** para que el watchdog del router pueda seguir reintentando en cada ciclo.

**Recuperación del Watchdog:** en cada ciclo, el watchdog comprueba si existe un sidecar de ejecución. Cualquier ID de contenedor listado ahí que esté actualmente detenido se reinicia, *independientemente de la `restart_policy` guardada del contenedor*. Esto significa que los servicios con `restart: on-failure` (que Docker NO reiniciaría después de una detención limpia) siguen volviendo después de un respaldo frío. Una vez que todos los contenedores listados estén en ejecución, el sidecar se elimina.

**Cómo los operadores detectan fallos:**

- `rdc machine query --name <machine> --containers` muestra el estado de ejecución. Compare con el conjunto esperado.
- `/var/run/rediacc/cold-backup-<guid>.status.json` en la máquina. Inspeccione vía `rdc term connect -m <machine> -r <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"`. `success: false` con un `startedAt` obsoleto significa que el último respaldo no se completó correctamente.
- Los registros del respaldo de renet (`journalctl -u renet-*` o la invocación directa `rdc machine backup schedule`) emiten una línea de resumen final de la forma `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]`. Un `failed_repos` no vacío es el objetivo de grep.

### Estimación del tiempo de inactividad del respaldo en frío

Cada repositorio solo está inactivo durante su propia ventana `down()` + `up()`. En un host en caliente estos son típicamente:

| Forma del repositorio | Stop+start típico |
|-----------------------|-------------------|
| Pequeño (1-2 contenedores, sin DB) | 5-15 s |
| Mediano (aplicación web + caché) | 20-45 s |
| Pesado (DB + colas + correo) | 60-120 s |

El paso de snapshot (`btrfs subvolume snapshot -r`) es O(1) independientemente del tamaño del repositorio: 0,1-1 s. Un repositorio no se mantiene detenido mientras se toman snapshots de otros repositorios. El cargador luego se ejecuta contra un snapshot de solo lectura mientras todos los repositorios ya están de vuelta.

**El tiempo total de reloj para toda la ejecución** está gobernado por cuántos repositorios reinician simultáneamente. Renet deriva este valor del host:

```text
concurrency = min(repoCount, max(2, NumCPU/2), 8)
```

Ejemplos:

| Host | Repos | Concurrencia | Reinicio en reloj |
|------|-------|--------------|-------------------|
| VM de 4 CPU | 5 repos, promedio 30 s cada uno | 2 | ~75 s |
| Servidor de 16 CPU | 10 repos, promedio 40 s cada uno | 8 | ~80 s |
| Nodo de flota de 64 CPU | 50 repos, promedio 40 s cada uno | 8 | ~4 min |

**Anulación vía variable de entorno:** establezca `REDIACC_COLD_BACKUP_CONCURRENCY=N` en el entorno del servicio de respaldo (normalmente mediante un drop-in de systemd) para fijar un valor específico. `=1` fuerza reinicios estrictamente seriales, útil al depurar un bucle de fallos en el hook `up()` de algún repositorio.

Si ejecuta un repositorio sensible a la latencia (aplicación web pública, correo), su tiempo de inactividad está limitado por su propio stop+start (típicamente 30-90 s), no por la duración total de la ejecución. Los repositorios se programan en slots de concurrencia en el orden en que fueron descubiertos; no hay cola de prioridad. Divida los repositorios pesados en sus propias estrategias con `--exclude` si necesita una planificación más fina.

### Respaldos de Larga Duración y Cronogramas Superpuestos

Un respaldo en frío que dura más que su propio intervalo de cronograma (por ejemplo, una primera siembra de un repositorio de 500 GB sobre un enlace modesto puede necesitar legítimamente más de 24 h, durante las cuales el temporizador nocturno dispara de nuevo) no encola ni lanza una segunda ejecución. La unidad systemd `Type=oneshot` es una sola instancia: cuando el temporizador dispara y el servicio ya está `activating`, systemd fusiona el inicio en el trabajo existente. No se lanza ningún proceso nuevo, no se encola ninguna ejecución para más tarde.

Concretamente, una ejecución que comienza el lunes a las 03:00 UTC y termina el jueves al mediodía:

| Día | Disparo de 03:00 UTC | Resultado |
|-----|---------------------|-----------|
| Lunes | Primer disparo | Comienza la ejecución |
| Martes | Segundo disparo | Descartado silenciosamente (la ejecución previa sigue activa) |
| Miércoles | Tercer disparo | Descartado silenciosamente (la ejecución previa sigue activa) |
| Jueves | La ejecución termina al mediodía | Sin recuperación; la siguiente ejecución es el viernes 03:00 UTC |

La directiva `Persistent=true` del temporizador **no** rescata estos disparos. `Persistent=true` repite disparos que se perdieron porque el temporizador mismo estaba inactivo (sistema apagado, temporizador deshabilitado). Los disparos descartados porque el servicio estaba ocupado se pierden.

Este comportamiento predeterminado es deliberado. Ejecutar dos respaldos en frío en paralelo contra el mismo datastore contendería por la ruta del snapshot BTRFS, el remote de rclone y los sidecars por repositorio en `/var/run/rediacc/cold-backup-<guid>.status.json`. Esperar detrás de una instancia en ejecución es el resultado seguro.

**Implicación de monitoreo.** Un respaldo colgado (por ejemplo, rclone atascado en un agujero negro de red) descarta silenciosamente cada disparo posterior del temporizador. El planificador no emite alarma. Observe `systemctl show <unit> -p ActiveEnterTimestamp`: si el servicio ha estado `activating` por más tiempo del esperado (por ejemplo, más de 48 h en un temporizador nocturno), investigue.

**Si necesita que cada disparo programado se ejecute**, cambie el temporizador de `OnCalendar=<cron>` a `OnUnitInactiveSec=<intervalo>`. Eso dispara N horas después de la finalización de la ejecución previa en lugar de en un cronograma de reloj de pared fijo, así las ejecuciones largas no causan descartes. Solo empujan la siguiente ejecución más tarde. La contrapartida es la deriva del cronograma: su nocturno de 03:00 se convierte en "24 h después de que la última terminó."

### Snapshots, Interrupciones y Espacio en el Pool

Cada push trabaja a partir de un snapshot momentáneo del datastore, por lo que los datos cargados son consistentes incluso mientras los repositorios siguen escribiendo. Mientras el respaldo se ejecuta, ese snapshot sigue referenciando todos los bloques que comparte con los repositorios activos: las eliminaciones y los [trims](/es/docs/repositories#recuperar-espacio-trim) liberan menos espacio en el pool hasta que el ciclo termina y el snapshot se elimina. El [informe de salud del almacenamiento](/es/docs/monitoring#salud-del-almacenamiento) muestra cuánto espacio están anclando actualmente los snapshots de respaldo.

Las interrupciones son seguras. Detener el servicio (o reiniciar la máquina) hace que el respaldo cancele su transferencia y elimine su snapshot antes de salir; la siguiente ejecución programada continúa donde se quedó, ya que los archivos sin cambios se omiten por checksum. Si el proceso se termina de forma tan abrupta que no puede limpiar (corte de energía), el snapshot huérfano es detectado y eliminado automáticamente por el mantenedor de almacenamiento en pocos minutos.

### Definir una Estrategia

El valor predeterminado canónico es una división en dos estrategias: un flujo hot horario rápido que captura todos los repositorios, y un flujo cold semanal más lento que toma snapshots consistentes a nivel de aplicación. Las dos estrategias escriben en subcarpetas distintas del almacenamiento (`hot/` y `cold/`) por lo que los flujos nunca se mezclan.

```bash
rdc config backup-strategy set \
  --name hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc config backup-strategy set \
  --name weekly-cold \
  --destination my-storage \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude very-large-repo \
  --enable
```

El filtro `--exclude` en la estrategia cold es la vía de escape recomendada para repositorios muy grandes que no caben en su ventana de mantenimiento semanal. La estrategia hot horaria los sigue cubriendo; cold simplemente los omite. Los nombres de repositorio en `--exclude` coinciden con el nombre de repositorio de la configuración local (sin `:tag`).

| Opción | Descripción |
|--------|-------------|
| `--name <name>` | Nombre de la estrategia (usado para la vinculación de la máquina) |
| `--destination <storage>` | Proveedor de almacenamiento al que cargar |
| `--cron <expression>` | Expresión cron (p. ej. `"0 2 * * *"` para diario a las 2 AM) |
| `--mode <hot\|cold>` | Modo de respaldo |
| `--bwlimit <limit>` | Límite de ancho de banda para cargas (p. ej. `10M`) |
| `--include <pattern>` | Filtro de inclusión (repetible) |
| `--exclude <pattern>` | Filtro de exclusión (repetible) |
| `--enable` / `--disable` | Habilitar o deshabilitar la estrategia |

### Ver Estrategias

```bash
rdc config backup-strategy list
rdc config backup-strategy show --name weekly-cold
```

### Eliminar una Estrategia

```bash
rdc config backup-strategy remove --name weekly-cold
```

### Vincular Estrategias a una Máquina

En su configuración, vincule uno o más nombres de estrategia a una máquina:

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "weekly-cold"]
    }
  }
}
```

> **La vinculación es solo de configuración local.** Definir una estrategia y vincularla a una máquina no afecta a la máquina. Ejecute `rdc machine backup schedule -m <machine>` (consulte [Desplegar Cronograma en la Máquina](#desplegar-cronograma-en-la-máquina)) para desplegar los temporizadores systemd, y vuelva a ejecutarlo tras cualquier cambio de estrategia o vinculación.

## Elegir entre Hot y Cold y Filtrado por Repositorio

### Hot vs cold de un vistazo

| | Hot | Cold |
|---|-----|------|
| **Consistencia** | Consistente ante fallos (snapshot BTRFS mientras los servicios están en ejecución) | Consistente a nivel de aplicación (detener - snapshot - iniciar) |
| **Tiempo de inactividad** | Ninguno | Ventana stop+start por repositorio (típicamente 5-120 s) |
| **Frecuencia adecuada** | Alta (p. ej. horaria) | Baja (p. ej. diaria o semanal) |
| **Uso típico** | Red de seguridad frecuente | Respaldo programado con consistencia garantizada |

**Hot** es la opción predeterminada correcta para ejecuciones de alta frecuencia. Los servicios siguen en funcionamiento mientras se toma el snapshot, por lo que la ventana de respaldo no interrumpe a los usuarios. El snapshot es consistente ante fallos: es equivalente a lo que obtendría tras un apagado incorrecto. Para la mayoría de las bases de datos modernas y colas de mensajes esto es aceptable.

**Cold** es apropiado cuando necesita un snapshot consistente a nivel de aplicación garantizado y puede aceptar un breve reinicio por repositorio. Los servicios se detienen antes del snapshot y se reinician antes de que comience la carga, de modo que una carga lenta o fallida nunca prolonga la ventana de tiempo de inactividad. Consulte [Semántica del Respaldo en Frío](#semántica-del-respaldo-en-frío) para el modelo de garantía completo.

### Filtrar repositorios por estrategia

Cada estrategia puede llevar filtros `--include` y `--exclude`. Los nombres de repositorios que coincidan con un patrón `--exclude` se omiten para esa estrategia; `--include` restringe la ejecución solo a esos nombres. Los filtros coinciden con el nombre de repositorio de la configuración local (sin `:tag`).

```bash
# Estrategia hot: respaldar todo cada hora
rdc config backup-strategy set \
  --name hourly-hot \
  --destination my-storage \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Estrategia cold: respaldar todo semanalmente, excluyendo el gran conjunto de datos derivado
rdc config backup-strategy set \
  --name weekly-cold \
  --destination my-storage \
  --cron "15 3 * * 0" \
  --mode cold \
  --exclude analytics-demo \
  --enable
```

### Cuándo excluir un repositorio de la estrategia hot de alta frecuencia

Excluya un repositorio de la ejecución de alta frecuencia cuando:

- El repositorio es grande y **totalmente regenerable** a partir de los datos de origen ya almacenados en el volumen, de modo que cada respaldo horario desperdicia ancho de banda significativo sin añadir valor de recuperación real.
- La ejecución del respaldo superaría su propio intervalo de cronograma a su velocidad de carga disponible.

**Ejemplo.** Un repositorio `analytics-demo` contiene aproximadamente 114 GB de tablas Postgres derivadas que pueden reconstruirse completamente a partir de archivos CSV brutos ya almacenados dentro del mismo volumen. Con un límite de carga de 6 MB/s, un solo respaldo hot de ese repositorio tarda más de 5 horas. Ejecutarlo cada hora significa que cada ejecución sigue en curso cuando se activa la siguiente, lo que provoca que cada ejecución posterior se descarte silenciosamente (consulte [Respaldos de Larga Duración y Cronogramas Superpuestos](#respaldos-de-larga-duración-y-cronogramas-superpuestos)). Excluirlo de `hourly-hot` y mantenerlo en `weekly-cold` significa que se respalda una vez por semana en lugar de nunca.

> **Si los datos son puramente regenerables**, considere si necesita respaldarlos en absoluto. Una alternativa es respaldar solo las entradas de origen bruto (los dumps CSV en este ejemplo) y omitir por completo la copia derivada. Un respaldo en frío semanal de las entradas de origen es mucho más pequeño y totalmente suficiente para la recuperación.

Los repositorios que no se excluyen de ninguna estrategia aparecen en las subcarpetas `hot/` y `cold/` del almacenamiento. La salida combinada de `rdc repo backup list` muestra ambas filas para verificar qué flujos cubren qué repositorios.

## Operaciones de Respaldo

### Desplegar Cronograma en la Máquina

Envíe las estrategias vinculadas a una máquina como temporizadores systemd:

```bash
rdc machine backup schedule -m server-1
rdc machine backup schedule -m server-1 --dry-run
```

El despliegue es un reconciliador de estado. Lee los archivos de unidad actuales y el estado de systemd en la máquina, los compara con lo que produciría la configuración (SHA-256 por archivo) y solo toca las unidades cuyo contenido realmente cambió. Volver a ejecutarlo sin cambios de configuración es un no-op: sin escrituras, sin `daemon-reload`, sin rotación de temporizadores.

`--dry-run` imprime el plan para cada estrategia (`created`, `updated (service, timer, env)`, `unchanged`, `removed`) sin tocar la máquina. Combínelo con `--debug` para imprimir también los cuerpos de las unidades generadas; los tokens de rclone se redactan.

Si actualmente se está ejecutando una copia de seguridad para una estrategia que está a punto de actualizar o eliminar, el despliegue falla rápido con una sugerencia de cancelarla o pasar `--force`. Con `--force`, la invocación en ejecución conserva su unidad en memoria y la nueva configuración se aplica en el próximo tick del temporizador, por lo que la copia de seguridad en ejecución nunca se termina.

`--reset-failed` es opt-in. Cuando se pasa, limpia el estado de fallo de systemd en los servicios modificados tras un despliegue exitoso. Desactivado por defecto para que las señales de fallo previas sigan visibles para las alertas.

### Ejecutar un Respaldo Ahora

Ejecute un respaldo inmediatamente sin esperar el temporizador. Funciona incluso si no se han desplegado temporizadores, usando `systemd-run` para ejecución ad-hoc:

```bash
rdc machine backup now -m server-1
rdc machine backup now -m server-1 --strategy weekly-cold
```

### Ver Estado del Respaldo

Muestre el estado actual de los temporizadores de respaldo y resultados de trabajos recientes:

```bash
rdc machine backup status -m server-1
rdc machine backup status -m server-1 --strategy hourly-hot
```

### Cancelar un Respaldo en Ejecución

```bash
rdc machine backup cancel -m server-1
rdc machine backup cancel -m server-1 --strategy weekly-cold
```

## Migración de Repositorios

Mueva un repositorio de una máquina a otra:

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Opción | Descripción |
|--------|-------------|
| `--name <repo>` | Repositorio a migrar |
| `--from <machine>` | Máquina de origen |
| `--to <machine>` | Máquina de destino |
| `--provision` | Provisionar el repositorio en el destino antes de transferir |
| `--checkpoint` | Crear un checkpoint CRIU antes de migrar |
| `--skip-dns` | Omitir la actualización de registros DNS después de la migración |
| `--bwlimit <limit>` | Límite de ancho de banda para la transferencia (p. ej. `50M`) |

La migración transfiere los datos del repositorio cifrado vía rsync. El repositorio de origen permanece intacto hasta que lo elimine explícitamente.

## Explorar Almacenamiento

Explore el contenido de una ubicación de almacenamiento:

```bash
rdc storage browse --name my-storage
```

## Mejores Prácticas

- Programar respaldos fríos diarios para snapshots consistentes a nivel de aplicación de datos críticos
- Usar respaldos calientes para snapshots de alta frecuencia donde se requiere tiempo de actividad total
- Probar las restauraciones periódicamente para verificar la integridad de los respaldos
- Usar múltiples proveedores de almacenamiento para datos críticos (p. ej. S3 + B2)
- Mantener las credenciales seguras; los respaldos están cifrados pero se requiere la credencial LUKS para restaurar
