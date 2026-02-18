---
title: "Repositorios"
description: "Cree, gestione y opere repositorios cifrados con LUKS en maquinas remotas."
category: "Guides"
order: 4
language: es
---

# Repositorios

Un **repositorio** es una imagen de disco cifrada con LUKS en un servidor remoto. Cuando se monta, proporciona:
- Un sistema de archivos aislado para los datos de su aplicacion
- Un daemon Docker dedicado (separado del Docker del host)
- IPs de loopback unicas para cada servicio dentro de una subred /26

## Crear un Repositorio

```bash
rdc repo create my-app -m server-1 --size 10G
```

| Opcion | Requerido | Descripcion |
|--------|-----------|-------------|
| `-m, --machine <name>` | Si | Maquina destino donde se creara el repositorio. |
| `--size <size>` | Si | Tamano de la imagen de disco cifrada (por ejemplo, `5G`, `10G`, `50G`). |

La salida mostrara tres valores generados automaticamente:

- **GUID del Repositorio** -- Un UUID que identifica la imagen de disco cifrada en el servidor.
- **Credencial** -- Una frase de contrasena aleatoria utilizada para cifrar/descifrar el volumen LUKS.
- **ID de Red** -- Un numero entero (comenzando en 2816, incrementando en 64) que determina la subred IP para los servicios de este repositorio.

> **Almacene la credencial de forma segura.** Es la clave de cifrado de su repositorio. Si se pierde, los datos no se pueden recuperar. La credencial se almacena en su `config.json` local pero no se almacena en el servidor.

## Montar y Desmontar

Montar descifra y hace accesible el sistema de archivos del repositorio. Desmontar cierra el volumen cifrado.

```bash
rdc repo mount my-app -m server-1       # Descifrar y montar
rdc repo unmount my-app -m server-1     # Desmontar y re-cifrar
```

| Opcion | Descripcion |
|--------|-------------|
| `--checkpoint` | Crear un punto de control antes de montar/desmontar |

## Verificar Estado

```bash
rdc repo status my-app -m server-1
```

## Listar Repositorios

```bash
rdc repo list -m server-1
```

## Redimensionar

Establezca el repositorio a un tamano exacto o expanda una cantidad dada:

```bash
rdc repo resize my-app -m server-1 --size 20G    # Establecer tamano exacto
rdc repo expand my-app -m server-1 --size 5G      # Agregar 5G al tamano actual
```

> El repositorio debe estar desmontado antes de redimensionar.

## Bifurcar

Cree una copia de un repositorio existente en su estado actual:

```bash
rdc repo fork my-app -m server-1 --tag my-app-staging
```

Esto crea una nueva copia cifrada con su propio GUID e ID de red. La bifurcacion comparte la misma credencial LUKS que el repositorio padre.

## Validar

Verifique la integridad del sistema de archivos de un repositorio:

```bash
rdc repo validate my-app -m server-1
```

## Propiedad

Establezca la propiedad de archivos dentro de un repositorio al usuario universal (UID 7111). Esto es tipicamente necesario despues de subir archivos desde su estacion de trabajo, que llegan con su UID local.

```bash
rdc repo ownership my-app -m server-1
```

El comando detecta automaticamente los directorios de datos de contenedores Docker (montajes bind de escritura) y los excluye. Esto previene danos en contenedores que gestionan archivos con sus propios UIDs (por ejemplo, MariaDB=999, www-data=33).

| Opcion | Descripcion |
|--------|-------------|
| `--uid <uid>` | Establecer un UID personalizado en lugar de 7111 |
| `--force` | Omitir la deteccion de volumenes Docker y cambiar la propiedad de todo |

Para forzar la propiedad en todos los archivos, incluyendo datos de contenedores:

```bash
rdc repo ownership my-app -m server-1 --force
```

> **Advertencia:** Usar `--force` en contenedores en ejecucion puede romperlos. Detenga los servicios primero con `rdc repo down` si es necesario.

Consulte la [Guia de Migracion](/es/docs/migration) para un recorrido completo de cuando y como usar la propiedad durante la migracion de proyectos.

## Plantilla

Aplique una plantilla para inicializar un repositorio con archivos:

```bash
rdc repo template my-app -m server-1 --file ./my-template.tar.gz
```

## Eliminar

Destruya permanentemente un repositorio y todos los datos dentro de el:

```bash
rdc repo delete my-app -m server-1
```

> Esto destruye permanentemente la imagen de disco cifrada. Esta accion no se puede deshacer.
