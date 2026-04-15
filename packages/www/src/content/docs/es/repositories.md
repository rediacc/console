---
title: Repositorios
description: 'Cree, gestione y opere repositorios cifrados con LUKS en máquinas remotas.'
category: Guides
order: 4
language: es
sourceHash: "83f2c9fa5ae53864"
sourceCommit: "5c97ef070ea0c474b03651ceea03433b3f48abcd"
---

# Repositorios

Un **repositorio** es una imagen de disco cifrada con LUKS en un servidor remoto. Cuando se monta, proporciona:
- Un sistema de archivos aislado para los datos de su aplicación
- Un daemon Docker dedicado (separado del Docker del host)
- IPs de loopback únicas para cada servicio dentro de una subred /26

## Crear un Repositorio

```bash
rdc repo create --name my-app -m server-1 --size 10G
```

| Opción | Requerido | Descripción |
|--------|-----------|-------------|
| `-m, --machine <name>` | Sí | Máquina destino donde se creará el repositorio |
| `--size <size>` | Sí | Tamaño de la imagen de disco cifrada (por ejemplo, `5G`, `10G`, `50G`) |
| `--skip-router-restart` | No | Omitir el reinicio del servidor de rutas después de la operación |

La salida mostrará tres valores generados automáticamente:

- **GUID del Repositorio** -- Un UUID que identifica la imagen de disco cifrada en el servidor.
- **Credencial** -- Una frase de contraseña aleatoria utilizada para cifrar/descifrar el volumen LUKS.
- **ID de Red** -- Un número entero (comenzando en 2816, incrementando en 64) que determina la subred IP para los servicios de este repositorio.

> **Almacene la credencial de forma segura.** Es la clave de cifrado de su repositorio. Si se pierde, los datos no se pueden recuperar. La credencial se almacena en su `config.json` local pero no se almacena en el servidor.

## Montar y Desmontar

Montar descifra y hace accesible el sistema de archivos del repositorio. Desmontar cierra el volumen cifrado.

```bash
rdc repo mount --name my-app -m server-1  # Descifrar y montar
rdc repo unmount --name my-app -m server-1  # Desmontar y re-cifrar
```

| Opción | Descripción |
|--------|-------------|
| `--checkpoint` | Crear un checkpoint CRIU antes de montar/desmontar (para contenedores con etiqueta `rediacc.checkpoint=true`) |
| `--skip-router-restart` | Omitir el reinicio del servidor de rutas después de la operación |

## Verificar Estado

```bash
rdc repo status --name my-app -m server-1
```

## Listar Repositorios

```bash
rdc repo list -m server-1
```

## Redimensionar

Establezca el repositorio a un tamaño exacto o expanda una cantidad dada:

```bash
rdc repo resize --name my-app -m server-1 --size 20G  # Establecer tamaño exacto
rdc repo expand --name my-app -m server-1 --size 5G  # Agregar 5G al tamaño actual
```

> El repositorio debe estar desmontado antes de redimensionar.

## Bifurcar

Cree una copia de un repositorio existente en su estado actual:

```bash
rdc repo fork --parent my-app --tag staging -m server-1
```

Las bifurcaciones usan el modelo name:tag: la bifurcación resultante se llama `my-app:staging`. Esto crea una nueva copia cifrada con su propio GUID e ID de red, compartiendo el nombre del repositorio padre. La bifurcación comparte la misma credencial LUKS que el repositorio padre.

## Validar

Verifique la integridad del sistema de archivos de un repositorio:

```bash
rdc repo validate --name my-app -m server-1
```

## Propiedad

Establezca la propiedad de archivos dentro de un repositorio al usuario universal (UID 7111). Esto es típicamente necesario después de subir archivos desde su estación de trabajo, que llegan con su UID local.

```bash
rdc repo ownership --name my-app -m server-1
```

El comando detecta automáticamente los directorios de datos de contenedores Docker (montajes bind de escritura) y los excluye. Esto previene daños en contenedores que gestionan archivos con sus propios UIDs (por ejemplo, MariaDB=999, www-data=33).

| Opción | Descripción |
|--------|-------------|
| `--uid <uid>` | Establecer un UID personalizado en lugar de 7111 |
| `--skip-router-restart` | Omitir el reinicio del servidor de rutas después de la operación |

Para forzar la propiedad en todos los archivos, incluyendo datos de contenedores:

```bash
rdc repo ownership --name my-app -m server-1
```


Consulte la [Guía de Migración](/en/docs/migration) para un recorrido completo de cuándo y cómo usar la propiedad durante la migración de proyectos.

## Plantilla

Aplique una plantilla para inicializar un repositorio con archivos:

```bash
rdc repo template apply --name my-template -m server-1 -r my-app --file ./my-template.tar.gz
```

## Eliminar

Destruya permanentemente un repositorio y todos los datos dentro de él:

```bash
rdc repo delete --name my-app -m server-1
```

> Esto destruye permanentemente la imagen de disco cifrada. Esta acción no se puede deshacer.

## Migrar Repositorio

Migre en vivo un repositorio de una máquina a otra con un tiempo de inactividad mínimo.

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Opción | Descripción |
|--------|-------------|
| `--provision` | Aprovisionar el repositorio en la máquina destino antes de migrar (crea imagen LUKS y registra configuración) |
| `--checkpoint` | Crear un checkpoint CRIU de los contenedores en ejecución antes del corte |
| `--bwlimit <kbps>` | Limitar el ancho de banda de rsync en kilobytes por segundo |
| `--skip-dns` | Omitir la actualización de registros DNS tras el corte |

**Flujo en tres fases:**

1. **Pre-copia en caliente** - rsync transfiere datos mientras el repositorio sigue ejecutándose en el origen. Los archivos grandes se transfieren antes de cualquier tiempo de inactividad.
2. **Corte** - el repositorio se detiene en el origen, un pase final de rsync sincroniza los cambios restantes, y el repositorio arranca en el destino.
3. **Inicio en el destino** - renet monta e inicia el repositorio en la máquina destino. El DNS se actualiza a menos que se pase `--skip-dns`.

![Migración en Vivo de Repositorio](/img/repo-migrate-flow.svg)

**Push vs. migrar:**

| | `repo push` | `repo migrate` |
|--|-------------|----------------|
| Operación | Copiar | Mover |
| Origen tras operación | Sin cambios | Detenido |
| Tiempo de inactividad | Ninguno (solo copia) | Breve ventana de corte |
| Actualización DNS | No | Sí (excepto con `--skip-dns`) |
| Caso de uso | Copia de seguridad, clon de staging | Reemplazo de máquina, traslado de servidor |

## Limpiar

Después de eliminar repositorios o recuperarse de operaciones fallidas, pueden quedar directorios de montaje huérfanos, archivos de bloqueo y marcadores inamovibles. La limpieza los elimina de forma segura:

```bash
# Vista previa de lo que se eliminaría
rdc machine prune --name server-1 --dry-run

# Eliminar recursos huérfanos
rdc machine prune --name server-1
```

Solo se ven afectados los recursos sin imagen de repositorio correspondiente. Los directorios de montaje no vacíos nunca se eliminan.
