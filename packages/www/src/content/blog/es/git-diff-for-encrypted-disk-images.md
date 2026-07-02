---
title: 'git diff para imágenes de disco cifradas: comparando forks sin descifrarlos'
description: >-
  rdc repo diff compara imágenes cifradas a nivel de bloque y reporta A/M/D/R.
  Sin tocar ninguna clave. El coste escala con los bloques modificados, no con
  el tamaño del repositorio.
author: Rediacc
publishedDate: 2026-05-28T00:00:00.000Z
category: guide
tags:
  - luks
  - btrfs
  - ext4
  - fiemap
  - cli
featured: false
language: es
sourceHash: 1b08ca130594e2e4
sourceCommit: 8062f196566d6ba5f90b084e5484cf722b4bdf16
---

> **Resumen.** `rdc repo diff` muestra la diferencia a nivel de archivo entre dos repositorios forkeados en gramática de `git status --short` (A/M/D/R), y nunca descifra ninguno de ellos.
>
> - Compara los dos archivos de imagen LUKS a nivel de bloque con el ioctl FIEMAP, que solo lee metadatos del mapa de extensiones. No se carga ninguna clave, no se lee ningún texto en claro.
> - aes-xts preserva la longitud y cifra cada sector de 512 bytes de forma independiente, de modo que un sector de texto plano modificado se convierte en un sector de texto cifrado modificado en el mismo desplazamiento (desplazado por los 16 MiB del desplazamiento de datos LUKS). Resta el desplazamiento, mapea los rangos del dispositivo a nombres de archivo a través del mapa de extensiones de ext4, y obtienes una lista de archivos.
> - El coste escala con el número de bloques modificados, no con el tamaño del repositorio. Un fork de 1 GB y uno de 100 GB producen el diff en los mismos milisegundos, porque la comparación es solo de metadatos.

Entonces, un fork en Rediacc es `cp --reflink=always` de la imagen LUKS de un repositorio. Instantáneo, y no le importa el tamaño. Un repositorio de 100 GB se forkea tan rápido como uno de 1 GB. Sé que suena a marketing, pero así funcionan los reflinks: btrfs copia el mapa de extensiones y comparte los bloques por debajo. Dependemos mucho de esto. Los forks son el sandbox de pruebas, la rama desechable, la copia de staging que eliminas cuando terminas.

Lo que no teníamos era una respuesta barata a la pregunta obvia: qué cambió realmente este fork. La ruta ingenua: montar el fork, desbloquear el contenedor LUKS, recorrer el ext4 interno, hashear cada archivo contra el padre. Eso escala con el tamaño del repositorio tanto en lecturas como en descifrado. Necesita las claves activas en la ruta del diff. Y descarta lo único que la capa de almacenamiento ya sabe de forma gratuita: qué bloques divergieron. `rdc repo diff` toma la otra ruta. Escala con los bloques modificados. No carga ninguna clave. Obtiene su lista de archivos comparando las dos imágenes cifradas.

## La pila que estás comparando

Déjame ser preciso sobre lo que "dos repositorios" significa en disco. Todo el truco depende de ello. De abajo hacia arriba: un SSD, el almacenamiento del host, un pool btrfs. Encima de eso, un archivo de imagen LUKS2 por repositorio. Desbloquéalo y obtienes un dispositivo dm-crypt. Dentro vive el sistema de archivos ext4 que usan los contenedores. Un repositorio es un archivo en el pool btrfs.

Un fork es un reflink de ese archivo. Justo después del fork, los dos archivos de imagen son idénticos byte a byte. Comparten cada bloque físico. El padre y el fork no son dos copias de los datos. Son dos mapas de extensiones que apuntan a los mismos bloques. Cuando escribes dentro del fork, la capa de almacenamiento asigna un bloque nuevo para la región modificada. Solo se reescribe el mapa de extensiones de ese fork. Los bloques del padre permanecen intactos.

Por lo tanto, "comparar dos repositorios" se reduce a "comparar dos archivos que comparten la mayoría de sus extensiones". El kernel ya puede responder eso. Nadie necesita leer un solo byte de ninguno de los dos archivos.

## FIEMAP: preguntarle al kernel qué cambió sin leerlo

El ioctl FIEMAP devuelve el mapa de extensiones de un archivo: una lista de tuplas (desplazamiento lógico, desplazamiento físico, longitud). Cada tupla indica dónde vive una parte del archivo en disco. Son metadatos puros del sistema de archivos. No lee datos del archivo. Para una imagen cifrada no necesita ninguna clave. El texto cifrado son solo bytes que el kernel nunca tiene que interpretar.

Compara los dos mapas de extensiones. Cualquier rango lógico donde ambos forks apuntan al mismo bloque físico está compartido. Compartido significa idéntico, porque literalmente es el mismo bloque en el dispositivo. Los rangos donde el fork tiene su propio bloque privado son las escrituras. Esos son los bloques modificados. Los obtuvimos de metadatos que la capa de almacenamiento mantiene de todos modos.

Aquí es de donde viene la historia del coste. La comparación FIEMAP lee registros de extensiones, no datos. Su trabajo escala con cuántas extensiones cambiaron, no con el tamaño del repositorio. El fork de 1 GB y el de 100 GB devuelven la misma lista corta de extensiones privadas. Los mismos milisegundos, si cambiaron los mismos archivos. Advertencia honesta: el tiempo de recorrido de extensiones escala con la fragmentación de la imagen, no con el tamaño. Un recorrido completo de `filefrag` tardó 3,19 segundos en la imagen de producción más fragmentada que medí. Consulta el post sobre el benchmark de fragmentación. Ese es el techo del lado de los metadatos. Es un escaneo en segundo plano, no una lectura de datos.

## De un bloque modificado a un nombre de archivo, a través de dos capas cifradas

Una lista de rangos de bytes modificados en la imagen cifrada no es útil todavía. Los rangos son posiciones en el texto cifrado. Los nombres que quieres están dos capas más arriba, en el ext4 interno. El puente entre ellos es aritmética de direcciones, no descifrado.

LUKS cifra con aes-xts. Preserva la longitud y cifra cada sector de 512 bytes por separado. Un sector de texto plano modificado produce un sector de texto cifrado modificado en el mismo desplazamiento. El único desplazamiento es el desplazamiento de datos LUKS. Son los 16 MiB de cabecera y ranuras de claves al frente de la carga cifrada. Resta ese desplazamiento de cada rango de imagen modificado. Ahora tienes el rango correspondiente en el dispositivo dm-crypt. Ese es el dispositivo de bloques sobre el que descansa el ext4 interno. No se usó ninguna clave. Es una resta.

Ahora mapea los rangos del dispositivo a archivos. ext4 también mantiene un mapa de extensiones por inodo. La misma estructura (lógico, físico, longitud). Lo alcanzas a través de FIEMAP en el sistema de archivos interno montado. Recorre los inodos una vez para construir un índice bloque-a-archivo. Luego busca cada rango de dispositivo modificado en ese índice. Un rango que se solapa con las extensiones de datos del inodo 1234 pertenece a la ruta de ese inodo. Esa ruta es el archivo que cambió.

Permíteme decir claramente lo que esto nunca hace. Nunca deriva texto plano de la imagen modificada. Lee estructura del sistema de archivos en desplazamientos conocidos. Lo hace tanto en el lado cifrado como en el descifrado. Luego une los dos por dirección. El filtro de bloques dice qué regiones del dispositivo se movieron. El mapa de extensiones de ext4 dice qué archivo posee cada región. Ninguno de los dos pasos inspecciona el contenido de un bloque modificado para decidir que cambió.

## Adiciones, borrados y renombrados: el recorrido de identidad por inodo

Las modificaciones se desprenden directamente de la comparación de bloques. Las adiciones, borrados y renombrados necesitan una observación más. El reflink nos la da de forma gratuita: un fork preserva los números de inodo. Hacer reflink de toda la imagen clona el sistema de archivos interno byte a byte antes de que nada diverja. Por lo tanto, un inodo que existía en el padre tiene el mismo número en el fork.

Eso convierte la identidad en una comparación de conjuntos. Un inodo en ambos lados con una ruta diferente es un renombrado. Un inodo solo en el lado nuevo es una adición. Un inodo solo en el lado antiguo es un borrado. Un renombrado se confirma por solapamiento de extensiones del dispositivo. Los bloques de datos del archivo renombrado están en los mismos desplazamientos del dispositivo en ambos forks. Los dos forks comparten un sistema de coordenadas. Ese solapamiento también descarta que un número de inodo se reutilice para datos no relacionados. Un renombrado puro entonces aparece con los bloques de datos del archivo sin cambios. Solo se movió la entrada del directorio.

Aquí está el formulario de estado de nombre predeterminado, la misma gramática A/M/D/R que ya lees en `git status --short`:

```
$ rdc repo diff --name test-1gb:fork1 -m hostinger
M  hello.txt

1 file changed: 0 added, 1 modified, 0 deleted, 0 renamed
```

Un archivo modificado en un repositorio de 1 GB. Reportado desde una comparación de bloques que no leyó ningún dato de archivo. Nada fue desbloqueado.

El predeterminado hace una cosa más para la corrección. El filtro de bloques es un superconjunto. Una extensión de btrfs puede cubrir más bytes de los que realmente cambiaron. Por lo tanto, una escritura en un archivo puede marcar a un vecino que comparte una extensión. Para evitar reportar un archivo que no cambió, el predeterminado confirma cada candidato marcado por bloques. Hashea solo ese archivo en ambos lados. Hashea los candidatos, no el repositorio. Por lo tanto, el coste de confirmación todavía escala con el conjunto de cambios. `--fast` confía en el filtro de bloques y omite la confirmación. Úsalo cuando quieras la respuesta rápida y toleres algún falso positivo ocasional.

## Por qué un agente de IA necesita esto

La razón por la que este comando existe en absoluto es el flujo de trabajo del agente. Estuve viendo continuamente cómo los agentes forkeaban producción, ejecutaban cambios y luego no tenían una forma clara de reportar qué habían tocado realmente. Un agente de IA puede forkear producción instantáneamente. Ejecuta un cambio arriesgado dentro del fork aislado. Luego necesita saber exactamente qué tocó antes de promover cualquier cosa de vuelta. El fork es la rama. El diff es la revisión.

El agente no lee el estado de nombre, lee `--json`:

```
$ rdc repo diff --name prod:experiment --json -m hostinger
```

La salida estructurada le da al agente un conjunto de cambios preciso. Qué rutas modificó, creó, borró. Con `--stat`, el tamaño del cambio por archivo en bytes y bloques. Un agente que ve su diff antes de promover es uno al que puedes dejar cerca de producción. El radio de explosión es inspeccionable, no afirmado. Otros modos sirven el mismo bucle de revisión. `--name-only` para una lista de rutas simple. `--content <ruta>` para un diff unificado de texto de un archivo (solo texto; un archivo binario reporta `Binary files differ`). `--stat` cuando el agente necesita saber qué cambió y cuánto.

## Por qué las pruebas de DR necesitan esto

El mismo primitivo responde una pregunta de DR que antes era incómoda de hacer sin riesgo. Forkea producción. Restaura un backup en el fork. Compara el fork contra producción. El diff te dice si la restauración reprodujo el conjunto de archivos que esperabas. Lo hace sin bajar producción. Y nunca descifra nada en la ruta del diff.

Ese es un ensayo que puedes ejecutar de forma programada. La restauración aterriza en un fork aislado. El diff reporta el delta en gramática de git. Un ensayo limpio: el conjunto modificado coincide con lo que se suponía que contenía el backup. Estás validando la recuperación contra producción en vivo. La copia no cuesta nada hacerla y nada desecharla.

## Límites honestos

El diff de contenido es solo texto. `--content` produce un diff unificado para archivos de texto. Para todo lo demás reporta `Binary files differ`, del mismo modo que git. Un diff orientado a líneas de un blob cifrado y luego comprimido es ruido.

Compara forks relacionados, no repositorios arbitrarios. Todo el mecanismo descansa en un sistema de coordenadas compartido. Las extensiones compartidas prueban igualdad. Los números de inodo preservados anclan la identidad. Un desplazamiento de datos común lo une todo. Dos repositorios que nunca fueron forkeados de un ancestro común no comparten nada de eso. No hay un diff barato entre ellos. Esto es una característica, no un defecto. Del mismo modo que `git diff` entre dos historiales no relacionados no tiene sentido.

La detección de renombrados se basa en inodos. Es exacta para los renombrados que el sistema de archivos registra realmente como renombrados. ¿Un borrar-y-crear de contenido idéntico con un nuevo nombre? Dos operaciones en la tabla de inodos. Por lo tanto, reporta como un borrado y una adición, no un renombrado. La heurística de similitud de contenido de git llamaría a eso un renombrado. El recorrido de inodos no lo hará. Esa es la respuesta correcta sobre lo que hizo el sistema de archivos. Aunque no sea la respuesta sobre lo que pretendía un humano.

Y el recorrido de metadatos escala con la fragmentación. En una imagen muy fragmentada la enumeración de extensiones es de segundos, no milisegundos. Sigue siendo independiente del tamaño del repositorio. Sigue siendo libre de cualquier lectura de datos. Pero no es literalmente instantáneo en las imágenes más fragmentadas.

## La conclusión

`rdc repo diff` pone ergonomía de control de versiones en infraestructura cifrada en ejecución. La interfaz es deliberadamente como git. A/M/D/R, diffs unificados, `--stat`. Nada nuevo que aprender. Si puedes leer `git status --short`, puedes leer un diff entre dos imágenes LUKS. La ingeniería debajo es la parte que vale la pena cuidar. Se reduce a dos negativas. Nunca descifra. aes-xts permite que una comparación FIEMAP a nivel de bloque localice cada sector modificado por dirección. Y nunca paga por datos que no cambiaron. La capa de almacenamiento ya registró qué bloques divergieron. El fork es la rama. El diff es la revisión. La revisión cuesta lo que cuesta el cambio, no lo que pesa el repositorio.
