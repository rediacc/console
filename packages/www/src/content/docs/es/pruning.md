---
title: "Limpieza"
description: "Eliminar copias de seguridad huérfanas, snapshots obsoletos, imágenes de repositorio y restos de configuración local para recuperar espacio en disco y mantener el estado coherente."
category: "Guides"
order: 12
language: es
sourceHash: "d2700c2ac4473962"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Limpieza

La limpieza barre el estado que ya no corresponde a un recurso vivo. Tres comandos cubren tres ámbitos diferentes:

| Comando | Qué limpia | Dónde reside la fuente de verdad |
|---|---|---|
| `rdc storage prune --name <storage> -m <machine>` | Respaldos huérfanos en almacenamiento en la nube | Configuración local del CLI (cruzada con la máquina ejecutora para seguridad de montaje) |
| `rdc machine prune --name <machine>` | Artefactos del datastore en la máquina (siempre); imágenes de repositorio huérfanas o desconocidas (opt-in) | Configuración local del CLI + el espejo `.interim/state` de la máquina |
| `rdc config prune` | Restos en la configuración local (caché de certificados, archivos expirados, referencias cruzadas colgantes) | Solo la configuración local del CLI |

Los tres son independientes. Puedes ejecutar cualquiera sin los otros. Comparten un modelo de seguridad común descrito en [Modelo de seguridad](#modelo-de-seguridad) más abajo.

La limpieza elimina el estado que dejaron atrás los recursos eliminados. Para recuperar el espacio ocupado por repositorios *activos* (bloques que sus sistemas de archivos han liberado pero el pool sigue reteniendo), use [`rdc repo trim`](/es/docs/repositories#recuperar-espacio-trim) en su lugar; los dos son complementarios.

## Verificación previa de seguridad de montaje

Tanto `storage prune` como `machine prune --prune-unknown` ejecutan una **verificación previa de seguridad de montaje** antes de eliminar cualquier cosa: consultan a la máquina ejecutora por los repositorios actualmente montados o en ejecución, los intersectan con los candidatos a eliminación y **se niegan a eliminar un candidato que sigue vivo en la máquina**. Eliminar el respaldo fuera de la máquina de un repositorio montado, o eliminar la imagen de un repositorio vivo, es un peligro real de pérdida de datos. La verificación previa hace imposible que ocurra por accidente.

Para anular esto (raro; solo cuando genuinamente sabes que el estado vivo es incorrecto), pasa `--force-delete-mounted`. Esta es una bandera independiente de `--force` (que controla el período de gracia del archivo) por lo que ambas vías de escape se mantienen distintas.

## Storage Prune

Escanea un proveedor de almacenamiento y elimina respaldos cuyos GUIDs ya no aparecen en ningún archivo de configuración local.

```bash
# Solo previsualizar — mostrar lo que se eliminaría
rdc storage prune --name my-s3 -m server-1 --dry-run

# Eliminar realmente los respaldos huérfanos (comportamiento por defecto)
rdc storage prune --name my-s3 -m server-1

# Anular el período de gracia (por defecto 7 días)
rdc storage prune --name my-s3 -m server-1 --grace-days 14

# Anular la verificación de seguridad de montaje (usar con cuidado)
rdc storage prune --name my-s3 -m server-1 --force-delete-mounted
```

`--machine` es obligatorio porque las llamadas de rclone se ejecutan en la máquina ejecutora, no en tu portátil. No se espera que los clientes tengan rclone instalado localmente. Las credenciales de almacenamiento siguen viniendo de tu configuración local; la máquina solo es el ejecutor de rclone.

### Qué verifica

1. Lista todos los GUIDs de respaldo en el almacenamiento indicado (en ambos subdirectorios `hot/` y `cold/`. Consulta [Respaldo y Restauración](/es/docs/backup-restore#respaldos-programados)).
2. Escanea cada archivo de configuración en disco (`~/.config/rediacc/*.json`).
3. Un respaldo está **huérfano** si su GUID no está referenciado por la sección de repositorios de ninguna configuración.
4. Los repositorios archivados recientemente dentro del período de gracia están **protegidos** incluso si fueron eliminados de la configuración activa.
5. Verificación previa de seguridad de montaje: los GUIDs actualmente montados en `--machine` se omiten y se reportan, nunca se eliminan.

### Rendimiento

Las eliminaciones se agrupan por subruta de almacenamiento: una llamada rclone por directorio `hot/` o `cold/` independientemente de cuántos GUIDs se estén eliminando. Una acumulación de 11 huérfanos colapsa de ~50 s de sobrecarga SSH a un único viaje de ida y vuelta por subruta.

## Machine Prune

Limpia recursos en la máquina en tres fases. La fase 1 siempre se ejecuta; las fases 2 y 3 son opt-in y pueden combinarse.

### Fase 1: Limpieza del datastore (siempre se ejecuta)

Elimina todo lo que queda cuando se borra un repositorio o se retira una convención de nomenclatura. Cada categoría se escanea de forma independiente. Ejecutar prune de forma repetida es seguro: es una única pasada idempotente, por lo que los huérfanos que la última ejecución pasó por alto se capturan en la siguiente.

| Categoría | Qué elimina |
|-----------|-------------|
| Directorios de montaje vacíos | Directorios `mounts/<guid>/` sin una imagen de repositorio que los respalde |
| Directorios inmóviles huérfanos | Directorios `immovable/<guid>/` sin una imagen de repositorio que los respalde |
| Archivos de bloqueo obsoletos | `repositories/.lock-<guid>` de repos eliminados |
| Snapshots de respaldo obsoletos | `.snapshot-*` y `.backup-*` dejados por ejecuciones de respaldo interrumpidas |
| Directorios sandbox de VS Code huérfanos | `.interim/sandbox/<name>` de repos que ya no están activos en la máquina |
| Cadenas iptables huérfanas | Cadenas `REDIACC_WILDCARD_<N>` y `DOCKER_ISOLATED_NET_<N>` de redes eliminadas |
| Entradas huérfanas en authorized_keys | Líneas `sandbox-gateway <repo> --guid <uuid>` cuyo `--guid` ya no corresponde a un directorio de montaje activo |

El escaneo de authorized_keys revisa `/home/*/.ssh/authorized_keys` y `/root/.ssh/authorized_keys`. Una entrada se conserva solo si su etiqueta `--guid` se corresponde con el GUID de un directorio de montaje vivo, por lo que los repos actualmente desplegados en la máquina siempre se preservan independientemente de si su nombre aparece en algún lugar del disco. Las entradas heredadas, escritas antes de que renet empezara a añadir la etiqueta `--guid`, no se pueden validar y siempre se reportan como huérfanas.

```bash
# Dry-run, muestra qué se eliminaría (sin cambios aplicados)
rdc machine prune --name server-1 --dry-run

# Ejecutar limpieza
rdc machine prune --name server-1
```

> **Limpieza en cascada.** Algunas categorías dependen de otras anteriores. Por ejemplo, eliminar directorios de montaje vacíos puede dejar expuestos sandbox huérfanos adicionales cuyo montaje de respaldo acaba de desaparecer. Ejecutar `rdc machine prune` una segunda vez captura la cascada y completa la limpieza. El último dry-run termina con `No orphaned resources found. Datastore is clean.` cuando ya no queda nada por hacer.

### Fase 2: `--orphaned-repos` (gruesa)

Con `--orphaned-repos`, el CLI también elimina imágenes de repositorios en la máquina que no aparecen en **ningún** archivo de configuración local.

```bash
rdc machine prune --name server-1 --orphaned-repos --dry-run
rdc machine prune --name server-1 --orphaned-repos
```

Esto es **grueso**. Elimina todo lo que no esté en tu configuración local, incluyendo bifurcaciones legítimas gestionadas por otras herramientas o por la copia del CLI de otro operador. Si el espejo `.interim/state` de renet identifica correctamente un repositorio como una bifurcación pero la configuración local nunca lo ha visto, esta fase aun así lo elimina. Prefiere la fase 3 (`--prune-unknown`) cuando quieras ser conservador.

### Fase 3: `--prune-unknown` (quirúrgico)

Con `--prune-unknown`, el CLI elimina solo repos que **ambas** señales no logran clasificar: no están en ninguna configuración local **y** no tienen entrada marcada como bifurcación en el espejo `.interim/state` de la máquina (consulta [Repositorios. Columna `Type`](/es/docs/repositories#columna-type-y-el-espejo-de-estado)).

```bash
rdc machine prune --name server-1 --prune-unknown --dry-run
rdc machine prune --name server-1 --prune-unknown
```

En la práctica `--prune-unknown` es lo que quieres para la limpieza rutinaria; `--orphaned-repos` solo es correcto cuando estás seguro de que tu configuración local es el inventario completo y autoritativo de cada repo en la máquina. Tanto los huérfanos heredados previos al espejo como los repos cuya entrada de configuración fue eliminada por error caen en el grupo "unknown". Son genuinamente inciertos, y la bandera quirúrgica le pide al operador que reconozca eso explícitamente.

La verificación previa de seguridad de montaje también se ejecuta en esta fase: un repo actualmente montado en `--machine` se reporta y se omite a menos que se pase `--force-delete-mounted`.

```bash
# Combinado: limpieza completa de la máquina con la ruta quirúrgica consciente de bifurcaciones
rdc machine prune --name server-1 --prune-unknown
```

## Config Prune

Barre los restos obsoletos **dentro del archivo de configuración local** en `~/.config/rediacc/<config>.json`. Puramente local. Sin SSH, sin llamadas a renet. Se limpian tres categorías:

1. **Entradas de la caché de certificados ACME** cuyo anclaje (GUID, nombre de repositorio o nombre de máquina) ya no está en la configuración activa. Los comodines de certificado nunca pueden enrutar a ninguna parte, por lo que son peso muerto.
2. **Repositorios archivados expirados** en `resources.deletedRepositories[]`. Entradas cuyo `deletedAt` es más antiguo que `defaults.pruneGraceDays` (por defecto 7 días). Las entradas dentro del período de gracia se reportan (con días restantes) y se conservan.
3. **Referencias cruzadas colgantes** entre categorías de configuración:
   - Entradas en `resources.machines.<m>.backupStrategies[]` que nombran una estrategia que ya no existe.
   - Entradas en `resources.backupStrategies.<s>.exclude[]` e `include[]` que nombran un repositorio que ya no existe.
   - Destinos de almacenamiento cuyo almacenamiento objetivo falta. Se marcan como advertencia, no se eliminan automáticamente (la eliminación automática cambiaría la semántica de la estrategia).

```bash
# Solo previsualizar
rdc config prune --dry-run

# Aplicar (comportamiento por defecto)
rdc config prune

# Restringir a una categoría
rdc config prune --certs-only
rdc config prune --archives-only
rdc config prune --refs-only

# Eliminar TODOS los repositorios archivados independientemente del período de gracia
rdc config prune --purge-archived

# Anular la ventana de gracia del archivo para esta invocación
rdc config prune --grace-days 30
```

### Lo que NO toca

- Recursos activos (máquinas, almacenamientos, repositorios, estrategias de respaldo, proveedores de la nube).
- Credenciales, el bloque de cuenta, el bloque de cifrado, defaults.
- `vaultContent` del almacenamiento (incluyendo el `access_token` expirado de OneDrive. El refresh_token sigue acuñando nuevos; podarlo forzaría re-autenticación).
- Entradas en `knownHosts` (la ruta de auto-actualización es `rdc config machine scan-keys`).
- El array de blob de certificado comprimido (`infra.acmeCertCache.<base>.data[]`) se reconstruye automáticamente desde la lista de certificados limpiada; no pierdes ninguna cadena que aún cubra un nombre conservado.

### Ejemplo trabajado

Salida de una ejecución real en una máquina con cuatro comodines de GUID huérfano y dos comodines de nombre de máquina obsoletos:

```text
Scanning local config for stale leftovers...
6 cert cache entry/entries would be removed:
  *.linode-1.rediacc.io  (unknown machine linode-1)
  *.marketing.linode-1.rediacc.io  (unknown machine linode-1)
  *.5b749533-99be-446c-9fe3-e6d0eec905a6.hostinger.rediacc.io  (unknown GUID 5b749533-…)
  *.5d09f3a6-9558-4df1-8a6e-b63140a6a7a6.hostinger.rediacc.io  (unknown GUID 5d09f3a6-…)
  *.e18d8c0f-367e-43c7-919e-2dbc59db4b5e.hostinger.rediacc.io  (unknown GUID e18d8c0f-…)
  *.9806c9b8-6bfb-4a87-9eaa-4b757ce1daca.hostinger.rediacc.io  (unknown GUID 9806c9b8-…)
Dry run: 6 change(s) would be applied. Re-run without --dry-run to commit.
```

Los nombres de certificado cuyo anclaje es una máquina, repositorio o GUID vivo se dejan en paz, al igual que los comodines de etiqueta única `<service>.<base>` o raíz `*.<base>`.

## Backfill del espejo de estado de migración

El espejo `.interim/state/<guid>/.rediacc.json` que alimenta `--prune-unknown` y la columna `Type` en `rdc repo list -m` se escribe:

- **En el momento de la bifurcación** (`rdc repo fork`). Inmediatamente, incluso antes de que la bifurcación se monte alguna vez.
- **En cada guardado de estado** (`rdc repo mount` y cualquier operación que actualice el estado del repositorio). Para repos que se crearon antes de que se desplegara el código del espejo.

Los repositorios que se crearon **antes de que existiera el espejo y no se han remontado desde la actualización** no tienen archivo de espejo. Aparecen como `unknown` en `rdc repo list -m` aunque algunos sean legítimamente bifurcaciones. Para corregir esto en huérfanos heredados, ejecuta el backfill de una sola vez en la máquina:

```bash
sudo /usr/local/bin/renet repository backfill-state-mirror \
    --datastore /mnt/rediacc \
    --mark-as-fork <guid1>,<guid2>,<guid3>
```

El backfill copia el estado vivo dentro del volumen al espejo para los repos actualmente montados y escribe un espejo sintético marcado como bifurcación para cualquier GUID que enumeres bajo `--mark-as-fork`. Tras el backfill, los respaldos programados dejan de cargar las bifurcaciones listadas (la canalización de carga comprueba el espejo en busca de `is_fork: true`).

## Modelo de seguridad

Todos los tres comandos adoptan un enfoque seguro por defecto en configuraciones múltiples.

### Reconocimiento de múltiples configuraciones

`storage prune` y `machine prune --orphaned-repos` escanean **todos** los archivos de configuración en `~/.config/rediacc/`, no solo el activo. Un repositorio referenciado por `production.json` no será eliminado aunque esté ausente en `staging.json`. Esto previene eliminaciones accidentales cuando las configuraciones están dirigidas a diferentes entornos.

### Período de gracia

Cuando un repositorio se elimina de una configuración con `--archive-config`, su entrada de credencial se mueve a `resources.deletedRepositories[]` con una marca de tiempo `deletedAt`. Los comandos de prune respetan un período de gracia (7 días por defecto) durante el cual los repositorios archivados recientemente están protegidos contra eliminación. Esto te da tiempo para restaurar un repositorio (`rdc config repository restore-archived --name <guid>`) si fue eliminado por accidente. Una vez que la gracia expira, `storage prune`, `machine prune` y `config prune` purgan automáticamente la entrada.

### Verificación previa de seguridad de montaje

Cubierto más arriba. `storage prune` y `machine prune --prune-unknown` se niegan a eliminar repos que están actualmente montados o en ejecución en la máquina ejecutora. Anula solo con `--force-delete-mounted`.

### Aplicar por defecto; `--dry-run` para previsualizar

Los tres comandos de prune por defecto **aplican** los cambios. Pasa `--dry-run` para previsualizar sin escribir. Esto coincide con el verbo: "prune" es destructivo por sí solo, y la bandera de dry-run es la opción explícita de no aplicar.

## Configuración

### `pruneGraceDays`

Establece un período de gracia predeterminado personalizado en tu archivo de configuración para no tener que pasar `--grace-days` cada vez:

```bash
# Establecer el período de gracia a 14 días en la configuración activa
rdc config field set --pointer /defaults/pruneGraceDays --new 14
```

La bandera CLI `--grace-days` anula este valor cuando se proporciona.

### Precedencia

1. Bandera `--grace-days <N>` (prioridad más alta)
2. `pruneGraceDays` en el archivo de configuración
3. Valor predeterminado incorporado: 7 días

## Mejores prácticas

- **Ejecuta dry-run primero en producción.** Siempre previsualiza antes de ejecutar una limpieza destructiva, especialmente en almacenamiento de producción.
- **Mantén múltiples configuraciones actualizadas.** La limpieza de almacenamiento y de máquina verifica todas las configuraciones en el directorio de configuración. Si un archivo de configuración está obsoleto o eliminado, sus repos pierden protección. Mantén los archivos de configuración precisos.
- **Prefiere `--prune-unknown` sobre `--orphaned-repos`.** La bandera quirúrgica respeta el espejo de renet; la bandera gruesa eliminará felizmente bifurcaciones que otras herramientas crearon.
- **Usa períodos de gracia generosos para producción.** El período de gracia predeterminado de 7 días es adecuado para la mayoría de los flujos de trabajo. Para entornos de producción con ventanas de mantenimiento poco frecuentes, considera 14 o 30 días.
- **Programa storage prune después de las ejecuciones de respaldo.** Combina `storage prune` con tu programación de respaldos para mantener los costos de almacenamiento bajo control sin intervención manual.
- **Combina machine prune con la programación de respaldos.** Después de desplegar programaciones de respaldo (`rdc machine backup schedule`), añade un machine prune periódico para limpiar snapshots obsoletos y artefactos huérfanos del datastore.
- **Ejecuta `config prune` periódicamente.** El abultamiento de la configuración local (especialmente la caché de certificados) se acumula silenciosamente; un `config prune --dry-run` trimestral es suficiente para detectarlo.
- **Audita antes de usar `--force` o `--force-delete-mounted`.** Ambas banderas omiten verificaciones de seguridad. Usa `--force` solo cuando estés seguro de que ninguna otra configuración referencia los repos en cuestión; usa `--force-delete-mounted` solo cuando estés seguro de que el estado vivo en la máquina es incorrecto.
