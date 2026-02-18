---
title: "Respaldo y Restauracion"
description: "Respalde repositorios cifrados en almacenamiento externo, restaure desde respaldos y programe respaldos automatizados."
category: "Guides"
order: 7
language: es
---

# Respaldo y Restauracion

Rediacc puede respaldar repositorios cifrados en proveedores de almacenamiento externo y restaurarlos en la misma o en diferentes maquinas. Los respaldos estan cifrados -- se requiere la credencial LUKS del repositorio para restaurar.

## Configurar Almacenamiento

Antes de enviar respaldos, registre un proveedor de almacenamiento. Rediacc soporta cualquier almacenamiento compatible con rclone: S3, B2, Google Drive y muchos mas.

### Importar desde rclone

Si ya tiene un remote de rclone configurado:

```bash
rdc context import-storage my-storage
```

Esto importa la configuracion de almacenamiento desde su configuracion de rclone al contexto actual.

### Ver Almacenamientos

```bash
rdc context storages
```

## Enviar un Respaldo

Envie un respaldo del repositorio al almacenamiento externo:

```bash
rdc backup push my-app -m server-1 --to my-storage
```

| Opcion | Descripcion |
|--------|-------------|
| `--to <storage>` | Ubicacion de almacenamiento destino |
| `--to-machine <machine>` | Maquina destino para respaldo de maquina a maquina |
| `--dest <filename>` | Nombre de archivo de destino personalizado |
| `--checkpoint` | Crear un punto de control antes de enviar |
| `--force` | Sobreescribir un respaldo existente |
| `--tag <tag>` | Etiquetar el respaldo |
| `-w, --watch` | Observar el progreso de la operacion |
| `--debug` | Habilitar salida detallada |

## Descargar / Restaurar un Respaldo

Descargue un respaldo del repositorio desde almacenamiento externo:

```bash
rdc backup pull my-app -m server-1 --from my-storage
```

| Opcion | Descripcion |
|--------|-------------|
| `--from <storage>` | Ubicacion de almacenamiento de origen |
| `--from-machine <machine>` | Maquina de origen para restauracion de maquina a maquina |
| `--force` | Sobreescribir respaldo local existente |
| `-w, --watch` | Observar el progreso de la operacion |
| `--debug` | Habilitar salida detallada |

## Listar Respaldos

Ver los respaldos disponibles en una ubicacion de almacenamiento:

```bash
rdc backup list --from my-storage -m server-1
```

## Sincronizacion Masiva

Envie o descargue todos los repositorios a la vez:

### Enviar Todos al Almacenamiento

```bash
rdc backup sync --to my-storage -m server-1
```

### Descargar Todos desde el Almacenamiento

```bash
rdc backup sync --from my-storage -m server-1
```

| Opcion | Descripcion |
|--------|-------------|
| `--to <storage>` | Almacenamiento destino (direccion de envio) |
| `--from <storage>` | Almacenamiento de origen (direccion de descarga) |
| `--repo <name>` | Sincronizar repositorios especificos (repetible) |
| `--override` | Sobreescribir respaldos existentes |
| `--debug` | Habilitar salida detallada |

## Respaldos Programados

Automatice los respaldos con un cronograma cron que se ejecuta como un temporizador systemd en la maquina remota.

### Configurar Cronograma

```bash
rdc backup schedule set --destination my-storage --cron "0 2 * * *" --enable
```

| Opcion | Descripcion |
|--------|-------------|
| `--destination <storage>` | Destino de respaldo predeterminado |
| `--cron <expression>` | Expresion cron (por ejemplo, `"0 2 * * *"` para diario a las 2 AM) |
| `--enable` | Habilitar el cronograma |
| `--disable` | Deshabilitar el cronograma |

### Enviar Cronograma a la Maquina

Despliegue la configuracion del cronograma en una maquina como un temporizador systemd:

```bash
rdc backup schedule push server-1
```

### Ver Cronograma

```bash
rdc backup schedule show
```

## Explorar Almacenamiento

Explore el contenido de una ubicacion de almacenamiento:

```bash
rdc storage browse my-storage -m server-1
```

## Mejores Practicas

- **Programe respaldos diarios** en al menos un proveedor de almacenamiento
- **Pruebe las restauraciones** periodicamente para verificar la integridad de los respaldos
- **Use multiples proveedores de almacenamiento** para datos criticos (por ejemplo, S3 + B2)
- **Mantenga las credenciales seguras** -- los respaldos estan cifrados pero se requiere la credencial LUKS para restaurar
