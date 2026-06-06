---
title: Herramientas
description: >-
  Sincronización de archivos, acceso por terminal, integración con VS Code y
  actualizaciones de la CLI.
category: Guides
order: 9
language: es
sourceHash: "4b3aebff5e82416f"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Herramientas

Rediacc ofrece cuatro herramientas para el trabajo diario en sus máquinas y repositorios: sincronización de archivos sobre SSH, un terminal SSH, integración con VS Code y actualizaciones automáticas de la CLI. Los cuatro funcionan sobre SSH. No se requiere agente ni demonio en el lado remoto. Si necesita una interfaz gráfica para cualquiera de esto, está buscando en la página equivocada.

## Sincronización de Archivos (sync)

Transfiera archivos entre su estación de trabajo y un repositorio remoto usando rsync sobre SSH.

### Subir Archivos

`--local` acepta una o más rutas. Cada ruta puede ser un archivo o un directorio. Los archivos se colocan en `<remote>/<basename>`; el contenido del directorio se fusiona en `<remote>/`. Para un único archivo, prefiera `--remote-file` para proporcionar la ruta de destino explícitamente.

```bash
# Directorio (contenido fusionado en remoto)
rdc repo sync upload -m server-1 -r my-app --local ./src --remote /app/src

# Archivo único colocado en un directorio remoto (nombre base preservado)
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote /app/conf

# Archivo único, ruta de destino explícita
rdc repo sync upload -m server-1 -r my-app --local ./config.yml --remote-file /app/conf/config.yml

# Múltiples fuentes en una sola llamada
rdc repo sync upload -m server-1 -r my-app --local a.yml b.yml ./assets --remote /app
```

`--remote` y `--remote-file` se excluyen mutuamente. `--remote-file` requiere exactamente una ruta `--local` que apunte a un archivo.

`--mirror` no puede combinarse con una fuente de archivo; eliminaría archivos hermanos en el directorio remoto.

### Descargar Archivos

Use `--remote` para un directorio (el predeterminado) o `--remote-file` para un único archivo. Los dos flags se excluyen mutuamente.

```bash
# Directorio
rdc repo sync download -m server-1 -r my-app --remote /app/data --local ./data

# Archivo único: --local debe ser un directorio existente
rdc repo sync download -m server-1 -r my-app --remote-file /app/conf/config.yml --local ./local-conf
```

### Verificar Estado de Sincronización

```bash
rdc repo sync status -m server-1 -r my-app
```

### Opciones

| Opción | Descripción |
|--------|-------------|
| `-m, --machine <name>` | Máquina destino |
| `-r, --repository <name>` | Repositorio destino |
| `--local <paths...>` | Una o más rutas locales de archivo o directorio (subida) o directorio local de destino (descarga) |
| `--remote <path>` | Directorio remoto (relativo al montaje del repositorio) |
| `--remote-file <path>` | Ruta de archivo remoto para descargas o subidas de archivo único (alternativa a `--remote`) |
| `--dry-run` | Previsualizar cambios sin transferir |
| `--mirror` | Duplicar origen en destino, eliminar archivos extra (solo fuentes de directorio) |
| `--verify` | Verificar checksums después de la transferencia |
| `--confirm` | Confirmación interactiva con vista detallada |
| `--exclude <patterns...>` | Excluir patrones de archivos |
| `--skip-router-restart` | Omitir el reinicio del servidor de rutas después de la operación |

## Terminal SSH (term)

Abra una sesión SSH interactiva a una máquina o al entorno de un repositorio.

### Sintaxis Abreviada

La forma más rápida de conectarse:

```bash
rdc term connect -m server-1                    # Conectarse a una máquina
rdc term connect -m server-1 -r my-app             # Conectarse a un repositorio
```

### Ejecutar un Comando

Ejecute un comando sin abrir una sesión interactiva:

```bash
rdc term connect -m server-1 -c "uptime"
rdc term connect -m server-1 -r my-app -c "docker ps"
```

Al conectarse a un repositorio, `DOCKER_HOST` se configura automáticamente al socket Docker aislado del repositorio, por lo que `docker ps` muestra solo los contenedores de ese repositorio.

### Subcomando Connect

O use el subcomando `connect` para el mismo resultado, con flags explícitos:

```bash
rdc term connect -m server-1
rdc term connect -m server-1 -r my-app
```

### Acciones de Contenedor

Interactúe directamente con un contenedor en ejecución:

```bash
# Abrir una shell dentro de un contenedor
rdc term connect -m server-1 -r my-app --container <container-id>

# Ver logs del contenedor
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs

# Seguir logs en tiempo real
rdc term connect -m server-1 -r my-app --container <container-id> --container-action logs --follow

# Ver estadísticas del contenedor
rdc term connect -m server-1 -r my-app --container <container-id> --container-action stats

# Ejecutar un comando en un contenedor
rdc term connect -m server-1 -r my-app --container <container-id> --container-action exec -c "ls -la"
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
rdc vscode connect -r my-app -m server-1
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
rdc vscode cleanup
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
rdc update --rollback
```

Revierte a la versión previamente instalada. Solo disponible después de que se haya aplicado una actualización.

### Estado de Actualización

```bash
rdc update --status
```

Muestra la versión actual, el canal de actualización y la configuración de actualización automática.

#### Canales de Lanzamiento

```bash
rdc update --channel edge      # Actualizaciones de producción implementadas continuamente
rdc update --channel stable    # Promovido desde edge después de 7 días de prueba (predeterminado)
rdc update --status            # Mostrar canal actual e información de versión
```
