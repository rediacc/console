---
title: "Limpieza"
description: "Eliminar copias de seguridad huérfanas, snapshots obsoletos e imágenes de repositorio no utilizadas para recuperar espacio en disco."
category: "Guides"
order: 12
language: es
sourceHash: "f355a0921afb72e9"
sourceCommit: "7874d5e2f0ca1262eb80ee7de79f20320d0ae2d7"
---

# Limpieza

La limpieza elimina recursos que ya no están referenciados por ningún archivo de configuración. Hay dos comandos de limpieza dirigidos a diferentes tipos de recursos:

- **`rdc storage prune`** -- elimina archivos de respaldo huérfanos del almacenamiento en la nube/externo
- **`rdc machine prune`** -- limpia artefactos del almacén de datos y (opcionalmente) imágenes de repositorios huérfanos en una máquina

## Storage Prune

Escanea un proveedor de almacenamiento y elimina respaldos cuyos GUIDs ya no aparecen en ningún archivo de configuración.

```bash
# Dry-run (default), shows what would be deleted
rdc storage prune --name my-s3 -m server-1

# Actually delete orphaned backups
rdc storage prune --name my-s3 -m server-1

# Override grace period (default 7 days)
rdc storage prune --name my-s3 -m server-1 --grace-days 14
```

### Qué se verifica

1. Lista todos los GUIDs de respaldo en el almacenamiento indicado.
2. Escanea todos los archivos de configuración en disco (`~/.config/rediacc/*.json`).
3. Un respaldo está **huérfano** si su GUID no está referenciado en la sección de repositorios de ninguna configuración.
4. Los repositorios archivados recientemente dentro del período de gracia están **protegidos** incluso si fueron eliminados de la configuración activa.

## Machine Prune

Limpia recursos en la máquina en dos fases.

### Fase 1: Limpieza del almacén de datos (siempre se ejecuta)

Elimina todo tipo de recurso que pueda quedar olvidado cuando se borra un repositorio o cuando una refactorización a nivel de máquina retira una convención de nomenclatura. Cada categoría se escanea de forma independiente y la limpieza es una única pasada idempotente, por lo que ejecutar prune de forma repetida es seguro y converge hacia un almacén de datos limpio.

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
# Dry-run, shows what would be removed (no changes applied)
rdc machine prune --name server-1 --dry-run

# Execute cleanup
rdc machine prune --name server-1
```

> **Limpieza en cascada.** Algunas categorías dependen de otras anteriores. Por ejemplo, eliminar directorios de montaje vacíos puede dejar expuestos sandbox huérfanos adicionales cuyo montaje de respaldo acaba de desaparecer. Ejecutar `rdc machine prune` una segunda vez captura la cascada y completa la limpieza. El último dry-run termina con `No orphaned resources found. Datastore is clean.` cuando ya no queda nada por hacer.

### Fase 2: Imágenes de repositorios huérfanos (opcional)

Con `--orphaned-repos`, la CLI también identifica imágenes de repositorios LUKS en la máquina que no aparecen en ningún archivo de configuración y las elimina.

```bash
# Dry-run (default behavior when is set)
rdc machine prune --name server-1

# Actually delete orphaned repos
rdc machine prune --name server-1

# Custom grace period
rdc machine prune --name server-1 --grace-days 30
```

## Modelo de seguridad

La limpieza está diseñada para ser segura por defecto en configuraciones múltiples.

### Reconocimiento de múltiples configuraciones

Ambos comandos de limpieza escanean **todos** los archivos de configuración en `~/.config/rediacc/`, no solo el activo. Un repositorio referenciado por `production.json` no será eliminado aunque esté ausente en `staging.json`. Esto previene eliminaciones accidentales cuando las configuraciones están dirigidas a diferentes entornos.

### Período de gracia

Cuando un repositorio se elimina de una configuración, puede archivarse con una marca de tiempo. Los comandos de limpieza respetan un período de gracia (7 días por defecto) durante el cual los repositorios archivados recientemente están protegidos contra eliminación. Esto le da tiempo para restaurar un repositorio si fue eliminado accidentalmente.

### Dry-run por defecto

`storage prune` y `machine prune` usan el modo dry-run por defecto. Muestran lo que se eliminaría sin realizar cambios. Pase `--no-dry-run` o `--force` para ejecutar la eliminación real.

## Configuración

### `pruneGraceDays`

Establezca un período de gracia predeterminado personalizado en su archivo de configuración para no tener que pasar `--grace-days` cada vez:

```bash
# Set grace period to 14 days in the active config
rdc config set --key pruneGraceDays --value 14
```

El flag CLI `--grace-days` anula este valor cuando se proporciona.

### Precedencia

1. Flag `--grace-days <N>` (prioridad más alta)
2. `pruneGraceDays` en el archivo de configuración
3. Valor predeterminado incorporado: 7 días

## Mejores prácticas

- **Ejecute dry-run primero.** Siempre previsualice antes de ejecutar una limpieza destructiva, especialmente en almacenamiento de producción.
- **Mantenga múltiples configuraciones actualizadas.** La limpieza verifica todas las configuraciones en el directorio de configuración. Si un archivo de configuración está obsoleto o eliminado, sus repositorios pierden protección. Mantenga los archivos de configuración precisos.
- **Use períodos de gracia generosos para producción.** El período de gracia predeterminado de 7 días es adecuado para la mayoría de los flujos de trabajo. Para entornos de producción con ventanas de mantenimiento poco frecuentes, considere 14 o 30 días.
- **Programe storage prune después de las ejecuciones de respaldo.** Combine `storage prune` con su programación de respaldos para mantener los costos de almacenamiento bajo control sin intervención manual.
- **Combine machine prune con backup schedule.** Después de implementar programaciones de respaldo (`rdc machine backup schedule`), agregue una limpieza periódica de la máquina para limpiar snapshots obsoletos y artefactos huérfanos del almacén de datos.
- **Audite antes de usar `--force`.** El flag `--force` omite el período de gracia. Úselo solo cuando esté seguro de que ninguna otra configuración referencia los repositorios en cuestión.
