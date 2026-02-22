---
title: Herramientas
description: >-
  Sincronización de archivos, acceso por terminal, integración con VS Code,
  actualizaciones y diagnósticos.
category: Guides
order: 8
language: es
sourceHash: 80ca3cd3e1a55d4b
---

# Herramientas

Rediacc incluye herramientas de productividad para trabajar con repositorios remotos: sincronización de archivos, terminal SSH, integración con VS Code y actualizaciones de la CLI.

## Sincronización de Archivos (sync)

Transfiera archivos entre su estación de trabajo y un repositorio remoto usando rsync sobre SSH.

### Subir Archivos

```bash
rdc sync upload -m server-1 -r my-app --local ./src --remote /app/src
```

### Descargar Archivos

```bash
rdc sync download -m server-1 -r my-app --remote /app/data --local ./data
```

### Verificar Estado de Sincronización

```bash
rdc sync status -m server-1 -r my-app
```

### Opciones

| Opción | Descripción |
|--------|-------------|
| `-m, --machine <name>` | Máquina destino |
| `-r, --repository <name>` | Repositorio destino |
| `--local <path>` | Ruta del directorio local |
| `--remote <path>` | Ruta remota (relativa al montaje del repositorio) |
| `--dry-run` | Previsualizar cambios sin transferir |
| `--mirror` | Duplicar origen en destino (eliminar archivos extra) |
| `--verify` | Verificar checksums después de la transferencia |
| `--confirm` | Confirmación interactiva con vista detallada |
| `--exclude <patterns...>` | Excluir patrones de archivos |
| `--skip-router-restart` | Omitir el reinicio del servidor de rutas después de la operación |

## Terminal SSH (term)

Abra una sesión SSH interactiva a una máquina o al entorno de un repositorio.

### Sintaxis Abreviada

La forma más rápida de conectarse:

```bash
rdc term server-1                    # Conectarse a una máquina
rdc term server-1 my-app             # Conectarse a un repositorio
```

### Ejecutar un Comando

Ejecute un comando sin abrir una sesión interactiva:

```bash
rdc term server-1 -c "uptime"
rdc term server-1 my-app -c "docker ps"
```

Al conectarse a un repositorio, `DOCKER_HOST` se configura automáticamente al socket Docker aislado del repositorio, por lo que `docker ps` muestra solo los contenedores de ese repositorio.

### Subcomando Connect

El subcomando `connect` proporciona la misma funcionalidad con flags explícitos:

```bash
rdc term connect -m server-1
rdc term connect -m server-1 -r my-app
```

### Acciones de Contenedor

Interactúe directamente con un contenedor en ejecución:

```bash
# Abrir una shell dentro de un contenedor
rdc term server-1 my-app --container <container-id>

# Ver logs del contenedor
rdc term server-1 my-app --container <container-id> --container-action logs

# Seguir logs en tiempo real
rdc term server-1 my-app --container <container-id> --container-action logs --follow

# Ver estadísticas del contenedor
rdc term server-1 my-app --container <container-id> --container-action stats

# Ejecutar un comando en un contenedor
rdc term server-1 my-app --container <container-id> --container-action exec -c "ls -la"
```

| Opción | Descripción |
|--------|-------------|
| `--container <id>` | ID del contenedor Docker destino |
| `--container-action <action>` | Acción: `terminal` (predeterminado), `logs`, `stats`, `exec` |
| `--log-lines <n>` | Número de líneas de log a mostrar (predeterminado: 50) |
| `--follow` | Seguir logs continuamente |
| `--external` | Usar terminal externo en lugar de SSH en línea |

## Integración con VS Code (vscode)

Abra una sesión SSH remota en VS Code, preconfigurada con los ajustes SSH correctos.

### Conectarse a un Repositorio

```bash
rdc vscode connect my-app -m server-1
```

Este comando:
1. Detecta su instalación de VS Code
2. Configura la conexión SSH en `~/.ssh/config`
3. Persiste la clave SSH para la sesión
4. Abre VS Code con una conexión Remote SSH a la ruta del repositorio

### Listar Conexiones Configuradas

```bash
rdc vscode list
```

### Limpiar Conexiones

```bash
rdc vscode clean
```

Elimina configuraciones SSH de VS Code que ya no son necesarias.

### Verificar Configuración

```bash
rdc vscode check
```

Verifica la instalación de VS Code, la extensión Remote SSH y las conexiones activas.

> **Prerrequisito:** Instale la extensión [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) en VS Code.

## Actualizaciones de la CLI (update)

Mantenga la CLI `rdc` actualizada.

### Buscar Actualizaciones

```bash
rdc update --check-only
```

### Aplicar Actualización

```bash
rdc update
```

Las actualizaciones se descargan y aplican en el lugar. La CLI selecciona automáticamente el binario correcto para su plataforma (Linux, macOS o Windows). La nueva versión entra en efecto en la siguiente ejecución.

### Revertir

```bash
rdc update rollback
```

Revierte a la versión previamente instalada. Solo disponible después de que se haya aplicado una actualización.

### Estado de Actualización

```bash
rdc update status
```

Muestra la versión actual, el canal de actualización y la configuración de actualización automática.
