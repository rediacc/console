---
title: "Herramientas"
description: "Use el acceso de terminal SSH, la sincronización de archivos, la integración con VS Code y los comandos de actualización de CLI."
category: "Tutorials"
order: 5
language: es
sourceHash: "9391a34dfb244942"
---

# Cómo usar las herramientas de terminal, sincronización y VS Code con Rediacc

El CLI incluye herramientas de productividad para las operaciones diarias: acceso de terminal SSH, sincronización de archivos mediante rsync, desarrollo remoto con VS Code y actualizaciones del CLI. En este tutorial, ejecutará comandos remotos, sincronizará archivos con un repositorio, verificará la integración de VS Code y comprobará su versión del CLI.

## Requisitos previos

- El CLI `rdc` instalado con una configuración inicializada
- Una máquina aprovisionada con un repositorio en ejecución (ver [Tutorial: Ciclo de vida del repositorio](/es/docs/tutorial-repos))

## Grabación interactiva

![Tutorial: Tools](/assets/tutorials/tools-tutorial.cast)

### Paso 1: Conectar a una máquina

Ejecute comandos en línea en una máquina remota a través de SSH sin abrir una sesión interactiva.

```bash
rdc term server-1 -c "hostname"
rdc term server-1 -c "uptime"
```

El indicador `-c` ejecuta un solo comando y devuelve la salida. Omita `-c` para abrir una sesión SSH interactiva.

### Paso 2: Conectar a un repositorio

Para ejecutar comandos dentro del entorno Docker aislado de un repositorio:

```bash
rdc term server-1 my-app -c "docker ps"
```

Al conectarse a un repositorio, `DOCKER_HOST` se configura automáticamente al socket Docker aislado del repositorio. Cualquier comando Docker se ejecuta solo contra los contenedores de ese repositorio.

### Paso 3: Vista previa de sincronización de archivos (simulación)

Antes de transferir archivos, previsualice qué cambiaría.

```bash
rdc repo sync upload -m server-1 -r my-app --local ./src --dry-run
```

El indicador `--dry-run` muestra archivos nuevos, archivos modificados y el tamaño total de transferencia sin cargar nada realmente.

### Paso 4: Subir archivos

Transfiera archivos desde su máquina local al punto de montaje del repositorio remoto.

```bash
rdc repo sync upload -m server-1 -r my-app --local ./src
```

Los archivos se transfieren mediante rsync a través de SSH. Solo se envían los archivos modificados en las cargas posteriores.

### Paso 5: Verificar archivos subidos

Confirme que los archivos llegaron listando el directorio de montaje del repositorio.

```bash
rdc term server-1 my-app -c "ls -la"
```

### Paso 6: Verificación de integración VS Code

Para desarrollar de forma remota con VS Code, verifique que los componentes necesarios estén instalados.

```bash
rdc vscode check
```

Verifica su instalación de VS Code, la extensión Remote SSH y la configuración SSH. Siga la salida para resolver cualquier requisito faltante, luego conéctese con `rdc vscode <machine> [repo]`.

### Paso 7: Verificar actualizaciones del CLI

```bash
rdc update --check-only
```

Informa si hay una versión más nueva del CLI disponible. Para instalar la actualización, ejecute `rdc update` sin `--check-only`.

## Solución de problemas

**"rsync: command not found" durante la sincronización de archivos**
Instale rsync tanto en su máquina local como en el servidor remoto. En Debian/Ubuntu: `sudo apt install rsync`. En macOS: rsync está incluido por defecto.

**"Permission denied" durante la carga de sincronización**
Verifique que su usuario SSH tenga acceso de escritura al directorio de montaje del repositorio. Los montajes del repositorio pertenecen al usuario especificado durante el registro de la máquina.

**"VS Code Remote SSH extension not found"**
Instale la extensión desde el marketplace de VS Code: busque "Remote - SSH" de Microsoft. Después de instalar, reinicie VS Code y ejecute `rdc vscode check` nuevamente.

## Próximos pasos

Ha ejecutado comandos remotos, sincronizado archivos, verificado la integración de VS Code y comprobado actualizaciones del CLI. Para proteger sus datos:

- [Tools](/es/docs/tools) — referencia completa para comandos de terminal, sincronización, VS Code y actualización
- [Tutorial: Respaldo y redes](/es/docs/tutorial-backup) — programación de respaldos y configuración de red
- [Services](/es/docs/services) — referencia de Rediaccfile y redes de servicios
