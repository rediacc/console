---
title: "Respaldo y Restauración"
description: "Toma snapshots de repositorios cifrados hacia almacenamiento fragmentado direccionado por contenido, donde solo se suben las celdas cambiadas y cada snapshot se restaura directamente. O conserva una copia en otra máquina. Restaura en cualquier lugar, y automatízalo con estrategias nombradas y temporizadores systemd."
category: "Guides"
order: 7
language: es
sourceHash: "91f6072e230b059c"
sourceCommit: "79c84ad044d5730b6d0a20aaf7b21f21914b6bda"
---

# Respaldo y Restauración

Rediacc respalda repositorios cifrados y los restaura en la misma máquina o en una diferente. Los respaldos están cifrados porque el repositorio lo está: lo que sale de la máquina es el texto cifrado, y se requiere la credencial LUKS de tu repositorio para restaurar.

Hay dos formas de respaldar, y responden preguntas distintas.

- **Snapshots al almacenamiento fragmentado** (`rdc backup snapshot`) mantienen un historial por el que puedes retroceder. Esta es la vía principal.
- **Una copia en otra máquina** (`rdc repo push`, `rdc repo pull`) mantiene el repositorio tal como está ahora, en hardware que tú controlas. No interviene ninguna cuenta en la nube.

Son independientes. Un repositorio respaldado de una forma no queda respaldado de la otra.

## Cómo funcionan los snapshots

La imagen del repositorio se corta en celdas de tamaño fijo sobre una cuadrícula fija. Cada celda es un agujero, es decir, nunca se escribió nada ahí, o se almacena bajo una clave que **es** el SHA-256 del texto cifrado de esa celda.

De esa única decisión salen las propiedades.

**Solo los cambios reales cuestan algo.** El primer snapshot sube cada celda escrita. Cada ejecución posterior pregunta al sistema de archivos qué extents se tocaron, lee y hashea solo esas, y sube solo las celdas que el almacén aún no tiene. Un repositorio cuyos datos apenas se movieron sube casi nada, y la ejecución tarda minutos en lugar de lo que tarde según el tamaño de la imagen.

**Los datos idénticos se almacenan una sola vez.** Como la clave es el hash del contenido, dos snapshots que comparten una celda comparten el objeto, y lo mismo pasa entre un repositorio y sus [forks](/es/docs/tutorial-forking): una familia de forks respalda contra un único linaje en lugar de duplicar a su padre.

**Restaurar un snapshot antiguo no es más lento que restaurar uno reciente.** No hay cadena de incrementos que reproducir. Restaurar resuelve el snapshot en una lista completa de celdas y las obtiene directamente, así que el tiempo de restauración depende del tamaño de la imagen y de tu ancho de banda, no de cuánto tiempo llevas haciendo backups. Los agujeros siguen siendo agujeros, así que una imagen sparse se restaura sparse, y una celda que aparece en varios lugares de la imagen se descarga una sola vez.

**Cada snapshot se sostiene por sí solo.** No hay un "backup completo" que no debas perder ni una ventana donde un incremento roto invalide los siguientes. Cualquier snapshot de la lista es directamente restaurable.

**Verificar es volver a hashear, no confiar.** Como la clave es el hash del contenido, comprobar un backup significa obtener celdas y hashearlas. `rdc backup verify` toma muestras; `rdc backup verify --deep` vuelve a hashear cada celda registrada.

**Una ejecución interrumpida no se pierde.** La subida se reanuda sin reenviar celdas que ya llegaron, y reiniciar una restauración parcial vuelve a hashear lo que ya está en disco y lo reutiliza en lugar de volver a descargarlo.

### Qué te cuesta

La cuota se cuenta en **bytes físicos únicos almacenados**: lo que realmente se conserva tras la deduplicación, no la suma de lo que tus snapshots representan lógicamente. Treinta snapshots de un repositorio que cambia lentamente cuestan casi como uno. `rdc backup usage` muestra los bytes almacenados frente a tu cuota, un número por suscripción que empieza en 10 GB en el plan Community.

### Qué necesitan los snapshots

La subida de un snapshot pasa por el servidor de cuenta, que autoriza cada ejecución contra la licencia instalada del repositorio y le entrega a la máquina un permiso de escritura de corta duración. Así que esta vía necesita un servidor de cuenta que la máquina pueda alcanzar y un repositorio con licencia. Sin ellos, el snapshot se rechaza en lugar de omitirse en silencio, y `rdc backup manifests`, `rdc backup usage` y `rdc backup retention` no tienen nada que leer.

Eso incluye `--dry-run`. La licencia se lee antes de que la ejecución decida si va a planificar o a subir, así que un dry run es una vista previa del trabajo, no una forma de probar el comando sin credenciales.

El push y el pull de máquina a máquina no necesitan ninguna de las dos cosas. Son una transferencia directa entre dos máquinas que ya están en tu configuración.

### Lo que un snapshot no promete

- **Un snapshot cubre un repositorio, no toda tu máquina de una vez.** Cada repositorio se captura en su propio instante. Si dos repositorios dependen entre sí, sus snapshots no forman un par coordinado.
- **No es replicación continua.** Un snapshot es un punto que tomaste, y puedes perder todo lo escrito desde el último. Cuánto sea eso depende de con qué frecuencia lo ejecutes.
- **Los objetos almacenados son de escritura única, no WORM certificado.** Las celdas se escriben con una condición de solo creación, el permiso que obtiene una máquina no puede borrar nada, y las eliminaciones ocurren en el servidor según la política de retención. Eso es una barrera real contra una máquina comprometida que destruye sus propios respaldos. No es una certificación de cumplimiento, y no se audita como tal.

### La vía de almacenamiento con rclone desapareció

`rdc repo push --to <storage>` y sus variantes solían copiar un archivo de respaldo completo a un proveedor compatible con rclone que registrabas tú mismo. Ahora rechazan un destino de almacenamiento y nombran su reemplazo. La transferencia de máquina a máquina nunca pasó por rclone y no se ve afectada. Si aún necesitas leer un archivo escrito de esa forma, consulta [Leer un archivo escrito antes de la retirada](#leer-un-archivo-escrito-antes-de-la-retirada).

### Comandos de almacenamiento fragmentado

```bash
# Subir un snapshot. La primera ejecución siembra los datos; las siguientes envían solo las celdas cambiadas.
rdc backup snapshot my-app

# Planificar sin subir: informa qué se movería.
rdc backup snapshot my-app --dry-run

# Detener los contenedores, congelar, reiniciar, y luego subir.
rdc backup snapshot my-app --cold

# Desconfiar del ancla local y volver a subir todo el inventario.
# Esto vuelve a subir todo y recarga la cuota; úsalo solo cuando
# el ancla sea sabidamente incorrecta.
rdc backup snapshot my-app --reseed

# Comprobar el inventario almacenado y tu cuota.
rdc backup verify my-app
rdc backup manifests my-app
rdc backup usage
```

| Opción | Descripción |
|--------|-------------|
| `<repo-ref>` (posicional) | Repositorio a respaldar con snapshot |
| `--dry-run` | Solo planificar: sin subida. Informa qué se movería |
| `--cold` | Detener los contenedores, congelar, reiniciar, y luego subir. No se puede combinar con `--dry-run` |
| `--reseed` | Desconfiar del ancla local y subir un inventario completo. Vuelve a subir todo y recarga la cuota |
| `--debug` | Habilitar salida detallada |

## Snapshots en Frío (`--cold`)

Un snapshot en frío detiene un repositorio antes de congelarlo, de modo que la imagen almacenada es consistente a nivel de aplicación en lugar de consistente ante fallos. El comando se ejecuta en la propia máquina:

```bash
# Todos los repositorios del datastore por defecto.
sudo renet backup snapshot --cold

# Solo los repositorios que indiques. --repo toma un GUID de repositorio y se puede repetir.
sudo renet backup snapshot --cold --repo <guid> --repo <guid>
```

`--cold` no se puede combinar con `--dry-run`. Una ejecución en seco que detiene contenedores no es en seco, y una que no los detiene no es en frío, así que renet rechaza la pareja en lugar de elegir un significado por ti.

### Qué hace una ejecución en frío

Para cada repositorio seleccionado, en este orden:

1. Detener sus contenedores.
2. Volcar a disco el montaje del repositorio y el datastore.
3. Comprobar que los contenedores se detuvieron de verdad.
4. Tomar un reflink copy-on-write de la imagen del repositorio.
5. Volver a arrancar los contenedores.

Solo entonces empieza la subida, con todos los repositorios ya en marcha.

El tiempo de inactividad es la congelación, no la transferencia. Un reflink es solo metadatos, así que tarda lo mismo tanto si el repositorio guarda 1 GB como 100 GB. Una subida no funciona así: crece con los bytes que cambiaron, y el primer snapshot sube el inventario no vacío entero. Mantener los contenedores parados hasta terminar la subida ataría la inactividad al tamaño de los datos, lo que en la primera copia significa horas en vez de milisegundos.

Todos los repositorios seleccionados se detienen dentro de una sola ventana, no de uno en uno. Eso cuesta algo más de inactividad por repositorio y, a cambio, da un único punto de consistencia para todo el conjunto.

Un repositorio sin contenedores en ejecución ya está en reposo. Se captura sin ninguna inactividad, y eso es un resultado normal, no un fallo.

### Cuánto cuesta la inactividad

Medido en una máquina real, la inactividad total fue de **222 ms**:

| Fase | Medido | Qué ocurre |
|------|--------|------------|
| `cold_down` | 64 ms | Los contenedores se detienen |
| `cold_sync` | 26 ms | Montajes del repositorio y datastore volcados a disco |
| `cold_verify` | 31 ms | Se confirma que los contenedores están parados |
| `cold_stage` | 0 ms | Reflink de la imagen del repositorio |
| `cold_up` | 99 ms | Los contenedores vuelven a arrancar |

Reiniciar los contenedores domina, y la preparación sale prácticamente gratis: el reflink ni siquiera se registra con resolución de milisegundos. Aun así, lee ese cero junto a los registros de cada repositorio y no por separado. Una ejecución que rechazó todos los repositorios también informa `cold_stage=0ms`, y solo los registros dicen cuál de los dos casos estás viendo.

El desglose es la prueba, no un adorno. Ninguna de estas cinco fases lee ni envía datos del repositorio, así que ninguna crece cuando crece la copia. La parte que sí crece, la subida, ocurre cuando la inactividad ya terminó.

renet imprime las mismas cifras al terminar una ejecución, para que midas tus propias máquinas en vez de fiarte de las nuestras:

```text
Cold backup: <n> repositories quiesced, outage 222ms (cold_down=64ms cold_sync=26ms cold_verify=31ms cold_stage=0ms cold_up=99ms)
```

El registro JSON de cada repositorio lleva la misma inactividad y las mismas fases, así que más adelante se distingue un snapshot en frío de uno en caliente sin adivinarlo por los tiempos.

### Cuándo elegir el frío

El modo en caliente es el predeterminado y la opción correcta para la mayoría de los repositorios. Un snapshot en caliente es consistente ante fallos, que es el estado en el que quedaría un repositorio tras un corte de luz, y no cuesta nada de inactividad. La mayoría de las bases de datos y las colas se recuperan solas desde ahí.

Elige el frío para datos que no se pueden capturar con seguridad mientras se escriben. Una base de datos con su propio registro de escritura anticipada y su estado en memoria es el caso claro. Cambias una inactividad corta y medida por un snapshot que la aplicación puede abrir sin recuperarse antes.

### Qué rechaza una ejecución en frío

Rechazar es la función. Una copia etiquetada como en frío que nunca detuvo nada es una mentira que solo descubrirías al restaurar, así que renet nunca degrada en silencio una ejecución en frío a una en caliente:

- **Contenedores que no se detuvieron.** Tras la parada, renet pregunta al socket Docker del propio repositorio si sigue corriendo algo. Si es así, ese repositorio se rechaza en lugar de capturarse. La comprobación falla del lado seguro: si no se puede alcanzar el socket o leer la lista de contenedores, la parada cuenta como no verificada, y lo no verificado se rechaza.
- **Una licencia que no se puede leer.** Las licencias se comprueban antes de la inactividad, no después, porque un repositorio cuya licencia no se puede leer nunca habría podido subir nada. Ese repositorio se omite sin detenerlo. Si ninguno de los repositorios seleccionados tiene una licencia legible, la ejecución entera se rechaza antes de que caiga un solo contenedor.
- **Una segunda ejecución en frío sobre el mismo datastore.** El bloqueo cubre el datastore, y un bloqueo ocupado se rechaza de inmediato, sin haber detenido nada. Dos ejecuciones solapadas pararían cada una contenedores que la otra cree suyos, y la segunda arrancaría repositorios que la primera todavía está congelando. Saltarse la ejecución y esperar a la siguiente es mejor que eso.

Si una ejecución se interrumpe con los contenedores parados, por un `systemctl stop` o un reinicio, renet los vuelve a arrancar antes de salir. La recuperación en la máquina es la red de seguridad: detecta una copia en frío cuyo dueño ha desaparecido y devuelve esos repositorios a su sitio.

## Enviar un Respaldo a Otra Máquina

Copia un repositorio a una segunda máquina por SSH:

```bash
rdc repo push my-app --to server-1
```

`--to <machine>` resuelve el destino desde tu configuración, y `--to-machine <machine>` dice lo mismo explícitamente. Un nombre de almacenamiento se rechaza: esa vía está retirada.

La imagen cifrada se copia con el MISMO GUID, así que esto es un respaldo o una migración, no un fork. Para obtener una copia independiente, ejecuta primero `rdc repo fork` y envía el fork.

El primer envío lleva la imagen completa. Cada envío posterior manda solo los bloques cambiados frente a una imagen base inmutable que se conserva en ambas máquinas, sin flags que ajustar. `--delta-base <guid>` nombra esa base tú mismo si lo necesitas.

La copia enviada aterriza en el destino como un artefacto de respaldo, no como un repositorio en ejecución. Conviértela en uno con `rdc backup restore`:

```bash
rdc backup restore my-app@server-1 --as my-app --machine server-1 --up
```

Para un respaldo puntual, usa almacenamiento fragmentado en su lugar: `rdc backup snapshot my-app` sube solo las celdas que cambiaron, y `rdc backup restore my-app --at <snapshot>` recupera cualquiera de ellas.

| Opción | Descripción |
|--------|-------------|
| `<ref>` (posicional) | Ref del repositorio a enviar |
| `--to <remote>` | Máquina o clúster de destino |
| `--to-machine <machine>` | Máquina de destino, indicada explícitamente |
| `--provision <provider>` | Aprovisionar la máquina destino mediante este proveedor de nube si no existe |
| `--checkpoint` | Crear un checkpoint CRIU antes de enviar (para contenedores con etiqueta `rediacc.checkpoint=true`). El destino se restaura automáticamente con `repo up` |
| `--force` | Sobreescribir un respaldo existente |
| `--bwlimit <limit>` | Límite de ancho de banda para la transferencia rsync (p. ej. `10M`, `500K`) |
| `--delta-base <guid>` | Transferir solo los bloques modificados respecto a esta GUID base inmutable. Omitir para una base automática |
| `--strategy <strategy>` | Estrategia de delta de bloques al usar una base delta: `auto`, `physical` o `shared` |
| `--debug` | Habilitar salida detallada |
| `--skip-router-restart` | Omitir el reinicio del servidor de rutas después de la operación |

## Descargar un Respaldo desde Otra Máquina

Recupera un repositorio desde la máquina que lo aloja:

```bash
rdc repo pull my-app --from server-1
```

Añade `--up` para montarlo y desplegarlo en el mismo comando. Para restaurar desde almacenamiento fragmentado en su lugar, usa `rdc backup restore my-app --at <snapshot-id>`.

Pull se niega a sobrescribir un repositorio que esté **montado** en ese momento. Desmóntalo primero, ejecuta el pull y luego vuelve a levantarlo con `rdc repo up`. Los repositorios basados en directorio son la excepción: se sincronizan en el sitio mientras están montados.

| Opción | Descripción |
|--------|-------------|
| `<ref>` (posicional) | Ref del repositorio a descargar |
| `--from <remote>` | Máquina o clúster de origen |
| `--from-machine <machine>` | Máquina de origen, indicada explícitamente |
| `--force` | Sobreescribir respaldo local existente |
| `--up` | Montar y desplegar el repositorio tras la descarga |
| `--bwlimit <limit>` | Límite de ancho de banda para la transferencia rsync (p. ej. `10M`, `500K`) |
| `--delta-base <guid>` | Recibir solo los bloques modificados respecto a esta GUID base inmutable |
| `--strategy <strategy>` | Estrategia de delta de bloques al usar una base delta: `auto`, `physical` o `shared` |
| `--debug` | Habilitar salida detallada |
| `--skip-router-restart` | Omitir el reinicio del servidor de rutas después de la operación |

## Listar Respaldos

Lista los snapshots en almacenamiento fragmentado:

```bash
rdc backup manifests my-app
```

Cada fila es un punto en el tiempo almacenado:

| Columna | Significado |
|---|---|
| `Repo` | Nombre del repositorio resuelto desde tu configuración local (recurre al GUID para repositorios no presentes en la configuración) |
| `Snapshot` | El id del snapshot. Esto es lo que toma `rdc backup restore --at` |
| `Created` | Hora UTC en que se tomó el snapshot |
| `Total` | Tamaño de la imagen del repositorio que representa este snapshot |
| `Added` | Bytes que este snapshot realmente subió por encima de los anteriores |
| `Chunks` | Cuántas celdas añadió |

Para ver qué dejó un `rdc repo push --to <machine>` en el destino, pregúntale a esa máquina qué tiene:

```bash
rdc repo list --machine server-1
```

La copia enviada aparece bajo su propio nombre. Una segunda fila con un GUID en bruto al lado es la base delta retenida, que es lo que hace incremental en lugar de completo el siguiente envío a esa máquina.

`rdc backup list --machine <machine>` lee las carpetas `hot/` y `cold/` en las que escriben las ejecuciones programadas, así que es la herramienta equivocada para una copia que dejó ahí un envío, y no te mostrará nada.

| Columna | Significado |
|---|---|
| `Mode` | `hot` o `cold`. En qué carpeta de respaldos programados vive esta entrada |
| `Name` | Nombre del repositorio resuelto desde tu configuración local (recurre al GUID para repositorios no presentes en la configuración) |
| `GUID` | El GUID del repositorio en disco |
| `Size` | Tamaño legible del archivo de respaldo |
| `Modified` | Marca de tiempo UTC del archivo en la máquina |

Listar un backend de almacenamiento quedó retirado junto con la rama de rclone; el comando se rechaza y nombra estos dos reemplazos.

## Retención

El servidor aplica una política de retención por repositorio sobre el almacenamiento fragmentado, así que los snapshots antiguos se podan sin que borres nada a mano. Sin política declarada, se conserva cada snapshot.

```bash
# Qué se está aplicando ahora mismo.
rdc backup retention my-app

# Mantener una ventana rotativa: 7 diarios, 4 semanales, 6 mensuales.
rdc backup retention set my-app --keep-daily 7 --keep-weekly 4 --keep-monthly 6

# Volver a conservar todo.
rdc backup retention clear my-app
```

| Opción | Descripción |
|--------|-------------|
| `--keep-last <n>` | Conservar esta cantidad de los snapshots más recientes |
| `--keep-hourly <n>` | Conservar el snapshot más nuevo de cada una de estas horas |
| `--keep-daily <n>` | Conservar el snapshot más nuevo de cada uno de estos días |
| `--keep-weekly <n>` | Conservar el snapshot más nuevo de cada una de estas semanas |
| `--keep-monthly <n>` | Conservar el snapshot más nuevo de cada uno de estos meses |
| `--keep-yearly <n>` | Conservar el snapshot más nuevo de cada uno de estos años |

Da al menos una regla. `set` sin reglas se rechaza en lugar de tratarse como "no conservar nada", porque para eso está `clear`.

## Restaurar

`rdc backup restore` convierte un respaldo en un repositorio en vivo, y es el mismo comando para ambas vías. Lo que cambia es a qué lo apuntas.

```bash
# Un punto en el tiempo desde almacenamiento fragmentado.
rdc backup restore my-app --as my-app-yesterday --at <snapshot-id> --up

# Un artefacto que dejó un envío en una máquina.
rdc backup restore my-app@server-1 --as my-app --machine server-1 --up
```

`--at` toma un id de snapshot de `rdc backup manifests`, o una hora RFC 3339 como `2026-08-14T12:00:00Z`, que se resuelve al snapshot más reciente tomado en ese momento o antes. Una hora sin snapshot en ese momento o antes se rechaza en lugar de redondearse hacia adelante.

Restaurar bajo un nombre nuevo con `--as` no sobrescribe nada, así que un simulacro de restauración es seguro de ejecutar contra una máquina en vivo. Restaurar sobre un nombre que ya existe se rechaza.

| Opción | Descripción |
|--------|-------------|
| `<artifact-ref>` (posicional) | Qué restaurar. `repo` para un snapshot de almacenamiento fragmentado, `repo@place` para un artefacto en una máquina |
| `--as <name>` | Nombre para el repositorio restaurado (por defecto, el nombre del artefacto) |
| `-m, --machine <machine>` | Máquina en la que restaurar |
| `--datastore <name>` | Restaurar en este datastore nombrado, cuya máquina asociada lo aloja |
| `--at <time>` | Restaurar un punto en el tiempo: un id de snapshot o una hora RFC 3339 |
| `--up` | Desplegar el repositorio restaurado después de la transferencia |
| `--health-window <seconds>` | Cuánto tiempo observar la salud del repositorio desplegado |
| `--health-timeout <seconds>` | Cuánto tiempo esperar hasta que esté saludable |
| `-y, --yes` | Omitir la confirmación |
| `--debug` | Habilitar salida detallada |

Restaurar un repositorio necesita su credencial LUKS, que vive en tu configuración. Si tienes el almacenamiento de configuración activado, esa credencial vuelve con tu configuración en una máquina nueva. Si no, conserva una copia de la configuración en algún lugar que la máquina que falla no se lleve consigo.

### Prueba la restauración en cada máquina

Una máquina que nunca ha completado el ciclo completo no está respaldada, por muy verdes que se vean sus subidas. Las subidas y las restauraciones fallan por razones distintas, y el segundo tipo solo se manifiesta cuando lo intentas.

Hazlo una vez por máquina, antes de confiar en los respaldos:

1. Toma un snapshot: `rdc backup snapshot my-app`.
2. Confirma que quedó registrado: `rdc backup manifests my-app`.
3. Restáuralo con un nombre desechable: `rdc backup restore my-app --as my-app-drill --at <snapshot-id>`.
4. Compara el repositorio restaurado contra la fuente, luego borra la copia de prueba con `rdc repo delete my-app-drill --yes`.

Nada en esa secuencia toca el repositorio en vivo, así que es seguro en una máquina que está sirviendo tráfico. Si estás abandonando un esquema de respaldo más antiguo, mantenlo funcionando hasta que esto haya pasado en esa máquina al menos una vez. Dos vías de respaldo cuestan almacenamiento; una vía no probada cuesta los datos.

## Sincronizar un Repositorio a la Vez

Push y pull actúan sobre un único repositorio, identificado por su ref (`name`, `name:tag` o `name@machine`). No existe una forma para «todos los repositorios a la vez»: ejecuta el comando una vez por repositorio.

Un ref que nombra un fork y una máquina funciona igual que un nombre simple:

```bash
rdc repo push shop:nightly@server-1 --to server-2
rdc repo pull shop:nightly@server-1 --from server-2
```

Las listas completas de opciones están en [Enviar un Respaldo a Otra Máquina](#enviar-un-respaldo-a-otra-máquina) y [Descargar un Respaldo desde Otra Máquina](#descargar-un-respaldo-desde-otra-máquina).

## Respaldos Programados

Rediacc utiliza estrategias de respaldo nombradas. Cada estrategia define un cronograma, modo de respaldo, límite de ancho de banda opcional y filtros de archivo. Vincula nombres de estrategia a máquinas para controlar qué respaldos se ejecutan donde.

### Modos de Respaldo

| Modo | Comportamiento | Tiempo de inactividad |
|------|---------------|----------------------|
| `hot` | Imagen del repositorio congelada mientras los servicios siguen en ejecución (consistente ante fallos) | Ninguno |
| `cold` | Servicios detenidos, snapshot tomado, servicios reiniciados, snapshot cargado (consistente a nivel de aplicación) | Ventana de stop+start por repositorio, paralelizada entre repositorios. Véase "Estimación del tiempo de inactividad del respaldo en frío" abajo. |

Usa `hot` para servicios que toleran snapshots consistentes ante fallos. Usa `cold` cuando necesites consistencia garantizada y puedas aceptar un breve reinicio.

### Semántica del Respaldo en Frío

Un respaldo frío ejecuta tres fases por repositorio incluido: **detener - snapshot - iniciar**. Entender los límites de las garantías ayuda a detectar fallos parciales a tiempo.

**Lo que el respaldo frío garantiza:**

- Antes del snapshot, cada contenedor en ejecución en cada repositorio incluido se detiene de forma controlada mediante el hook `down()` del Rediaccfile, y el daemon de Docker por repositorio queda en reposo. El snapshot es por lo tanto consistente a nivel de aplicación, no solo consistente ante fallos.
- El conjunto de IDs de contenedor que estaban en ejecución antes del snapshot se persiste en un archivo sidecar en `/var/run/rediacc/cold-backup-<guid>.running.json`. Esta es la fuente de verdad de "qué debe volver a estar activo cuando terminemos."
- Después del snapshot, se invoca el hook `up()` del Rediaccfile del repositorio para restaurar el stack completo de compose.
- Un archivo sidecar de estado por ejecución en `/var/run/rediacc/cold-backup-<guid>.status.json` registra la fase, resultado y cualquier error de cada intento.

**Lo que el respaldo frío NO garantiza:**

- `up()` es de mejor esfuerzo. Puede fallar por razones fuera del control del respaldo frío (una condición `depends_on: service_healthy` aún esperando, un error de sintaxis en el archivo compose, un fallo de red transitorio al descargar una imagen). Cuando falla, el respaldo frío registra el error a nivel de error, escribe el sidecar de estado y pasa al siguiente repositorio.
- Cuando `up()` falla, se activa un **reinicio directo de respaldo**: se lee el sidecar de ejecución y cada ID de contenedor registrado se reinicia mediante la API de Docker directamente (sin compose). Esto pone los servicios de vuelta en marcha incluso si el flujo de compose tiene un problema, aunque sin volver a ejecutar ningún hook de Rediaccfile.
- Si incluso el respaldo falla para algunos IDs de contenedor (por ejemplo, el propio daemon de Docker está caído), el sidecar se **deja en su lugar** para que el watchdog del router pueda seguir reintentando en cada ciclo.

**Recuperación del Watchdog:** en cada ciclo, el watchdog comprueba si existe un sidecar de ejecución. Cualquier ID de contenedor listado ahí que esté actualmente detenido se reinicia, *independientemente de la `restart_policy` guardada del contenedor*. Esto significa que los servicios con `restart: on-failure` (que Docker NO reiniciaría después de una detención limpia) siguen volviendo después de un respaldo frío. Una vez que todos los contenedores listados estén en ejecución, el sidecar se elimina.

**Cómo detectas fallos:**

- `rdc machine status <machine> --containers` muestra el estado de ejecución. Compáralo con el conjunto esperado.
- `/var/run/rediacc/cold-backup-<guid>.status.json` en la máquina. Inspecciona vía `rdc term connect <repo> -c "cat /var/run/rediacc/cold-backup-$GUID.status.json"`. `success: false` con un `startedAt` obsoleto significa que el último respaldo no se completó correctamente.
- Los registros del respaldo de renet (`journalctl -u renet-*` o la invocación directa `rdc backup schedule`) emiten una línea de resumen final de la forma `Cold backup: post-snapshot restart summary total=N compose_ok=N fallback_ok=N failed=N failed_repos=[...]`. Un `failed_repos` no vacío es el objetivo de grep.

### Estimación del Tiempo de Inactividad del Respaldo en Frío

Cada repositorio solo está inactivo durante su propia ventana `down()` + `up()`. En un host en caliente estos son típicamente:

| Forma del repositorio | Stop+start típico |
|-----------------------|-------------------|
| Pequeño (1-2 contenedores, sin DB) | 5-15 s |
| Mediano (aplicación web + caché) | 20-45 s |
| Pesado (DB + colas + correo) | 60-120 s |

El paso de congelación es un reflink copy-on-write de la imagen del repositorio. Es solo metadatos, así que tarda lo mismo tanto si el repositorio guarda 1 GB como 100 GB, y en una ejecución medida ni siquiera se registró con resolución de milisegundos. Un repositorio no se mantiene detenido mientras se congelan otros repositorios. La subida luego se ejecuta contra la copia congelada mientras todos los repositorios ya están de vuelta.

**El tiempo total de reloj para toda la ejecución** está gobernado por cuántos repositorios reinician simultáneamente. Renet deriva este valor del host:

```text
concurrency = min(repoCount, max(2, NumCPU/2), 8)
```

Ejemplos:

| Host | Repos | Concurrencia | Reinicio en reloj |
|------|-------|--------------|-------------------|
| VM de 4 CPU | 5 repos, promedio 30 s cada uno | 2 | ~75 s |
| Servidor de 16 CPU | 10 repos, promedio 40 s cada uno | 8 | ~80 s |
| Nodo de flota de 64 CPU | 50 repos, promedio 40 s cada uno | 8 | ~4 min |

**Anulación vía variable de entorno:** establece `REDIACC_COLD_BACKUP_CONCURRENCY=N` en el entorno del servicio de respaldo (normalmente mediante un drop-in de systemd) para fijar un valor específico. `=1` fuerza reinicios estrictamente seriales, útil al depurar un bucle de fallos en el hook `up()` de algún repositorio.

Si ejecutas un repositorio sensible a la latencia (aplicación web pública, correo), su tiempo de inactividad está limitado por su propio stop+start (típicamente 30-90 s), no por la duración total de la ejecución. Los repositorios se programan en slots de concurrencia en el orden en que fueron descubiertos; no hay cola de prioridad. Dale a los repositorios pesados su propia estrategia acotada con `--include` si necesitas una planificación más fina.

### Respaldos de Larga Duración y Cronogramas Superpuestos

Un respaldo en frío que dura más que su propio intervalo de cronograma (por ejemplo, una primera siembra de un repositorio de 500 GB sobre un enlace modesto puede legítimamente necesitar más de 24 h, durante las cuales el temporizador nocturno dispara de nuevo) no encola ni lanza una segunda ejecución. La unidad systemd `Type=oneshot` es una sola instancia: cuando el temporizador dispara y el servicio ya está `activating`, systemd fusiona el inicio en el trabajo existente. No se lanza ningún proceso nuevo, no se encola ninguna ejecución para más tarde.

Concretamente, una ejecución que comienza el lunes a las 03:00 UTC y termina el jueves al mediodía:

| Día | Disparo de 03:00 UTC | Resultado |
|-----|---------------------|-----------|
| Lunes | Primer disparo | Comienza la ejecución |
| Martes | Segundo disparo | Descartado silenciosamente (la ejecución previa sigue activa) |
| Miércoles | Tercer disparo | Descartado silenciosamente (la ejecución previa sigue activa) |
| Jueves | La ejecución termina al mediodía | Sin recuperación; la siguiente ejecución es el viernes 03:00 UTC |

La directiva `Persistent=true` del temporizador **no** rescata estos disparos. `Persistent=true` repite disparos que se perdieron porque el temporizador mismo estaba inactivo (sistema apagado, temporizador deshabilitado). Los disparos descartados porque el servicio estaba ocupado se pierden.

Este comportamiento predeterminado es deliberado. Ejecutar dos respaldos en frío en paralelo contra el mismo datastore contendería por la ruta de congelación, la subida, y los sidecars por repositorio en `/var/run/rediacc/cold-backup-<guid>.status.json`. Esperar detrás de una instancia en ejecución es mejor que castigar los mismos datos desde dos direcciones. El bloqueo del datastore lo impone: una segunda ejecución en frío encuentra el bloqueo ocupado y se rechaza rotundamente, sin haber detenido nada.

**Implicación de monitoreo.** Un respaldo colgado (por ejemplo, una subida atascada en un agujero negro de red) descarta silenciosamente cada disparo posterior del temporizador. El planificador no emite alarma. Observa `systemctl show <unit> -p ActiveEnterTimestamp`: si el servicio ha estado `activating` por más tiempo del esperado (por ejemplo, más de 48 h en un temporizador nocturno), investiga.

**Si necesitas que cada disparo programado se ejecute**, cambia el temporizador de `OnCalendar=<cron>` a `OnUnitInactiveSec=<intervalo>`. Eso dispara N horas después de la finalización de la ejecución previa en lugar de en un cronograma de reloj de pared fijo, así las ejecuciones largas no causan descartes. Solo empujan la siguiente ejecución más tarde. La contrapartida es la deriva del cronograma: tu nocturno de 03:00 se convierte en "24 h después de que la última terminó."

### Snapshots, Interrupciones y Espacio en el Pool

Cada envío trabaja a partir de un snapshot momentáneo del datastore, por lo que los datos cargados son consistentes incluso mientras los repositorios siguen escribiendo. Mientras el respaldo se ejecuta, ese snapshot sigue referenciando todos los bloques que comparte con los repositorios activos: las eliminaciones y los [trims](/es/docs/repositories#recuperar-espacio-trim) liberan menos espacio en el pool hasta que el ciclo termina y el snapshot se elimina. El [informe de salud del almacenamiento](/es/docs/monitoring#salud-del-almacenamiento) muestra cuánto espacio están anclando actualmente los snapshots de respaldo.

Las interrupciones son seguras. Detener el servicio (o reiniciar la máquina) hace que el respaldo cancele su transferencia y elimine su snapshot antes de salir; la siguiente ejecución programada continúa donde se quedó, porque las celdas ya almacenadas no se vuelven a subir. Si el proceso se termina de forma tan abrupta que no puede limpiar (corte de energía), el snapshot huérfano es detectado y eliminado automáticamente por el mantenedor de almacenamiento en pocos minutos.

### Definir una Estrategia

La configuración predeterminada es una división en dos estrategias: un flujo hot horario rápido que captura todos los repositorios, y un flujo cold semanal más lento que detiene los contenedores para tomar snapshots consistentes a nivel de aplicación. Ambos escriben en el mismo almacenamiento fragmentado, y los bloques compartidos se almacenan una sola vez en lugar de una por flujo.

```bash
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 20M \
  --enable
```

```bash
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --include shop --include mail \
  --enable
```

`--destination <name>` nombra el destino dentro de la estrategia; es una etiqueta que tú eliges, y describe el almacenamiento fragmentado. `--include` lista los repositorios a respaldar, y repetirlo añade más. Omítelo y la estrategia cubre todos los repositorios del datastore. Los nombres coinciden con el nombre de repositorio de la configuración local (sin `:tag`).

`--exclude` se rechaza para un destino de almacenamiento fragmentado en lugar de descartarse en silencio, porque el `backup snapshot` subyacente selecciona repositorios nombrándolos y no tiene exclusión propia. Respetarlo significaría respaldar repositorios que pediste dejar fuera. Delimita una estrategia con `--include` en su lugar, para que lo que cubre una ejecución programada quede escrito en lugar de inferido.

| Opción | Descripción |
|--------|-------------|
| `<strategy>` (posicional) | Nombre de la estrategia (usado para la vinculación a la máquina) |
| `--destination <name>` | Nombre del destino dentro de la estrategia. Por defecto, el almacenamiento fragmentado |
| `--storage <name>` | Optar por el tipo de destino rclone retirado. Un cronograma que lo use no se puede desplegar |
| `--cron <expression>` | Expresión cron (p. ej. `"0 2 * * *"` para diario a las 2 AM) |
| `--mode <hot\|cold>` | Modo de respaldo |
| `--bwlimit <limit>` | Límite de ancho de banda para cargas (p. ej. `10M`) |
| `--include <repos>` | Repositorios que cubre esta estrategia (repetible) |
| `--exclude <repos>` | Repositorios a omitir (repetible). Se rechaza en un destino de almacenamiento fragmentado |
| `--folder <path>` | Subcarpeta dentro de un bucket rclone. Se rechaza en un destino de almacenamiento fragmentado |
| `--enable` / `--disable` | Habilitar o deshabilitar la estrategia |

### Ver Estrategias

```bash
rdc backup strategy list
rdc backup strategy show weekly-cold
```

### Eliminar una Estrategia

```bash
rdc backup strategy remove weekly-cold
```

### Vincular Estrategias a una Máquina

Una estrategia no vinculada a ninguna máquina nunca se despliega. Vincula una o más a una máquina:

```bash
rdc backup strategy bind hourly-hot --machine hostinger
rdc backup strategy bind weekly-cold --machine hostinger
rdc backup strategy unbind weekly-cold --machine hostinger
```

La vinculación se registra en tu configuración como una lista en la máquina, que es lo que lee `rdc backup schedule` para decidir qué unidades desplegar:

```json
{
  "machines": {
    "hostinger": {
      "backupStrategies": ["hourly-hot", "weekly-cold"]
    }
  }
}
```

> **La vinculación es solo de configuración local.** Definir una estrategia y vincularla a una máquina no afecta a la máquina. Ejecuta `rdc backup schedule -m <machine>` (consulta [Desplegar Cronograma en la Máquina](#desplegar-cronograma-en-la-máquina)) para desplegar los temporizadores systemd, y vuelve a ejecutarlo tras cualquier cambio de estrategia o vinculación.

## Elegir entre Hot y Cold y Filtrado por Repositorio

### Hot vs cold de un vistazo

| | Hot | Cold |
|---|-----|------|
| **Consistencia** | Consistente ante fallos (imagen congelada mientras se ejecuta) | Consistente a nivel de aplicación (detener - snapshot - iniciar) |
| **Tiempo de inactividad** | Ninguno | Ventana stop+start por repositorio (típicamente 5-120 s) |
| **Frecuencia adecuada** | Alta (p. ej. horaria) | Baja (p. ej. diaria o semanal) |
| **Uso típico** | Red de seguridad frecuente | Respaldo programado con consistencia garantizada |

**Hot** es la opción predeterminada correcta para ejecuciones de alta frecuencia. Los servicios siguen en funcionamiento mientras se toma el snapshot, por lo que no hay tiempo de inactividad para tus aplicaciones. El snapshot es consistente ante fallos: es equivalente a lo que obtendrías tras un apagado incorrecto. Para la mayoría de las bases de datos modernas y colas de mensajes, esto es aceptable.

**Cold** es apropiado cuando necesitas un snapshot consistente a nivel de aplicación garantizado y puedes aceptar un breve reinicio por repositorio. Los servicios se detienen antes del snapshot y se reinician antes de que comience la carga, así una carga lenta o fallida nunca prolonga la ventana de tiempo de inactividad. Consulta [Semántica del Respaldo en Frío](#semántica-del-respaldo-en-frío) para el modelo de garantía completo.

Ambos modos escriben en el mismo almacenamiento fragmentado, y el modo trata de cómo se maneja el repositorio mientras la imagen está congelada, no de dónde termina la data. Un repositorio cubierto tanto por un cronograma hot cada hora como por uno cold cada semana almacena las celdas que comparten una sola vez en lugar de dos.

### Delimitar repositorios por estrategia

Una estrategia sin `--include` cubre todos los repositorios del datastore. Repetir `--include` la reduce a los repositorios que nombras, comparados con el nombre de repositorio de la configuración local (sin `:tag`).

```bash
# Estrategia hot: respaldar todo cada hora
rdc backup strategy set hourly-hot \
  --destination rediacc \
  --cron "0 * * * *" \
  --mode hot \
  --bwlimit 6M \
  --enable

# Estrategia cold: semanal, y solo los repositorios que necesitan reposo
rdc backup strategy set weekly-cold \
  --destination rediacc \
  --cron "15 3 * * 0" \
  --mode cold \
  --include shop --include mail \
  --enable
```

### Cuándo mantener un repositorio fuera de la estrategia hot frecuente

Nombra los repositorios que quieres en la ejecución de alta frecuencia, en lugar de dejar que lo tome todo, cuando:

- Un repositorio es grande y **totalmente regenerable** a partir de los datos de origen ya almacenados en el volumen, así cada respaldo horario gasta ancho de banda sin añadir valor de recuperación.
- La ejecución del respaldo superaría su propio intervalo de cronograma a tu velocidad de carga disponible.

**Ejemplo.** Un repositorio `analytics-demo` contiene aproximadamente 114 GB de tablas Postgres derivadas que pueden reconstruirse a partir de dumps CSV en bruto almacenados dentro del mismo volumen. Con un límite de carga de 6 MB/s, un primer snapshot de ese repositorio tarda más de 5 horas. Ejecutarlo cada hora significa que cada ejecución sigue en curso cuando se activa la siguiente, así que cada disparo posterior se descarta silenciosamente (consulta [Respaldos de Larga Duración y Cronogramas Superpuestos](#respaldos-de-larga-duración-y-cronogramas-superpuestos)). Listar los demás repositorios en `hourly-hot` y dejar `analytics-demo` para `weekly-cold` significa que se respalda una vez por semana en lugar de nunca.

> **Si los datos son puramente regenerables**, considera si necesitas respaldarlos en absoluto. Una alternativa es respaldar solo las entradas de origen bruto (los dumps CSV en este ejemplo) y omitir por completo la copia derivada. Un respaldo en frío semanal de las entradas de origen es mucho más pequeño y totalmente suficiente para la recuperación.

Un repositorio que ambas estrategias cubren obtiene snapshots horarios consistentes ante fallos y uno semanal consistente a nivel de aplicación. `rdc backup manifests <repo>` los muestra juntos, y las celdas que comparten se almacenan una sola vez.

## Operaciones de Respaldo

### Desplegar Cronograma en la Máquina

Envía las estrategias vinculadas a una máquina como temporizadores systemd:

```bash
rdc backup schedule -m server-1
rdc backup schedule -m server-1 --dry-run
```

El despliegue es un reconciliador de estado. Lee los archivos de unidad actuales y el estado de systemd en la máquina, los compara con lo que produciría la configuración (SHA-256 por archivo) y solo toca las unidades cuyo contenido realmente cambió. Volver a ejecutarlo sin cambios de configuración es un no-op: sin escrituras, sin `daemon-reload`, sin rotación de temporizadores.

`--dry-run` imprime el plan para cada estrategia (`created`, `updated (service, timer, env)`, `unchanged`, `removed`) sin tocar la máquina. Combínalo con `--debug` para imprimir también los cuerpos de las unidades generadas, con las credenciales redactadas. Una unidad de almacenamiento fragmentado no lleva ninguna de entrada: la máquina se autentica con su propia licencia de repositorio firmada, y el servidor devuelve un permiso de corta duración, así que no se escribe nada sensible en el archivo de unidad.

Si actualmente se está ejecutando una copia de seguridad para una estrategia que estás a punto de actualizar o eliminar, el despliegue falla rápido con una sugerencia de cancelarla o pasar `--force`. Con `--force`, la invocación en ejecución conserva su unidad en memoria y la nueva configuración se aplica en el próximo tick del temporizador, así la copia de seguridad en ejecución nunca se termina.

`--reset-failed` es opt-in. Cuando se pasa, limpia el estado de fallo de systemd en los servicios modificados tras un despliegue exitoso. Desactivado por defecto para que las señales de fallo previas sigan visibles para las alertas.

### Ejecutar un Respaldo Ahora

Ejecuta un respaldo inmediatamente sin esperar el temporizador. Funciona incluso si no se han desplegado temporizadores, usando `systemd-run` para ejecución ad-hoc:

```bash
rdc backup run -m server-1
rdc backup run weekly-cold -m server-1
```

### Ver Estado del Respaldo

Muestra el estado actual de los temporizadores de respaldo y resultados de trabajos recientes:

```bash
rdc backup status -m server-1
rdc backup status hourly-hot -m server-1
```

### Cancelar un Respaldo en Ejecución

```bash
rdc backup cancel -m server-1
rdc backup cancel weekly-cold -m server-1
```

## Migración de Repositorios

Mueve un repositorio de una máquina a otra:

```bash
rdc repo migrate my-app@server-1 --to server-2
```

| Opción | Descripción |
|--------|-------------|
| `<ref>` (posicional) | Ref del repositorio a migrar; su `@machine` indica el origen |
| `--to <place>` | Máquina o clúster de destino |
| `--provision <provider>` | Aprovisionar automáticamente la máquina destino mediante este proveedor de nube (p. ej. `hetzner`, `linode`) |
| `--checkpoint` | Crear un checkpoint CRIU antes de migrar, para que la memoria del proceso también se mueva |
| `--delta-base <guid>` | GUID base inmutable para el delta del cutover. Por defecto, la base de la primera fase |
| `--strategy <strategy>` | Estrategia de delta de bloques para el cutover: `auto`, `physical` o `shared` |
| `--skip-dns` | Omitir la actualización de registros DNS después de la migración |
| `--keep-source` | Conservar las imágenes de origen tras un movimiento exitoso |
| `--bwlimit <limit>` | Límite de ancho de banda para la transferencia (p. ej. `50M`) |

La migración transfiere los datos del repositorio cifrado vía rsync en dos fases: una transferencia masiva mientras el repositorio sigue en ejecución, y luego una breve parada para el delta. La migración **mueve** el repositorio, así que las imágenes de origen se eliminan una vez que el movimiento tiene éxito. Pasa `--keep-source` para conservarlas. Esta es la diferencia entre `repo migrate` y `repo push`: push deja la fuente en ejecución e intacta.

## Leer un Archivo Escrito Antes de la Retirada

`rdc storage` es lo que queda de la rama de rclone, y es de solo lectura. Ya no puede ser un destino de respaldo, pero todavía puede acceder a un archivo que se escribió en uno.

```bash
# Registra un remote que ya tienes configurado para rclone.
rdc storage import rclone.conf
rdc storage list

# Mira qué hay en él. Esto ejecuta el rclone de tu PATH.
rdc storage browse my-storage
```

`import` lee un archivo de configuración rclone y registra los remotes en tu configuración; los tipos compatibles son S3, B2, Google Drive, OneDrive, Mega, Dropbox, Box, Azure Blob y Swift.

**`browse` requiere `rclone` en tu PATH.** Ejecuta el rclone instalado en la máquina donde estás escribiendo; ya no hay una copia integrada. Sin uno, te lo dice y no hace nada más.

Enviar a, descargar desde, listar y restaurar un backend de almacenamiento están retirados; cada uno se rechaza y nombra el comando que lo reemplaza.

## Mejores Prácticas

- Programa snapshots fríos diarios para copias consistentes a nivel de aplicación de datos críticos
- Usa snapshots calientes para ejecuciones de alta frecuencia donde se requiere disponibilidad total
- Prueba las restauraciones periódicamente. `rdc backup restore --as <new-name>` no sobrescribe nada, así que un simulacro es seguro en una máquina en vivo
- Establece una política de retención en lugar de podar a mano, para que la ventana que conservas quede escrita
- Mantén una copia de máquina a máquina además de los snapshots si quieres una copia en hardware que controlas
- Mantén las credenciales seguras; los respaldos están cifrados pero se requiere la credencial LUKS para restaurar
