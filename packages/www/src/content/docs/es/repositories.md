---
title: Repositorios
description: 'Cree, gestione y opere repositorios cifrados con LUKS en máquinas remotas.'
category: Guides
order: 4
language: es
sourceHash: 04fe287348176b64
---

# Repositorios

Un **repositorio** es una imagen de disco cifrada con LUKS en un servidor remoto. Cuando se monta, proporciona:
- Un sistema de archivos aislado para los datos de su aplicación
- Un daemon Docker dedicado (separado del Docker del host)
- IPs de loopback únicas para cada servicio dentro de una subred /26

## Crear un Repositorio

```bash
rdc repo create my-app -m server-1 --size 10G
```

| Opción | Requerido | Descripción |
|--------|-----------|-------------|
| `-m, --machine <name>` | Sí | Máquina destino donde se creará el repositorio. |
| `--size <size>` | Sí | Tamaño de la imagen de disco cifrada (por ejemplo, `5G`, `10G`, `50G`). |
| `--skip-router-restart` | No | Omitir el reinicio del servidor de rutas después de la operación |

La salida mostrará tres valores generados automáticamente:

- **GUID del Repositorio** -- Un UUID que identifica la imagen de disco cifrada en el servidor.
- **Credencial** -- Una frase de contraseña aleatoria utilizada para cifrar/descifrar el volumen LUKS.
- **ID de Red** -- Un número entero (comenzando en 2816, incrementando en 64) que determina la subred IP para los servicios de este repositorio.

> **Almacene la credencial de forma segura.** Es la clave de cifrado de su repositorio. Si se pierde, los datos no se pueden recuperar. La credencial se almacena en su `config.json` local pero no se almacena en el servidor.

## Montar y Desmontar

Montar descifra y hace accesible el sistema de archivos del repositorio. Desmontar cierra el volumen cifrado.

```bash
rdc repo mount my-app -m server-1       # Descifrar y montar
rdc repo unmount my-app -m server-1     # Desmontar y re-cifrar
```

| Opción | Descripción |
|--------|-------------|
| `--checkpoint` | Crear un punto de control antes de montar/desmontar |
| `--skip-router-restart` | Omitir el reinicio del servidor de rutas después de la operación |

## Verificar Estado

```bash
rdc repo status my-app -m server-1
```

## Listar Repositorios

```bash
rdc repo list -m server-1
```

## Redimensionar

Establezca el repositorio a un tamaño exacto o expanda una cantidad dada:

```bash
rdc repo resize my-app -m server-1 --size 20G    # Establecer tamaño exacto
rdc repo expand my-app -m server-1 --size 5G      # Agregar 5G al tamaño actual
```

> El repositorio debe estar desmontado antes de redimensionar.

## Bifurcar

Cree una copia de un repositorio existente en su estado actual:

```bash
rdc repo fork my-app -m server-1 --tag my-app-staging
```

Esto crea una nueva copia cifrada con su propio GUID e ID de red. La bifurcación comparte la misma credencial LUKS que el repositorio padre.

## Validar

Verifique la integridad del sistema de archivos de un repositorio:

```bash
rdc repo validate my-app -m server-1
```

## Propiedad

Establezca la propiedad de archivos dentro de un repositorio al usuario universal (UID 7111). Esto es típicamente necesario después de subir archivos desde su estación de trabajo, que llegan con su UID local.

```bash
rdc repo ownership my-app -m server-1
```

El comando detecta automáticamente los directorios de datos de contenedores Docker (montajes bind de escritura) y los excluye. Esto previene daños en contenedores que gestionan archivos con sus propios UIDs (por ejemplo, MariaDB=999, www-data=33).

| Opción | Descripción |
|--------|-------------|
| `--uid <uid>` | Establecer un UID personalizado en lugar de 7111 |
| `--force` | Omitir la detección de volúmenes Docker y cambiar la propiedad de todo |
| `--skip-router-restart` | Omitir el reinicio del servidor de rutas después de la operación |

Para forzar la propiedad en todos los archivos, incluyendo datos de contenedores:

```bash
rdc repo ownership my-app -m server-1 --force
```

> **Advertencia:** Usar `--force` en contenedores en ejecución puede romperlos. Detenga los servicios primero con `rdc repo down` si es necesario.

Consulte la [Guía de Migración](/es/docs/migration) para un recorrido completo de cuándo y cómo usar la propiedad durante la migración de proyectos.

## Plantilla

Aplique una plantilla para inicializar un repositorio con archivos:

```bash
rdc repo template my-app -m server-1 --file ./my-template.tar.gz
```

## Eliminar

Destruya permanentemente un repositorio y todos los datos dentro de él:

```bash
rdc repo delete my-app -m server-1
```

> Esto destruye permanentemente la imagen de disco cifrada. Esta acción no se puede deshacer.
