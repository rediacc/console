---
title: Respaldo y Restauración
description: >-
  Respalde repositorios cifrados en almacenamiento externo, restaure desde
  respaldos y programe respaldos automatizados.
category: Guides
order: 7
language: es
sourceHash: "f5222efa9505ab5e"
sourceCommit: "35b53352026ae87fb6800c7fed10b793223ca1da"
---

# Respaldo y Restauración

Rediacc puede respaldar repositorios cifrados en proveedores de almacenamiento externo y restaurarlos en la misma o en diferentes máquinas. Los respaldos están cifrados; se requiere la credencial LUKS del repositorio para restaurar.

## Configurar Almacenamiento

Antes de enviar respaldos, registre un proveedor de almacenamiento. Rediacc soporta cualquier almacenamiento compatible con rclone: S3, B2, Google Drive y muchos más.

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

Push siempre verifica que el repositorio de destino esté montado antes de escribir. Si no está montado, la operación se cancela.

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

Rediacc utiliza estrategias de respaldo con nombre. Cada estrategia define un cronograma, modo de respaldo, límite de ancho de banda opcional y filtros de archivo. Las máquinas referencian estrategias por nombre para determinar qué respaldos se ejecutan en ellas.

### Modos de Respaldo

| Modo | Comportamiento | Tiempo de inactividad |
|------|---------------|----------------------|
| `hot` | Snapshot de BTRFS tomado mientras los servicios están en ejecución (consistente ante fallos) | Ninguno |
| `cold` | Servicios detenidos, snapshot tomado, servicios reiniciados, snapshot cargado (consistente a nivel de aplicación) | Ventana de stop+start por repositorio, paralelizada entre repositorios. Véase "Estimación del tiempo de inactividad del respaldo en frío" abajo. |

Use `hot` para servicios que toleran snapshots consistentes ante fallos. Use `cold` cuando necesite consistencia garantizada y pueda aceptar un breve reinicio.

### Semantica del Respaldo en Frio

Un respaldo frio ejecuta tres fases por repositorio incluido: **detener -- snapshot -- iniciar**. Comprender los limites de las garantias ayuda a los operadores a detectar fallos parciales a tiempo.

**Lo que el respaldo frio garantiza:**

- Antes del snapshot, cada contenedor en ejecucion en cada repositorio incluido se detiene de forma controlada mediante el hook `down()` del Rediaccfile, y el Docker daemon por repositorio queda en reposo. El snapshot es por lo tanto consistente a nivel de aplicacion, no solo consistente ante fallos.
- El conjunto de IDs de contenedor que estaban en ejecucion antes del snapshot se persiste en un archivo sidecar en `/var/run/rediacc/cold-backup-<guid>.running.json`. Esta es la fuente de verdad de "que debe volver a estar activo cuando terminemos."
- Despues del snapshot, se invoca el hook `up()` del Rediaccfile del repositorio para restaurar el stack completo de compose.
- Un archivo sidecar de estado por ejecucion en `/var/run/rediacc/cold-backup-<guid>.status.json` registra la fase, resultado y cualquier error de cada intento.

**Lo que el respaldo frio NO garantiza:**

- `up()` es de mejor esfuerzo. Puede fallar por razones fuera del control del respaldo frio (una condicion `depends_on: service_healthy` aun esperando, un error de sintaxis en el archivo compose, un fallo de red transitorio al descargar una imagen). Cuando falla, el respaldo frio registra el error a nivel de error, escribe el sidecar de estado y pasa al siguiente repositorio.
- Cuando `up()` falla, se activa un **reinicio directo de respaldo**: se lee el sidecar de ejecucion y cada ID de contenedor registrado se reinicia mediante la API de Docker directamente (sin compose). Esto pone los servicios de vuelta en marcha incluso si el flujo de compose tiene un problema, aunque sin volver a ejecutar ningun hook de Rediaccfile.
- Si incluso el respaldo falla para algunos IDs de contenedor (por ejemplo, el propio Docker daemon esta caido), el sidecar se **deja en su lugar** para que el watchdog del router pueda seguir reintentando en cada ciclo.

**Recuperacion del Watchdog:** en cada ciclo, el watchdog comprueba si existe un sidecar de ejecucion. Cualquier ID de contenedor listado ahi que este actualmente detenido se reinicia, *independientemente de la `restart_policy` guardada del contenedor*. Esto significa que los servicios con `restart: on-failure` (que Docker NO reiniciaria despues de una detencion limpia) siguen volviendo despues de un respaldo frio. Una vez que todos los contenedores listados esten en ejecucion, el sidecar se elimina.

**Como los operadores detectan fallos:**

- `rdc machine query --name <machine> --containers` muestra el estado de ejecucion. Compare con el conjunto esperado.
- `/var/run/rediacc/cold-backup-<guid>.status.json` en la maquina. Inspeccione via `rdc term connect -m <machine> -r <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"`. `success: false` con un `startedAt` obsoleto significa que el ultimo respaldo no se completo correctamente.
- Los registros del respaldo de renet (`journalctl -u renet-*` o la invocacion directa `rdc machine deploy-backup`) emiten una linea de resumen final de la forma `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]`. Un `failed_repos` no vacio es el objetivo de grep.

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

Este comportamiento predeterminado es deliberado. Ejecutar dos respaldos en frío en paralelo contra el mismo datastore contendería por la ruta del snapshot BTRFS, el remote de rclone y los sidecars por repositorio en `/var/run/rediacc/cold-backup-<guid>.status.json`. Serializar detrás de una instancia de larga duración es el resultado seguro.

**Implicación de monitoreo.** Un respaldo colgado (por ejemplo, rclone atascado en un agujero negro de red) descarta silenciosamente cada disparo posterior del temporizador. El planificador no emite alarma. Observe `systemctl show <unit> -p ActiveEnterTimestamp`: si el servicio ha estado `activating` por más tiempo del esperado (por ejemplo, más de 48 h en un temporizador nocturno), investigue.

**Si necesita que cada disparo programado se ejecute**, cambie el temporizador de `OnCalendar=<cron>` a `OnUnitInactiveSec=<intervalo>`. Eso dispara N horas después de la finalización de la ejecución previa en lugar de en un cronograma de reloj de pared fijo, así las ejecuciones largas no causan descartes. Solo empujan la siguiente ejecución más tarde. La contrapartida es la deriva del cronograma: su nocturno de 03:00 se convierte en "24 h después del término del último."

### Definir una Estrategia

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
  --name nightly-cold \
  --destination my-storage \
  --cron "0 2 * * *" \
  --mode cold \
  --include "*.db" \
  --exclude "tmp/**" \
  --enable
```

| Opción | Descripción |
|--------|-------------|
| `--name <name>` | Nombre de la estrategia (usado para la vinculación de la máquina) |
| `--destination <storage>` | Proveedor de almacenamiento al que cargar |
| `--cron <expression>` | Expresión cron (p. ej. `"0 2 * * *"` para diario a las 2 AM) |
| `--mode <hot\|cold>` | Modo de respaldo |
| `--bwlimit <limit>` | Límite de ancho de banda para cargas (p. ej. `10M`) |
| `--include <pattern>` | Filtro de inclusion (repetible) |
| `--exclude <pattern>` | Filtro de exclusion (repetible) |
| `--enable` / `--disable` | Habilitar o deshabilitar la estrategia |

### Ver Estrategias

```bash
rdc config backup-strategy list
rdc config backup-strategy show --name nightly-cold
```

### Eliminar una Estrategia

```bash
rdc config backup-strategy remove --name nightly-cold
```

### Vincular Estrategias a una Maquina

En su configuración, vincule uno o más nombres de estrategia a una máquina:

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "nightly-cold"]
    }
  }
}
```

## Operaciones de Respaldo

### Desplegar Cronograma en la Máquina

Envíe las estrategias vinculadas a una máquina como temporizadores systemd:

```bash
rdc machine backup schedule -m server-1
rdc machine backup schedule -m server-1 --dry-run
```

`--dry-run` imprime los archivos de unidad systemd generados sin desplegarlos. Los tokens de rclone están enmascarados en la salida de dry-run.

### Ejecutar un Respaldo Ahora

Ejecute un respaldo inmediatamente sin esperar el temporizador. Funciona incluso si no se han desplegado temporizadores, usando `systemd-run` para ejecución ad-hoc:

```bash
rdc machine backup now -m server-1
rdc machine backup now -m server-1 --strategy nightly-cold
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
rdc machine backup cancel -m server-1 --strategy nightly-cold
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

La migración transfiere los datos del repositorio cifrado via rsync. El repositorio de origen permanece intacto hasta que lo elimine explícitamente.

## Explorar Almacenamiento

Explore el contenido de una ubicación de almacenamiento:

```bash
rdc storage browse --name my-storage
```

## Mejores Prácticas

- Programar respaldos frios diarios para snapshots consistentes a nivel de aplicacion de datos criticos
- Usar respaldos calientes para snapshots de alta frecuencia donde se requiere tiempo de actividad total
- Probar las restauraciones periódicamente para verificar la integridad de los respaldos
- Usar múltiples proveedores de almacenamiento para datos críticos (p. ej. S3 + B2)
- Mantener las credenciales seguras; los respaldos están cifrados pero se requiere la credencial LUKS para restaurar
