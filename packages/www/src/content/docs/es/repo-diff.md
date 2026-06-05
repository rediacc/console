---
title: "rdc repo diff"
description: "Mostrar una comparación de nivel de archivo estilo git entre dos repositorios bifurcados de copia en escritura, comparando sus imágenes cifradas a nivel de bloque, sin desencriptación."
category: Reference
subcategory: advanced
order: 40
language: es
sourceHash: "c72fbcc13e7e77ed"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# rdc repo diff

`rdc repo diff` muestra qué archivos cambiaron entre dos repositorios relacionados: una bifurcación y su principal, o cualquier dos repositorios que compartan un antepasado de copia en escritura. Pasa `--name <fork>` para comparar una bifurcación contra el principal que la configuración local registra para ella, o agrega `--base <repo>` para comparar contra un repositorio relacionado arbitrario, donde `--base` es el lado base (antiguo) y `--name` es el lado objetivo (nuevo). El comando es de solo lectura y nunca desencripta las imágenes. Las compara a nivel de bloque en la máquina remota, por lo que el costo sigue el número de bloques cambiados, no el tamaño del repositorio: un repositorio de 1 GB y uno de 100 GB con las mismas ediciones tardan el mismo tiempo. Si todo el repositorio cambió, el recuento de bloques escala con el tamaño y el costo también.

## Cuándo usarlo

Entonces: usa `repo diff` antes de promover una bifurcación. Un agente de IA se soltó en una copia bifurcada de producción y quieres ver exactamente qué archivos tocó antes de fusionar el cambio nuevamente: `repo diff --name <fork> -m <machine>` te da esa lista de archivos en segundos. Segundos. Después de una restauración de recuperación ante desastres, compara la bifurcación restaurada contra la instantánea que se suponía debía reproducir para confirmar que el conjunto de archivos esperado regresó y nada más se desvió. Para una bifurcación de larga vida que se ha ejecutado junto a su principal durante semanas, la comparación muestra la divergencia acumulada (ediciones de configuración, acumulación de registro, migraciones de esquema) sin montar y recorrer manualmente ambos árboles.

No la uses en repositorios no relacionados. Los dos lados deben compartir un antepasado de copia en escritura, porque la comparación funciona en el historial de bloques compartidos. Tampoco es una herramienta de comparación binaria: `--content` produce salida a nivel de línea solo para archivos de texto, y los binarios reportan `Binary files differ`.

## Referencia de comandos

### Sinopsis

```bash
rdc repo diff --name <fork> -m <machine>            # diff a fork against its parent
rdc repo diff --name <fork> --base <repo> -m <machine>   # diff against an arbitrary related repo
```

### Opciones

| Opción | Descripción | Predeterminado |
|--------|-------------|---------|
| `--name <name>` | Repositorio a inspeccionar (el lado objetivo, nuevo). Requerido. | requerido |
| `--base <name>` | Repositorio a comparar (el lado base, antiguo). Por defecto es el principal de `--name`, resuelto desde la configuración local. | principal de `--name` |
| (sin bandera de formato) | Salida de estado de nombre: una letra de color `A`/`M`/`D`/`R` por archivo cambiado más un resumen de una línea. | activado |
| `--name-only` | Una ruta cambiada por línea, sin letra de estado. Compatible con tuberías. | desactivado |
| `--stat` | Magnitud de cambio por archivo (deltas de bytes y bloques) con un pie de página de totales. | desactivado |
| `--content <path>` | Comparación de texto unificada de un único archivo. Solo texto; los binarios reportan `Binary files differ`. | desactivado |
| `--json` | Salida estructurada para agentes y scripts. | desactivado |
| `--fast` | Omitir el paso de confirmación de hash de contenido y confiar en el filtro de bloque. Más rápido, pero puede reportar excesivamente archivos como Modificados. | desactivado |
| `-m, --machine <name>` | Máquina objetivo. Requerido. | requerido |
| `--debug` | Diagnósticos detallados en stderr. | desactivado |
| `--skip-router-restart` | Omitir el paso de reinicio del enrutador. | desactivado |

## Ejemplos

### Estado de nombre predeterminado contra el principal

Con solo `--name`, la bifurcación se compara contra el principal registrado en la configuración local. Aquí la bifurcación `test-1gb:fork1` tiene un archivo modificado:

```bash
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### Comparación contra una base explícita

Pasa `--base` para comparar contra un repositorio relacionado arbitrario. `--base` es el lado base (antiguo), `--name` es el lado objetivo (nuevo):

```bash
$ rdc repo diff --name test-1gb:fork1 --base test-1gb:latest -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

### Magnitud de cambio con `--stat`

`--stat` añade el delta de bytes y bloques por archivo y un pie de página de totales:

```bash
$ rdc repo diff --name test-1gb:fork1 --stat -m hostinger
 hello.txt | +8 bytes, 1 block

1 file changed, 4096 bytes touched
```

### Solo rutas, canalizadas a una herramienta

`--name-only` imprime una ruta por línea sin letra de estado, lista para alimentar a otro comando:

```bash
$ rdc repo diff --name test-1gb:fork1 --name-only -m hostinger | xargs -I{} echo "review: {}"
review: hello.txt
```

### Comparación a nivel de línea de un archivo

`--content` produce una comparación unificada de un único archivo de texto:

```bash
$ rdc repo diff --name test-1gb:fork1 --content hello.txt -m hostinger
--- a/hello.txt
+++ b/hello.txt
@@ -1 +1 @@
-the original line of text in the parent
+the original line of text in the parent, now edited
```

### Filtrado de JSON con jq

`--json` emite la envoltura estructurada en stdout, por lo que se canaliza limpiamente a `jq`:

```bash
$ rdc repo diff --name test-1gb:fork1 --json -m hostinger | jq '.data.entries[] | select(.status=="M")'
{
  "status": "M",
  "path": "/hello.txt",
  "type": "file",
  "old_size": 53,
  "size": 61,
  "bytes_changed": 4096,
  "blocks_changed": 1,
  "inode": 13,
  "content_changed": true,
  "mode_changed": false,
  "uid_changed": false,
  "gid_changed": false
}
```

## Formatos de salida

### Estado de nombre (predeterminado)

Cada archivo cambiado obtiene una letra de estado y su ruta. `A` es agregado, `M` modificado, `D` eliminado, `R` renombrado (con la ruta antigua mostrada). Una línea de resumen sigue con el recuento por categoría.

### `--name-only`

Una ruta por línea, sin letra de estado, sin resumen. Úsalo cuando un comando posterior quiera una lista de archivos limpia.

### `--stat`

Cada línea lleva el delta de bytes del archivo y el delta de bloques. Un pie de página reporta el número total de archivos y el total de bytes tocados. Esto muestra dónde se concentra el peso de un cambio, no solo qué archivos se movieron.

### `--content <path>`

Una comparación unificada estándar (encabezados `---`/`+++`, fragmentos `@@`) para un único archivo de texto. Los archivos binarios reportan `Binary files differ` y no producen fragmentos.

### `--json`

El resultado estructurado completo. Los datos van a stdout; el progreso y los diagnósticos van a stderr, por lo que el JSON se canaliza limpiamente a `jq` u otro analizador incluso mientras se imprime el progreso.

## Esquema JSON

La CLI envuelve el resultado de renet en la envoltura estándar (`success`, `command`, `data`, `errors`, `warnings`, `metrics`). El resultado de la comparación vive en `data` con campos en snake_case:

```json
{
  "success": true,
  "command": "repo diff",
  "data": {
    "base": "<base-guid>",
    "target": "<target-guid>",
    "added": 0,
    "modified": 1,
    "deleted": 0,
    "renamed": 0,
    "strategy": "shared",
    "fast": false,
    "degraded": false,
    "block_size": 4096,
    "total_bytes_changed": 4096,
    "entries": [
      {
        "status": "M",
        "path": "/hello.txt",
        "type": "file",
        "old_size": 53,
        "size": 61,
        "bytes_changed": 4096,
        "blocks_changed": 1,
        "inode": 13,
        "content_changed": true,
        "mode_changed": false,
        "uid_changed": false,
        "gid_changed": false
      }
    ]
  }
}
```

Cada objeto en `entries[]` describe una ruta cambiada:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `status` | `A` \| `M` \| `D` \| `R` | Agregado, Modificado, Eliminado o Renombrado. |
| `path` | string | Ruta en el lado objetivo (o lado base para una eliminación). |
| `old_path` | string | Ruta anterior. Presente solo en cambios de nombre. |
| `type` | `file` \| `dir` \| `symlink` \| `other` | Tipo de entrada. |
| `old_size` | number | Tamaño en bytes en el lado base. |
| `size` | number | Tamaño en bytes en el lado objetivo. |
| `bytes_changed` | number | Bytes que difieren, redondeados a bloques completos. |
| `blocks_changed` | number | Número de bloques cambiados. |
| `inode` | number | Número de inodo, utilizado para detección de cambios de nombre. |
| `content_changed` | boolean | Si el contenido del archivo (no solo los metadatos) cambió. |
| `mode_changed` | boolean | Si el modo del archivo cambió. `old_mode`/`new_mode` están presentes cuando es verdadero. |
| `uid_changed` | boolean | Si el propietario cambió. `old_uid`/`new_uid` están presentes cuando es verdadero. |
| `gid_changed` | boolean | Si el grupo cambió. `old_gid`/`new_gid` están presentes cuando es verdadero. |
| `old_target` / `new_target` | string | Objetivos de enlace simbólico. Presentes para enlaces simbólicos cambiados. |

Para los campos de envoltura y las reglas de auto-detección que emiten JSON en entornos sin TTY, consulta la [Referencia de Salida JSON](/es/docs/ai-agents-json-output).

## Cómo funciona

Un repositorio es un archivo de imagen LUKS2 en un pool de btrfs, y una bifurcación es un reflink constante de esa imagen. `repo diff` compara las dos imágenes cifradas a nivel de bloque a través de FIEMAP, leyendo solo metadatos del sistema de archivos y nunca desencriptando nada. Desplaza los desplazamientos de texto cifrado cambiado por el desplazamiento de datos de LUKS para obtener desplazamientos de dispositivo ext4, luego mapea esos desplazamientos nuevamente a nombres de archivo a través del mapa de extensiones ext4 de cada archivo. Una caminata final de identidad de inodo de ambos montajes reconcilia el resultado en entradas Agregadas, Modificadas, Eliminadas y Renombradas. Porque el trabajo está limitado por el recuento de bloques cambiados, la comparación es independiente del tamaño del repositorio, y porque reutiliza un montaje vivo en su lugar, nunca perturba un repositorio en ejecución. El mecanismo completo se describe en [Git diff for encrypted disk images](/en/blog/git-diff-for-encrypted-disk-images).

## Limitaciones

- **Solo bifurcaciones relacionadas.** Ambos lados deben compartir un antepasado de copia en escritura. No hay una comparación significativa a nivel de bloque entre repositorios no relacionados.
- **La detección de cambios de nombre se basa en inodo.** Un archivo se reporta como renombrado cuando el mismo inodo aparece en una ruta nueva. Un eliminado-y-recreado (un inodo nuevo) se muestra como una entrada Eliminada más una Agregada, no un cambio de nombre.
- **`--content` solo es para texto.** Produce fragmentos a nivel de línea para archivos de texto. Los binarios reportan `Binary files differ`.
- **`--fast` puede reportar excesivamente Modificado.** Confía en el filtro de bloque y omite la confirmación de hash de contenido, por lo que un archivo cuyos bloques se movieron sin cambiar contenido puede aparecer como Modificado.
- **El tiempo de recorrido de extensión escala con fragmentación, no con tamaño.** Un sistema de archivos muy fragmentado tiene más extensiones para mapear, lo que alarga el recorrido incluso cuando el volumen de bytes de cambios es pequeño.

## Ver también

- [rdc repo fork](/es/docs/repositories). Crear la bifurcación de copia en escritura que este comando compara.
- [rdc repo status](/es/docs/repositories). Estado actual de un único repositorio.
- [rdc repo cat](/es/docs/repositories). Leer un único archivo de un repositorio.
