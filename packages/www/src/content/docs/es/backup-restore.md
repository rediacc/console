---
title: Respaldo y Restauración
description: >-
  Respalde repositorios cifrados en almacenamiento externo, restaure desde
  respaldos y programe respaldos automatizados.
category: Guides
order: 7
language: es
sourceHash: cf186b18b0c50eba
---

# Respaldo y Restauración

Rediacc puede respaldar repositorios cifrados en proveedores de almacenamiento externo y restaurarlos en la misma o en diferentes máquinas. Los respaldos están cifrados -- se requiere la credencial LUKS del repositorio para restaurar.

## Configurar Almacenamiento

Antes de enviar respaldos, registre un proveedor de almacenamiento. Rediacc soporta cualquier almacenamiento compatible con rclone: S3, B2, Google Drive y muchos más.

### Importar desde rclone

Si ya tiene un remote de rclone configurado:

```bash
rdc config import-storage rclone.conf
```

Esto importa configuraciones de almacenamiento desde un archivo de configuración rclone a la configuración actual. Tipos compatibles: S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob y Swift.

### Ver Almacenamientos

```bash
rdc config storages
```

## Enviar un Respaldo

Envíe un respaldo del repositorio al almacenamiento externo:

```bash
rdc backup push my-app -m server-1 --to my-storage
```

| Opción | Descripción |
|--------|-------------|
| `--to <storage>` | Ubicación de almacenamiento destino |
| `--to-machine <machine>` | Máquina destino para respaldo de máquina a máquina |
| `--dest <filename>` | Nombre de archivo de destino personalizado |
| `--checkpoint` | Crear un punto de control antes de enviar |
| `--force` | Sobreescribir un respaldo existente |
| `--tag <tag>` | Etiquetar el respaldo |
| `-w, --watch` | Observar el progreso de la operación |
| `--debug` | Habilitar salida detallada |
| `--skip-router-restart` | Omitir el reinicio del servidor de rutas después de la operación |

## Descargar / Restaurar un Respaldo

Descargue un respaldo del repositorio desde almacenamiento externo:

```bash
rdc backup pull my-app -m server-1 --from my-storage
```

| Opción | Descripción |
|--------|-------------|
| `--from <storage>` | Ubicación de almacenamiento de origen |
| `--from-machine <machine>` | Máquina de origen para restauración de máquina a máquina |
| `--force` | Sobreescribir respaldo local existente |
| `-w, --watch` | Observar el progreso de la operación |
| `--debug` | Habilitar salida detallada |
| `--skip-router-restart` | Omitir el reinicio del servidor de rutas después de la operación |

## Listar Respaldos

Ver los respaldos disponibles en una ubicación de almacenamiento:

```bash
rdc backup list --from my-storage -m server-1
```

## Sincronización Masiva

Envíe o descargue todos los repositorios a la vez:

### Enviar Todos al Almacenamiento

```bash
rdc backup sync --to my-storage -m server-1
```

### Descargar Todos desde el Almacenamiento

```bash
rdc backup sync --from my-storage -m server-1
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

Automatice los respaldos con un cronograma cron que se ejecuta como un temporizador systemd en la máquina remota.

### Configurar Cronograma

```bash
rdc backup schedule set --destination my-storage --cron "0 2 * * *" --enable
```

| Opción | Descripción |
|--------|-------------|
| `--destination <storage>` | Destino de respaldo predeterminado |
| `--cron <expression>` | Expresión cron (por ejemplo, `"0 2 * * *"` para diario a las 2 AM) |
| `--enable` | Habilitar el cronograma |
| `--disable` | Deshabilitar el cronograma |

### Enviar Cronograma a la Máquina

Despliegue la configuración del cronograma en una máquina como un temporizador systemd:

```bash
rdc backup schedule push server-1
```

### Ver Cronograma

```bash
rdc backup schedule show
```

## Explorar Almacenamiento

Explore el contenido de una ubicación de almacenamiento:

```bash
rdc storage browse my-storage -m server-1
```

## Mejores Prácticas

- **Programe respaldos diarios** en al menos un proveedor de almacenamiento
- **Pruebe las restauraciones** periódicamente para verificar la integridad de los respaldos
- **Use múltiples proveedores de almacenamiento** para datos críticos (por ejemplo, S3 + B2)
- **Mantenga las credenciales seguras** -- los respaldos están cifrados pero se requiere la credencial LUKS para restaurar
