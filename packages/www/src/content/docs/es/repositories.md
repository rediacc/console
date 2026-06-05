---
title: Repositorios
description: 'Cree, gestione y opere repositorios cifrados con LUKS en máquinas remotas.'
category: Guides
order: 4
language: es
sourceHash: "ffb07e5870accfd8"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Repositorios

Un **repositorio** es una imagen de disco cifrada con LUKS en un servidor remoto. Cuando está montado, proporciona:
- Un sistema de archivos aislado para los datos de su aplicación
- Un daemon Docker dedicado (separado del Docker del host)
- IPs de loopback únicas para cada servicio dentro de una subred /26

## Crear un repositorio

```bash
rdc repo create --name my-app -m server-1 --size 10G
```

| Option | Required | Description |
|--------|----------|-------------|
| `-m, --machine <name>` | Yes | Target machine where the repository will be created |
| `--size <size>` | Yes | Size of the encrypted disk image (e.g., `5G`, `10G`, `50G`) |
| `--skip-router-restart` | No | Skip restarting the route server after the operation |

La salida mostrará tres valores generados automáticamente:

- **Repository GUID** - Un UUID que identifica la imagen de disco cifrado en el servidor.
- **Credential** - Una frase de paso aleatoria utilizada para cifrar/descifrar el volumen LUKS.
- **Network ID** - Un entero (comenzando en 2816, incrementando en 64) que determina la subred IP para los servicios de este repositorio.

> **Guarde la credencial de forma segura.** Es la clave de cifrado de su repositorio. Si se pierde, los datos no se pueden recuperar. La credencial se almacena en su `config.json` local pero no se almacena en el servidor.

## Montar y desmontar

Montar descifra y hace que el sistema de archivos del repositorio sea accesible. Desmontar cierra el volumen cifrado.

```bash
rdc repo mount --name my-app -m server-1  # Decrypt and mount
rdc repo unmount --name my-app -m server-1  # Unmount and re-encrypt
```

| Option | Description |
|--------|-------------|
| `--checkpoint` | Create a CRIU checkpoint before mount/unmount (for containers with `rediacc.checkpoint=true` label) |
| `--skip-router-restart` | Skip restarting the route server after the operation |

## Verificar estado

```bash
rdc repo status --name my-app -m server-1
```

## Listar repositorios

```bash
rdc repo list -m server-1
```

### Columna Type y el espejo de estado

La tabla de salida incluye una columna `Type` con tres valores:

- **`grand`**. Un repositorio de nivel superior registrado en su configuración de CLI local sin un padre. El caso base.
- **`fork`**. Un fork de copia en escritura de otro repositorio. Identificado ya sea a través de `grandGuid` en la configuración local **o** a través del espejo renet `.interim/state` en la máquina. Cualquiera de las fuentes es autoritativa; ambas deberían coincidir una vez que el espejo se haya poblado.
- **`unknown`**. Ninguna señal puede clasificar el repositorio. Más a menudo un fork heredado anterior al espejo (creado antes de que se enviara el código del espejo y nunca se remontara desde entonces), o un `grand` obsoleto cuya entrada de configuración local fue eliminada por error. La CLI se niega a adivinar; el operador debe ejecutar [el relleno del espejo](/es/docs/pruning#migration-state-mirror-backfill) o eliminar el directorio si realmente está huérfano.

El espejo `.interim/state/<guid>/.rediacc.json` es un pequeño archivo complementario escrito **fuera** del volumen cifrado con LUKS para que las herramientas de copia de seguridad y `repo list` puedan leer el linaje de fork sin desbloquear cada imagen. Tiene la misma forma que `.rediacc.json` en volumen (`is_fork`, `grand_guid`, `name`, etc.) y se actualiza en cada `Repository.SaveState`. Es decir, en cada montaje y cada mutación de estado. Es la fuente de verdad para la detección de fork en copias de seguridad programadas: un fork desmontado con un espejo que dice `is_fork: true` se salta correctamente de las cargas `cold` y `hot`.

Para la limpieza rutinaria de entradas desconocidas, consulte [`rdc machine prune --prune-unknown`](/es/docs/pruning#phase-3---prune-unknown-surgical).

## Cambiar tamaño

Establezca el repositorio a un tamaño exacto o expanda por una cantidad dada:

```bash
rdc repo resize --name my-app -m server-1 --size 20G  # Set to exact size
rdc repo expand --name my-app -m server-1 --size 5G  # Add 5G to current size
```

> El repositorio debe estar desmontado antes de cambiar su tamaño.

## Fork

Cree una copia de un repositorio existente en su estado actual:

```bash
rdc repo fork --parent my-app --tag staging -m server-1
```

Los forks utilizan el modelo name:tag: el fork resultante se llama `my-app:staging`. Esto crea una nueva copia cifrada con su propio GUID e ID de red, mientras comparte el nombre del padre. El fork comparte la misma credencial LUKS que el padre.

> Los forks comparten los datos del padre a través de BTRFS reflink, incluidas las credenciales almacenadas en disco. Consulte [Lo que Rediacc no aísla](/es/docs/ai-agents-safety#what-rediacc-does-not-isolate) para las implicaciones cuando esas credenciales autorizan servicios externos como Stripe, AWS o Railway. Para mantener las credenciales de tiempo de implementación fuera del alcance del fork, utilice [secretos por repositorio](#secrets) en lugar de incrustar valores en archivos `.env` dentro del repositorio.

En la creación del fork, `repo fork` escribe el [complemento del espejo de estado](#type-column-and-the-state-mirror) en `<datastore>/.interim/state/<fork-guid>/.rediacc.json` inmediatamente. Sin desbloquear el volumen. Entonces, el nuevo fork se identifica correctamente como `is_fork: true` desde el momento de la creación. Esto permite que las copias de seguridad programadas lo omitan (los forks se excluyen del pipeline de carga de forma predeterminada) incluso si nunca se monta. Cuando se realiza un fork de un fork, `grand_guid` se encadena correctamente: el espejo del nuevo fork apunta al GUID del abuelo original, no al fork intermedio.

## Versionado estilo Git

Los forks pueden actuar como commits de git. `rdc repo commit` congela un fork en uso en un commit inmutable y estable en bytes; `rdc repo branch` nombra una línea de historial; `rdc repo checkout` clona mediante reflink un commit de vuelta a un fork escribible; `rdc repo log` recorre la cadena de padres; y `rdc repo merge` combina dos líneas sin mutar un repositorio activo en su lugar. `rdc repo fork --immutable` produce una base equivalente a un commit en un solo paso.

```bash
rdc repo commit --name my-app:work --message "schema migration applied" -m server-1
rdc repo branch --branch staging --name my-app:work
rdc repo checkout --ref staging --from my-app:work --tag staging-copy -m server-1
```

Consulte la [referencia de ramificación estilo Git](/es/docs/repo-branching) para el conjunto completo de comandos, opciones y ejemplos detallados.

## Secretos

Los secretos por repositorio son credenciales de tiempo de implementación inyectadas en contenedores sin ser escritas en la imagen del repositorio cifrado. Se mantienen en un plano separado de los datos del repositorio, por lo que `rdc repo fork` no los propaga. Un fork comienza con un mapa de secretos vacío y sus contenedores se inician identificándose como un principal externo diferente al del padre.

> ¿Quiere un tutorial paso a paso? Consulte el [tutorial Administración de secretos](/es/docs/tutorial-managing-secrets) para el ciclo completo de set/list/deploy/verify/rotate.

**Modelo de solo escritura (estilo GitHub):** `get` devuelve solo el resumen SHA-256. El valor en texto plano nunca se devuelve a nadie, humano o agente. Si olvida cuál es un valor, búsquelo en su administrador de contraseñas y rótelo; no puede leerlo de nuevo desde Rediacc por diseño. Esto elimina una clase completa de fuga: grabaciones de terminal, historial de shell, redirección accidental, espionaje visual.

Dos modos de entrega:

- `env`. El secreto se exporta como `REDIACC_SECRET_<KEY>` en el shell renet en la máquina de destino. Hágale referencia desde su `docker-compose.yml` mediante interpolación `${REDIACC_SECRET_<KEY>}`. Visible dentro del entorno del contenedor, por lo que use esto para valores con forma de cadena de conexión que la aplicación ya espera en env.
- `file`. El secreto se escribe en `/var/run/rediacc/secrets/<networkID>/<KEY>` en el host (tmpfs, nunca persistido). Hágale referencia desde su archivo de composición mediante una declaración de `secrets:` de nivel superior con origen `file:`, más una lista `secrets:` por servicio. Los contenedores leen desde `/run/secrets/<key>`. Prefiera este modo para cualquier cosa sensible. Nunca aparece en `docker inspect` o `/proc/<pid>/environ`.

```bash
# Set, list, get (digest only), unset
rdc repo secret set --name my-app --key STRIPE_LIVE_KEY --value sk_live_xxx --mode file --current ""
rdc repo secret set --name my-app --key DB_HOST         --value postgres.internal --mode env --current ""
rdc repo secret list --name my-app
rdc repo secret get  --name my-app --key DB_HOST    # → { key, mode, digest } — no value
rdc repo secret unset --name my-app --key STRIPE_LIVE_KEY --current sk_live_xxx
```

**Puerta de mutación simétrica.** Tanto los humanos como los agentes necesitan `--current <previous-value>` para sobrescribir o desactivar un secreto (precondición estilo contraseña). Para la primera escritura de una clave nueva, pase `--current ""` (vacío). Para rotar sin verificar el valor anterior, pase `--rotate-secret` en su lugar. Esto se audita ruidosamente como una rotación. `--current` y `--rotate-secret` son mutuamente excluyentes.

Pase `--value -` para leer desde stdin en lugar de argv (evita la exposición del historial del shell para escrituras puntuales).

En su `docker-compose.yml`:

```yaml
services:
  api:
    image: myapp
    environment:
      DATABASE_HOST: ${REDIACC_SECRET_DB_HOST}
    secrets:
      - stripe_live_key

secrets:
  stripe_live_key:
    file: /var/run/rediacc/secrets/${REDIACC_NETWORK_ID}/STRIPE_LIVE_KEY
```

La referencia minúscula del lado del servicio (`stripe_live_key`) es el nombre del archivo `/run/secrets/<name>` dentro del contenedor; la parte en mayúsculas de la ruta del host (`STRIPE_LIVE_KEY`) coincide con lo que establece con `--key`. `${REDIACC_NETWORK_ID}` se interpola automáticamente por `renet compose`.

> **Aislamiento entre repositorios aplicado**: el validador de composición de renet rechaza rutas `secrets: file:` (y `configs: file:`, y `env_file:`) que hacen referencia al ID de red de cualquier otro repositorio. El token literal `${REDIACC_NETWORK_ID}` (o el entero de su propia red) es la única forma aceptada para referencias `/var/run/rediacc/secrets/...`. Y `--unsafe` NO anula esta verificación. La sandbox de Landlock alrededor del subproceso bash de Rediaccfile también limita el acceso del sistema de archivos solo al directorio de secretos de su propia red, por lo que un `cat /var/run/rediacc/secrets/<other>/X` malicioso de un Rediaccfile falla con EACCES en el nivel del kernel.

> **Forks**: `rdc repo fork` **no** copia secretos. Para usar secretos en un fork, ejecute `rdc repo secret set --name <fork>` en el fork explícitamente. Esta es la propiedad de seguridad que soporta la carga. Los contenedores del fork no deberían poder actuar como el principal de producción contra servicios externos.

> **Agentes** (Claude Code, Cursor, etc.): `repo secret list` y `repo secret get` se exponen como herramientas MCP (seguro de lectura. Solo nombres y resúmenes, nunca valores). `set` y `unset` son solo CLI porque la ceremonia `--current`/`--rotate-secret` requiere supervisión humana; los agentes que los llaman a través del shell reciben la misma puerta que los humanos. Cuando falla la precondición, la envoltura JSON contiene un campo `errors[].next.options[].run` estructurado. Los agentes deben retransmitir esos comandos textualmente al usuario. Consulte [AI agent safety](/es/docs/ai-agents-safety) para el modelo completo.

## Validar

Verifique la integridad del sistema de archivos de un repositorio:

```bash
rdc repo validate --name my-app -m server-1
```

## Propiedad

Establezca la propiedad del archivo dentro de un repositorio en el usuario universal (UID 7111). Esto suele ser necesario después de cargar archivos desde su estación de trabajo, que llegan con su UID local.

```bash
rdc repo ownership --name my-app -m server-1
```

El comando detecta automáticamente directorios de datos de contenedores Docker (montajes bind escribibles) y los excluye. Esto evita romper contenedores que administran archivos con sus propios UID (por ejemplo, MariaDB=999, www-data=33).

| Option | Description |
|--------|-------------|
| `--uid <uid>` | Set a custom UID instead of 7111 |
| `--skip-router-restart` | Skip restarting the route server after the operation |

Para forzar la propiedad en todos los archivos, incluidos los datos del contenedor:

```bash
rdc repo ownership --name my-app -m server-1
```


Consulte la [Guía de migración](/es/docs/migration) para ver un tutorial completo sobre cuándo y cómo usar la propiedad durante la migración del proyecto.

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

> Esto destruye permanentemente la imagen de disco cifrado. Esta acción no se puede deshacer.

## Migrar repositorio

Migre en vivo un repositorio de una máquina a otra. El único tiempo de inactividad es la fase de sincronización de delta final: normalmente segundos a minutos bajos dependiendo de la tasa de escritura en el cambio.

```bash
rdc repo migrate --name my-app --from server-1 --to server-2
```

| Option | Description |
|--------|-------------|
| `--provision` | Provision the repository on the target machine before migrating (creates LUKS image and registers config) |
| `--checkpoint` | Create a CRIU checkpoint of running containers before cutover |
| `--bwlimit <kbps>` | Limit rsync bandwidth in kilobytes per second |
| `--skip-dns` | Skip updating DNS records after cutover |

**Flujo de tres fases:**

1. **Precopia en caliente** - rsync transfiere datos mientras el repositorio sigue funcionando en la fuente. Los archivos grandes se transfieren antes de cualquier tiempo de inactividad.
2. **Cambio** - el repositorio se detiene en la fuente, un pase rsync final sincroniza los cambios restantes y el repositorio se inicia en el destino.
3. **Iniciar en el destino** - renet monta e inicia el repositorio en la máquina de destino. DNS se actualiza a menos que se pase `--skip-dns`.

![Repository Live Migration](/img/repo-migrate-flow.svg)

**Push vs migrar:**

| | `repo push` | `repo migrate` |
|--|-------------|----------------|
| Operation | Copy | Move |
| Source after | Unchanged | Stopped |
| Downtime | None (copy only) | Brief cutover window |
| DNS update | No | Yes (unless `--skip-dns`) |
| Use case | Backup, staging clone | Machine replacement, server move |

## Podar

Después de eliminar repositorios o recuperarse de operaciones fallidas, pueden quedar directorios de montaje huérfanos, archivos de bloqueo y marcadores inamovibles. Podar los elimina de forma segura:

```bash
# Preview what would be removed
rdc machine prune --name server-1 --dry-run

# Remove orphaned resources
rdc machine prune --name server-1
```

Solo se ven afectados los recursos sin imagen de repositorio coincidente. Los directorios de montaje no vacíos nunca se eliminan.
