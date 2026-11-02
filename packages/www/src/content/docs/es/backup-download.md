---
title: "Descarga de respaldos"
description: "Copia la imagen cifrada de un repositorio en un directorio local o en una unidad externa, la actualiza en el sitio en ejecuciones posteriores o la reconstruye directamente desde el almacén de respaldos, sin ninguna máquina."
category: "Guides"
tags:
  - backup
  - storage
subcategory: data-protection
order: 8
language: es
sourceHash: "c52e6a0471befc30"
---

# Descarga de respaldos

`rdc backup download` mantiene una copia de la imagen cifrada de un repositorio en un directorio local o en una unidad externa. La copia es el mismo texto cifrado que reside en la máquina, así que nada se descifra por el camino. La credencial que la abre permanece en la configuración, por lo que la inscripción en [config storage](/es/docs/config-storage) es la forma de mantenerla a salvo. Sin la credencial, la imagen no se puede abrir.

Hay dos orígenes. Una máquina en ejecución es el predeterminado. El otro es el almacén de respaldos, que se elige con `--store`.

## Descarga desde una máquina

```bash
rdc backup download mail@prod --to /mnt/usb
```

`--to` indica un directorio existente y con permiso de escritura. Nunca se crea, así que la unidad debe montarse antes. La imagen queda en `<machine>/<name>.<tag>.img`, con un archivo `.state.json` al lado.

Cada ejecución toma un snapshot nuevo del repositorio que solo se conserva mientras dura la transferencia, envía las diferencias con rsync y compara un sha256 del resultado con el snapshot de la máquina.

| Flag | Efecto |
|------|--------|
| `--all -m <machine>` | Copia todos los repositorios grand ubicados en la máquina |
| `--include-forks` | Junto con `--all`, copia también los forks |
| `--bwlimit <rate>` | Limita el ancho de banda de red, por ejemplo `100Mbps` o `12.5M` |
| `--checkpoint` | Hace checkpoint y congela el repositorio antes del snapshot (respaldo en caliente) |
| `--retries <n>` | Reintentos dentro de la ejecución tras un fallo de red (3 por defecto) |
| `--skip-verify` | Omite la comparación sha256; el checksum propio de rsync se sigue ejecutando |
| `--skip-space-check` | Avisa en lugar de rechazar cuando el destino podría no tener espacio libre |

### Actualización de la copia

Una segunda ejecución actualiza la imagen existente en el sitio mediante el delta de rsync. Una ejecución semanal envía solo lo que cambió, y el destino necesita espacio para una copia de la imagen, no para dos. Antes de que empiece una ejecución, se comprueba el espacio libre frente al tamaño de la imagen, y `--skip-space-check` convierte un rechazo en un aviso.

### Ejecuciones interrumpidas y reanudación

El archivo de estado registra `status`. Vale `incomplete` desde antes de escribirse el primer byte hasta que una ejecución se verifica, y una imagen `incomplete` no es utilizable. Ctrl-C, una conexión perdida o un proceso terminado a la fuerza la dejan así. Volver a ejecutar el mismo comando reanuda, y solo se envían las diferencias. El comando termina con código 0 cuando el estado pasa a `complete`.

### Requisitos

La transferencia necesita rsync 3.1.3 o posterior en este equipo y no tiene alternativa por SFTP. Las distribuciones de Linux lo incluyen. En macOS, `brew install rsync` reemplaza el openrsync incluido, que no puede ejecutar la transferencia. En Windows, se instala MSYS2 con el paquete rsync, o se usa la aplicación de escritorio.

### Unidades externas

El sistema de archivos del destino decide qué cabe.

- **FAT32** no admite un archivo de más de 4 GiB, y el comando rechaza la ejecución.
- **exFAT** sin soporte de archivos dispersos almacena la imagen con su tamaño aparente completo, por lo que la comprobación de espacio libre cuenta ese tamaño.
- Un **snapshot copy-on-write** tomado localmente del destino (btrfs, ZFS, APFS) conserva versiones anteriores de la imagen. Cada actualización en el sitio cuesta entonces los bloques modificados además de los antiguos.

## Descarga desde el almacén de respaldos

```bash
export REDIACC_TOKEN=<api-token>
rdc backup download mail --store --to /mnt/usb
```

`--store` reconstruye la imagen directamente desde el almacén de chunks, sin ninguna máquina de por medio. El token de `REDIACC_TOKEN` necesita los scopes `backup:read` y `backup:restore`. Un inicio de sesión de la CLI nunca incluye `backup:restore`, así que el token se crea en la página API Tokens del portal. Debe pertenecer a un equipo y haber sido creado por un propietario o administrador actual de la organización.

`--store` admite exactamente un nombre de repositorio. No admite `-m`, `--checkpoint`, `--all`, `--include-forks`, `--bwlimit`, `--retries`, `--skip-verify` ni `--skip-space-check`: la descarga desde el almacén tiene su propia reanudación y verifica cada chunk.

La imagen se escribe en `<dir>/<name>.<tag>.img`. Una descarga interrumpida conserva la copia parcial, y el mismo comando continúa desde ella.

### Elegir un snapshot con `--at`

De forma predeterminada se obtiene el snapshot más reciente. `--at <time|snapshot>` selecciona otro, ya sea una hora en ISO 8601 o un id de snapshot. Solo se aplica junto con `--store`.

```bash
rdc backup download mail --store --to /mnt/usb --at 2026-10-01T00:00:00Z
```

En una plataforma distinta de Linux, la imagen obtenida está cifrada y no puede abrirse localmente. Se envía a una máquina Linux con `rdc backup upload`.

## Subir una copia de vuelta

```bash
rdc backup upload /mnt/usb/prod/mail.latest.img --to prod --as mail-copy --up
```

`rdc backup upload` envía una imagen descargada a una máquina y la registra como un repositorio nuevo. La transferencia se reanuda tras una interrupción, y la máquina comprueba el sha256 y la cabecera LUKS antes de colocar la imagen. El archivo de estado junto a la imagen aporta la credencial. Si ese archivo se pierde, `--from-repo <name>` indica el repositorio que la aporta.

| Flag | Efecto |
|------|--------|
| `--as <name>` | Nombre del nuevo repositorio (por defecto, el nombre de la imagen) |
| `--datastore <name>` | Coloca la imagen en un datastore con nombre |
| `--from-repo <name>` | Aporta la credencial y el linaje cuando el archivo de estado no se puede usar |
| `--bwlimit <rate>`, `--retries <n>` | Igual que en la descarga |
| `--up` | Inicia el repositorio una vez registrado |
| `--skip-verify` | Omite la comparación con el sha256 registrado en la descarga |

## Snapshots de transferencia obsoletos

Una transferencia terminada a la fuerza puede dejar su snapshot en la máquina. `rdc machine status` cuenta los snapshots de transferencia obsoletos en el resumen del pool, y `rdc machine prune <machine> --dry-run` los lista. Ejecutar `rdc machine prune <machine>` los elimina.

Véase [Respaldo y Restauración](/es/docs/backup-restore) para los snapshots hacia el almacenamiento de chunks.
