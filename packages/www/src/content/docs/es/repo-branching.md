---
title: "Ramificación tipo git"
description: "Trate las bifurcaciones de copia en escritura como commits de git: congele una bifurcación en un commit inmutable, nombre ramas, revise commits en bifurcaciones escribibles, recorra el historial y fusione sin mutar nunca un repositorio activo."
category: Reference
subcategory: advanced
order: 41
language: es
sourceHash: "6ca18986dfd6e237"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Ramificación tipo git

Los repositorios de Rediacc admiten un control de versiones similar a git basado en bifurcaciones de copia en escritura. Cada bifurcación inmutable es un **commit**: una imagen estable a nivel de bytes, congelada, que se niega a montarse. Las ramas son referencias con nombre que apuntan a un commit. `rdc repo checkout` clona un commit mediante reflink de vuelta a una bifurcación de trabajo escribible, y `rdc repo merge` combina dos líneas de historial sin mutar nunca un repositorio activo en su lugar.

El modelo se aplica a dos almacenes. La **máquina es el almacén de objetos**: los commits son imágenes de bifurcación inmutables que viven en el almacén de datos. La **configuración del CLI es el almacén de referencias**: los nombres de ramas, el `HEAD` actual y el reflog viven en su configuración local, no en la máquina. Esta es la misma división que git usa entre `.git/objects` y `.git/refs`.

## Cuándo usarlo

Use la ramificación cuando una bifurcación haya ganado un nombre. Un agente de IA corrió sin control en una bifurcación de producción, el resultado se ve bien, y quiere un punto de control congelado y con nombre al que pueda regresar o promover más tarde: `rdc repo commit` lo congela, `rdc repo branch` le da nombre. Antes de una migración arriesgada, confirme la bifurcación de trabajo para tener un punto de reversión exacto que garantizadamente nunca cambiará (un commit inmutable se niega a montarse, por lo que nada puede escribir en él). Para comparar dos puntos de control, `rdc repo diff` funciona entre dos commits cualesquiera porque comparten un ancestro de copia en escritura. Para incorporar una línea de trabajo revisada de vuelta en una bifurcación de destino, `rdc repo merge` construye el resultado en un clon con reflink y lo intercambia atómicamente, de modo que un destino en ejecución nunca queda corrupto a mitad de la fusión.

No lo use como sustituto de `rdc repo fork` cuando solo necesita una copia desechable. Una bifurcación simple es la unidad correcta para el aislamiento efímero por prueba. Los commits añaden valor cuando un estado vale la pena conservar, nombrar o publicar.

## Cómo se relacionan los commits y las bifurcaciones

Un repositorio es un archivo de imagen LUKS en un pool btrfs. Una bifurcación es un reflink de tiempo constante de esa imagen, por lo que bifurcar un repositorio de 1 GB y uno de 100 GB cuesta lo mismo. Un **commit** es una bifurcación que ha sido marcada como inmutable: renet se niega a montarla, lo que mantiene su imagen estable a nivel de bytes para siempre. Esa estabilidad de bytes es lo que hace de un commit un punto de reversión fiable y una base determinista para la transferencia delta entre máquinas.

`rdc repo commit` registra el mensaje del commit, el autor, la marca de tiempo y el commit padre **dentro del volumen** (de modo que los metadatos viajan con la imagen al hacer push) y también los refleja fuera del volumen (de modo que `rdc repo log` pueda recorrer el historial sin desbloquear nada). La bifurcación de trabajo confirmada continúa sin cambios, exactamente como git deja el árbol de trabajo intacto después de un commit.

## Comandos

### rdc repo commit

Congela una bifurcación de trabajo montada en un nuevo commit inmutable.

```bash
rdc repo commit --name <fork> --message "<message>" -m <machine>
```

| Opción | Descripción | Predeterminado |
|--------|-------------|----------------|
| `--name <name>` | Bifurcación de trabajo a confirmar. Debe estar montada. Obligatorio. | obligatorio |
| `--message <msg>` | Mensaje del commit. Obligatorio. | obligatorio |
| `--author <author>` | Autor del commit registrado en los metadatos. | sin definir |
| `-m, --machine <name>` | Máquina de destino. Obligatorio. | obligatorio |
| `--debug` | Diagnósticos detallados en stderr. | desactivado |

El nuevo commit se registra en la configuración local con `immutable: true`, y el `headCommit` de la bifurcación de trabajo avanza para apuntar a él. Confirmar un repositorio inmutable se rechaza: primero revíselo en una bifurcación escribible.

### rdc repo branch

Crea una referencia de rama con nombre que apunta al commit actual de una bifurcación de trabajo.

```bash
rdc repo branch --branch <name> --name <fork>
```

| Opción | Descripción | Predeterminado |
|--------|-------------|----------------|
| `--branch <branch>` | Nombre de la nueva rama. Obligatorio. | obligatorio |
| `--name <name>` | Bifurcación de trabajo cuyo commit actual señala la rama. Obligatorio. | obligatorio |

Esta es una operación solo de configuración. No se realiza ningún trabajo en la máquina. La referencia de rama asigna un nombre al `headCommit` de la bifurcación de trabajo, por lo que la bifurcación debe tener al menos un commit primero.

### rdc repo checkout

Clona mediante reflink un commit inmutable (o la punta de una rama) en una nueva bifurcación de trabajo escribible.

```bash
rdc repo checkout --ref <commit> --tag <newFork> -m <machine>
rdc repo checkout --ref <branchName> --from <fork> --tag <newFork> -m <machine>
```

| Opción | Descripción | Predeterminado |
|--------|-------------|----------------|
| `--ref <commit\|branch>` | GUID del commit a revisar, o un nombre de rama cuando se usa `--from`. Obligatorio. | obligatorio |
| `--tag <name>` | Nombre para la nueva bifurcación de trabajo escribible. Obligatorio. | obligatorio |
| `-m, --machine <name>` | Máquina de destino. Obligatorio. | obligatorio |
| `--from <workingFork>` | Resuelve `--ref` como nombre de rama en el conjunto de ramas de esta bifurcación de trabajo. | commit directo |
| `--debug` | Diagnósticos detallados en stderr. | desactivado |
| `--skip-router-restart` | Omitir el paso de reinicio del router. | desactivado |

El checkout reutiliza la ruta de reflink de bifurcación, por lo que es casi instantáneo y de tiempo constante independientemente del tamaño del repositorio. El `headCommit` de la nueva bifurcación de trabajo se establece al commit revisado.

### rdc repo log

Recorre el historial de commits alcanzable desde una bifurcación de trabajo o un commit.

```bash
rdc repo log --name <fork> -m <machine>
```

| Opción | Descripción | Predeterminado |
|--------|-------------|----------------|
| `--name <name>` | Bifurcación de trabajo o commit desde donde iniciar el recorrido del historial. Obligatorio. | obligatorio |
| `-m, --machine <name>` | Máquina de destino. Obligatorio. | obligatorio |
| `--json` | Muestra el historial de commits como JSON. | desactivado |
| `--debug` | Diagnósticos detallados en stderr. | desactivado |

`log` recorre la cadena de padres registrada por `rdc repo commit`, leyendo el espejo de estado fuera del volumen, por lo que ningún commit se desbloquea ni se monta. Es de solo lectura.

### rdc repo merge

Fusiona un commit fuente o una bifurcación en una bifurcación de trabajo de destino, sin mutar el destino activo en su lugar.

```bash
rdc repo merge --name <target> --from <source> -m <machine>
rdc repo merge --name <target> --from <source> --resolve theirs -m <machine>
```

| Opción | Descripción | Predeterminado |
|--------|-------------|----------------|
| `--name <name>` | Bifurcación de trabajo de destino en la que fusionar. Obligatorio. | obligatorio |
| `--from <source>` | Commit fuente o bifurcación desde donde fusionar. Obligatorio. | obligatorio |
| `-m, --machine <name>` | Máquina de destino. Obligatorio. | obligatorio |
| `--force` | Aquietar primero un destino montado o en ejecución y luego fusionar. Nunca muta un montaje activo. | desactivado |
| `--resolve <ours\|theirs>` | Fusión de tres vías por archivo: incorpora los cambios por archivo del fuente en el destino, conservando (`ours`) o tomando (`theirs`) la versión del fuente para los archivos cambiados en ambos lados. Omitir para tomar el fuente en su totalidad. | desactivado |
| `--base <guid>` | Commit ancestro común para la fusión de tres vías (se usa con `--resolve`). Por defecto es el padre del commit fuente o el commit actual del destino. | automático |
| `--debug` | Diagnósticos detallados en stderr. | desactivado |

El resultado se construye en un clon con reflink y se intercambia atómicamente detrás de un marcador seguro ante fallos, de modo que una fusión interrumpida deja el destino original intacto. Un destino montado o en ejecución se rechaza a menos que se use `--force`, que cierra limpiamente el destino antes del intercambio.

Sin `--resolve`, la fusión toma el fuente en su totalidad (el destino pasa a ser el fuente). Con `--resolve`, es una fusión de tres vías por archivo contra el padre registrado del commit fuente: los archivos cambiados solo en un lado se toman de ese lado, y los archivos cambiados en ambos lados se resuelven según el flag. Las rutas en conflicto se informan.

### rdc repo gc

Recolecta objetos de commit inmutables en una máquina a los que ninguna rama ni HEAD alcanza.

```bash
rdc repo gc -m <machine>            # previsualización en seco (predeterminado)
rdc repo gc --apply -m <machine>    # elimina los commits inalcanzables
```

| Opción | Descripción | Predeterminado |
|--------|-------------|----------------|
| `-m, --machine <name>` | Máquina en la que recolectar. Obligatorio. | obligatorio |
| `--apply` | Elimina efectivamente los commits inalcanzables (de lo contrario, es una previsualización en seco). | desactivado |
| `--debug` | Diagnósticos detallados en stderr. | desactivado |

La alcanzabilidad se calcula desde la configuración local (el almacén de referencias): el conjunto de commits alcanzables siguiendo cada punta de rama y HEAD por la cadena de padres. Los commits inmutables en la máquina fuera de ese conjunto son inalcanzables. Un objeto montado o una bifurcación de trabajo nunca se recolectan.

### rdc repo fsck

Valida las referencias de configuración contra los objetos presentes en una máquina.

```bash
rdc repo fsck -m <machine>
```

| Opción | Descripción | Predeterminado |
|--------|-------------|----------------|
| `-m, --machine <name>` | Máquina a verificar. Obligatorio. | obligatorio |

Informa sobre referencias colgantes (una punta de rama o HEAD que apunta a un GUID sin objeto en la máquina) y commits huérfanos (un commit inmutable en la máquina al que ninguna referencia alcanza). Es de solo lectura; recupere huérfanos con `rdc repo gc --apply`.

### Bifurcaciones inmutables

`rdc repo fork --immutable` marca la nueva bifurcación como de solo lectura en el momento de la creación, produciendo una base equivalente a un commit sin un paso `commit` separado.

```bash
rdc repo fork --parent <name> --tag <tag> --immutable -m <machine>
```

Una bifurcación inmutable se niega a montarse, lo que mantiene su imagen estable a nivel de bytes para siempre. Esto es útil como base congelada para la transferencia delta entre máquinas, donde la base debe ser idéntica en ambos extremos. Para realizar cambios, revísela (o bifúrquela de nuevo) en una copia escribible.

## Ejemplos

### Confirmar una bifurcación de trabajo

```bash
$ rdc repo commit --name myapp:work --message "schema migration applied" -m server-1
Committed 4f3c2a1b9d8e: schema migration applied
```

### Confirmar con un autor explícito

```bash
$ rdc repo commit --name myapp:work --message "nightly snapshot" --author ci-bot -m server-1
Committed 7a1b2c3d4e5f: nightly snapshot
```

### Nombrar una rama en el commit actual

```bash
$ rdc repo branch --branch staging --name myapp:work
Branch "staging" -> 4f3c2a1b9d8e
```

### Revisar un commit en una nueva bifurcación escribible

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag rollback-test -m server-1
```

### Revisar la punta de una rama por nombre

Con `--from`, el valor de `--ref` se resuelve como nombre de rama en la bifurcación de trabajo indicada:

```bash
$ rdc repo checkout --ref staging --from myapp:work --tag staging-copy -m server-1
```

### Recorrer el historial

```bash
$ rdc repo log --name myapp:work -m server-1
commit 4f3c2a1b9d8e
  Author: ci-bot  Date: 2026-05-29T10:14:02Z
  schema migration applied
commit 9d8e7a1b2c3d
  Author: ci-bot  Date: 2026-05-28T22:01:55Z
  initial import
```

### Historial como JSON

`--json` emite el recorrido estructurado, el más reciente primero:

```bash
$ rdc repo log --name myapp:work --json -m server-1
{
  "success": true,
  "start": "4f3c2a1b9d8e",
  "entries": [
    {
      "guid": "4f3c2a1b9d8e",
      "message": "schema migration applied",
      "author": "ci-bot",
      "parent": "9d8e7a1b2c3d",
      "committed_at": "2026-05-29T10:14:02Z",
      "immutable": true
    }
  ]
}
```

### Comparar dos commits

`rdc repo diff` funciona entre dos commits cualesquiera porque comparten un ancestro de copia en escritura. Revise un commit y luego compárelo con otro:

```bash
$ rdc repo checkout --ref 4f3c2a1b9d8e --tag review -m server-1
$ rdc repo diff --name review --base myapp:work -m server-1
M  db/schema.sql

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

Consulte [rdc repo diff](/es/docs/repo-diff) para la referencia completa de diff.

### Fusionar una línea de trabajo revisada

```bash
$ rdc repo merge --name myapp:main --from myapp:work -m server-1
Merged myapp:work into myapp:main
```

### Fusionar en un destino en ejecución

Un destino montado o en ejecución se rechaza a menos que se use `--force`, que lo aquieta primero:

```bash
$ rdc repo merge --name myapp:main --from myapp:work --force -m server-1
Merged myapp:work into myapp:main
```

### Fusión de tres vías por archivo

Dos bifurcaciones (`feature` y `hotfix`) revisadas desde el mismo commit cambiaron algunos archivos cada una. `--resolve theirs` incorpora el fuente (`hotfix`) en el destino (`feature`): los archivos que solo un lado cambió se toman de ese lado, y los archivos que ambos lados cambiaron se resuelven al fuente. La base se detecta automáticamente desde el ancestro compartido (o se puede fijar con `--base`):

```bash
$ rdc repo merge --name myapp:feature --from myapp:hotfix --resolve theirs -m server-1
Merged myapp:hotfix into myapp:feature (three-way); 1 conflict(s) resolved --theirs: [config/app.yaml]
```

`config/app.yaml` cambió en ambos lados y se resolvió al fuente; un archivo que solo `hotfix` añadió se aplica, y un archivo que solo `feature` cambió se conserva. Las rutas en conflicto se informan para que pueda revisarlas.

### Crear una base inmutable directamente

```bash
$ rdc repo fork --parent myapp --tag baseline-v1 --immutable -m server-1
```

## Transferencia delta de push y pull

Una imagen inmutable y estable a nivel de bytes es también la base para la **transferencia delta a nivel de bloque**. Cuando la misma base inmutable existe en dos máquinas, un push o pull puede calcular los bloques cambiados contra esa base y mover solo esos, en lugar de escanear toda la imagen cifrada. Un repositorio de 1 GB con unos pocos bloques cambiados se transfiere en megabytes.

Normalmente no es necesario pasar una base manualmente. Después de un push completo, el CLI retiene la imagen publicada como base inmutable en ambas máquinas y la registra, de modo que el **siguiente** push de ese repositorio envía automáticamente solo el delta, sin ningún flag, incluso para una bifurcación que ya existe en el destino. (Un re-push *completo* de una bifurcación existente sigue necesitando `--force`, ya que reemplaza toda la imagen en lugar de aplicar un delta verificado.) Pase `--delta-base <guid>` para fijar una base específica, y `--strategy <auto|physical|shared>` para controlar cómo se detectan los bloques cambiados (`auto` es correcto en casi todos los casos).

```bash
# El primer push es una transferencia completa; también retiene una base reutilizable en ambos extremos.
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# Tras los cambios locales, el siguiente push envía solo los bloques cambiados, sin flag necesario.
$ rdc repo push --name myapp:work --to-machine backup-1 -m server-1

# Fijar una base explícita (un commit inmutable presente en ambas máquinas).
$ rdc repo push --name myapp:work --to-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# El delta también funciona en sentido inverso, extrayendo solo los bloques cambiados de una máquina fuente.
$ rdc repo pull --name myapp:work --from-machine backup-1 --delta-base 4f3c2a1b9d8e -m server-1

# Re-extraer un repositorio local existente (sobreescribirlo) con --force.
$ rdc repo pull --name myapp:work --from-machine backup-1 --force -m server-1
```

La transferencia delta solo se aplica entre máquinas (un remoto con la base FIEMAP). Los pushes a almacenamiento de objetos en la nube siempre transfieren la imagen completa. La base debe ser byte a byte idéntica en ambos extremos, que es exactamente lo que garantiza un commit inmutable o una bifurcación con `--immutable`.

## Esquema JSON

`rdc repo log --json` envuelve el resultado de renet en el sobre estándar. El historial recorrido vive en `entries`, el más reciente primero:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `success` | boolean | Si el recorrido se completó. |
| `start` | string | GUID desde donde comenzó el recorrido. |
| `entries` | array | Un objeto por commit, el más reciente primero. |
| `entries[].guid` | string | GUID del commit. |
| `entries[].message` | string | Mensaje del commit. Omitido cuando está vacío. |
| `entries[].author` | string | Autor del commit. Omitido cuando está vacío. |
| `entries[].parent` | string | GUID del commit padre. Omitido en la raíz. |
| `entries[].committed_at` | string | Marca de tiempo del commit en RFC 3339. Omitida cuando no está definida. |
| `entries[].immutable` | boolean | Si el commit está marcado como de solo lectura (siempre true para un commit real). |

Para los campos del sobre y las reglas de detección automática que emiten JSON en entornos sin TTY, consulte la [Referencia de Salida JSON](/es/docs/ai-agents-json-output).

## Limitaciones

- **Las referencias son locales.** Los nombres de ramas, `HEAD` y el reflog viven en su configuración del CLI, no en la máquina. Hacer push de un commit a otra máquina envía el objeto commit y sus metadatos dentro del volumen, pero la referencia de rama es un concepto del lado de la configuración.
- **Un commit se niega a montarse.** Ese es el punto: la inmutabilidad es lo que hace que un commit sea estable a nivel de bytes. Para ejecutar o editar un commit, revíselo primero en una bifurcación de trabajo escribible.
- **La resolución de fusión es a nivel de archivo, no de línea.** Se admiten tanto la toma del fuente en su totalidad (sin `--resolve`) como la fusión de tres vías por archivo (`--resolve ours|theirs`). La fusión de tres vías resuelve los conflictos archivo a archivo según el flag; no produce hunks a nivel de línea ni marcadores de fusión dentro de un archivo.
- **El historial es una cadena de padres.** `rdc repo log` recorre el único enlace `parent` registrado en el momento del commit. Se detiene cuando alcanza un commit cuyos metadatos no están presentes en la máquina consultada.

## Véase también

- [rdc repo diff](/es/docs/repo-diff). Diferencia a nivel de archivo entre dos commits o bifurcaciones relacionados.
- [Repositorios](/es/docs/repositories). Crear, bifurcar, montar y operar repositorios.
