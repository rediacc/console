---
title: "Herramientas"
description: "Sincronizacion de archivos, acceso por terminal, integracion con VS Code, actualizaciones y diagnosticos."
category: "Guides"
order: 8
language: es
---

# Herramientas

Rediacc incluye varias herramientas de productividad para trabajar con repositorios remotos. Estas herramientas se basan en la conexion SSH establecida por la configuracion de su contexto.

## Sincronizacion de Archivos (sync)

Transfiera archivos entre su estacion de trabajo y un repositorio remoto usando rsync sobre SSH.

### Subir Archivos

```bash
rdc sync upload my-app -m server-1 --local ./src --remote /app/src
```

### Descargar Archivos

```bash
rdc sync download my-app -m server-1 --remote /app/data --local ./data
```

### Opciones

| Opcion | Descripcion |
|--------|-------------|
| `-m, --machine <name>` | Maquina destino |
| `--local <path>` | Ruta del directorio local |
| `--remote <path>` | Ruta remota (relativa al punto de montaje del repositorio) |
| `--dry-run` | Vista previa de cambios sin transferir |
| `--delete` | Eliminar archivos en el destino que no existen en el origen |

La bandera `--dry-run` es util para obtener una vista previa de lo que se transferira antes de confirmar la sincronizacion.

## Terminal SSH (term)

Abra una sesion SSH interactiva a una maquina o directamente en la ruta de montaje de un repositorio.

### Conectar a una Maquina

```bash
rdc term connect server-1
```

### Conectar a un Repositorio

```bash
rdc term connect my-app -m server-1
```

Al conectarse a un repositorio, la sesion de terminal se inicia en el directorio de montaje del repositorio con el socket Docker del repositorio configurado.

## Integracion con VS Code (vscode)

Abra una sesion SSH remota en VS Code, preconfigurada con los ajustes SSH correctos y la extension Remote SSH.

### Conectar a un Repositorio

```bash
rdc vscode connect my-app -m server-1
```

Este comando:
1. Detecta su instalacion de VS Code
2. Configura la conexion SSH en `~/.ssh/config`
3. Persiste la clave SSH para la sesion
4. Abre VS Code con una conexion Remote SSH a la ruta del repositorio

### Listar Conexiones Configuradas

```bash
rdc vscode list
```

Muestra todas las conexiones SSH que se han configurado para VS Code.

### Limpiar Conexiones

```bash
rdc vscode clean
```

Elimina las configuraciones SSH de VS Code que ya no son necesarias.

> **Requisito previo:** Instale la extension [Remote - SSH](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-ssh) en VS Code.

## Actualizaciones de la CLI (update)

Mantenga la CLI `rdc` actualizada con las ultimas funciones y correcciones de errores.

### Buscar Actualizaciones

```bash
rdc update --check-only
```

### Aplicar Actualizacion

```bash
rdc update
```

Las actualizaciones se descargan y aplican en el lugar. La nueva version toma efecto en la siguiente ejecucion.

### Revertir

```bash
rdc update rollback
```

Revierte a la version instalada anteriormente. Solo disponible despues de que se haya aplicado una actualizacion.

### Estado de Auto-Actualizacion

```bash
rdc update status
```

Muestra la version actual, el canal de actualizacion y la configuracion de auto-actualizacion.

## Diagnosticos del Sistema (doctor)

Ejecute una verificacion de diagnostico completa de su entorno Rediacc.

```bash
rdc doctor
```

El comando doctor verifica:

| Categoria | Verificaciones |
|-----------|---------------|
| **Entorno** | Version de Node.js, version de la CLI, modo SEA |
| **Renet** | Presencia del binario, version, CRIU y rsync integrados |
| **Configuracion** | Contexto activo, modo, maquinas, clave SSH |
| **Autenticacion** | Estado de inicio de sesion |

Cada verificacion reporta **OK**, **Advertencia** o **Error** con una breve explicacion. Use esto como primer paso al resolver cualquier problema.
