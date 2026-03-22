---
title: "Limpieza"
description: "Eliminar copias de seguridad huérfanas, snapshots obsoletos e imágenes de repositorio no utilizadas para recuperar espacio en disco."
category: "Guides"
order: 12
language: es
sourceHash: "39df2a50797597f6"
---

# Limpieza

La limpieza elimina recursos que ya no están referenciados por ningún archivo de configuración. Hay dos comandos de limpieza dirigidos a diferentes tipos de recursos:

- **`rdc storage prune`** -- elimina archivos de respaldo huérfanos del almacenamiento en la nube/externo
- **`rdc machine prune`** -- limpia artefactos del almacén de datos y (opcionalmente) imágenes de repositorios huérfanos en una máquina

## Storage Prune

Escanea un proveedor de almacenamiento y elimina respaldos cuyos GUIDs ya no aparecen en ningún archivo de configuración.

```bash
# Dry-run (default) — shows what would be deleted
rdc storage prune my-s3 -m server-1

# Actually delete orphaned backups
rdc storage prune my-s3 -m server-1

# Override grace period (default 7 days)
rdc storage prune my-s3 -m server-1 --grace-days 14
```

### Qué se verifica

1. Lista todos los GUIDs de respaldo en el almacenamiento indicado.
2. Escanea todos los archivos de configuración en disco (`~/.config/rediacc/*.json`).
3. Un respaldo está **huérfano** si su GUID no está referenciado en la sección de repositorios de ninguna configuración.
4. Los repositorios archivados recientemente dentro del período de gracia están **protegidos** incluso si fueron eliminados de la configuración activa.

## Machine Prune

Limpia recursos en la máquina en dos fases.

### Fase 1: Limpieza del almacén de datos (siempre se ejecuta)

Elimina directorios de montaje vacíos, archivos de bloqueo obsoletos y snapshots BTRFS obsoletos.

```bash
# Dry-run
rdc machine prune server-1 --dry-run

# Execute cleanup
rdc machine prune server-1
```

### Fase 2: Imágenes de repositorios huérfanos (opcional)

Con `--orphaned-repos`, la CLI también identifica imágenes de repositorios LUKS en la máquina que no aparecen en ningún archivo de configuración y las elimina.

```bash
# Dry-run (default behavior when is set)
rdc machine prune server-1

# Actually delete orphaned repos
rdc machine prune server-1

# Custom grace period
rdc machine prune server-1 --grace-days 30
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
rdc config set pruneGraceDays 14
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
- **Combine machine prune con deploy-backup.** Después de implementar programaciones de respaldo (`rdc machine deploy-backup`), agregue una limpieza periódica de la máquina para limpiar snapshots obsoletos y artefactos huérfanos del almacén de datos.
- **Audite antes de usar `--force`.** El flag `--force` omite el período de gracia. Úselo solo cuando esté seguro de que ninguna otra configuración referencia los repositorios en cuestión.
