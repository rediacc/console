---
title: "Java4Shell: nuestra CPU calificaba, nuestro servidor no tenía Java y nuestras plantillas nos enseñaron sobre el pinning"
description: "CVE-2026-114938 necesita una CPU con AVX-512 VBMI y un JDK afectado. Nuestro servidor tenía la CPU, pero cero JVM. El trabajo real estuvo en las plantillas de apps que publicamos, donde un tag fijado había congelado un JDK de 2023."
author: Rediacc
publishedDate: 2026-11-20
category: case-study
tags:
  - security
  - cve
  - java
  - docker
  - case-study
featured: true
language: es
sourceHash: "df1e880f9d6ac549"
sourceCommit: "fca7bdc04b65c873118e8b35ce56fdd0c7c46e1b"
---

> **Resumen.** Java4Shell (CVE-2026-114938) es una escritura fuera de límites en el heap, en el decodificador Base64 compilado por JIT de OpenJDK. Solo se activa en CPU x86-64 con AVX-512 VBMI.
>
> - La CPU de nuestro servidor de producción **tiene los cuatro flags requeridos**. Mirando solo la CPU, parecía expuesto.
> - Una sonda sobre **43 contenedores**, el host y los repositorios detenidos encontró **cero runtimes de Java**. Un control con la misma sonda, buscando `python3`, lo encontró en todos los lugares esperados. No había nada que parchear en el servidor.
> - Las plantillas de apps que publicamos eran otra historia. **Cuatro** de ellas arrancan una JVM. **Tres** usan tags flotantes y ya se habían reconstruido upstream con JDK parcheados el 20 de noviembre.
> - **Una**, Elasticsearch, estaba fijada a `8.11.0`: una imagen de noviembre de 2023 con el JDK incluido `21.0.1`. Elastic aún no tiene una release corregida, así que la plantilla ahora arranca Elasticsearch con el flag de mitigación de Elastic, verificado en un nodo en ejecución.

## Qué se divulgó

El 17 de noviembre, investigadores de Calif publicaron **Java4Shell**, y Oracle y OpenJDK lanzaron arreglos ese mismo día. El bug está en el decodificador Base64 acelerado por hardware de HotSpot: la ruta AVX-512 VBMI maneja mal los últimos caracteres y puede escribir más allá del final de un búfer del heap. Un atacante remoto sin cuenta puede convertir eso en corrupción de memoria y, en la aplicación adecuada, en ejecución de código. El análisis muestra cadenas sin autenticación para varios productos de servidor Java conocidos.

Los detalles que importan para el triaje:

- **Afectado:** OpenJDK 17.0.6 y posteriores, 21, 25 y 27, anteriores a los builds corregidos. Java 8 y Java 11 estándar no están afectados.
- **Corregido:** 17.0.21.1, 21.0.13.1, 25.0.5.1 y 27.0.1.1 (los builds de Temurin llevan `+2`, o `+4` para 27). Un runtime que reporta `17.0.21` sin el `.1` sigue siendo vulnerable.
- **Precondiciones:** una CPU x86-64 con AVX-512 VBMI, un JIT que ya haya compilado el decodificador y una ruta de la aplicación que decodifique Base64 desde una entrada no confiable. ARM no está afectado.
- **Puntuación:** 9,2 en CVSS 4.0, 8,1 en CVSS 3.1. Hay una prueba de concepto independiente pública. Al momento de escribir no se había reportado explotación activa.
- **Mitigación:** arrancar la JVM con `-XX:-UseBASE64Intrinsics`. La otra opción publicada, `-XX:UseAVX=2`, también funciona en x86-64, pero hace que una JVM en ARM se niegue a arrancar.

Nuestra [ronda de parches anterior](/es/blog/patching-nginx2root-and-php-fork-first) terminó con un despliegue fork primero de cuatro apps. Esta terminó mucho antes, y lo interesante es el porqué.

## Paso 1: ¿la CPU califica?

La mayoría de los CVE tienen una precondición de software. Este tiene además una de hardware, y es barata de comprobar:

```bash
rdc term connect hostinger -c "grep -m1 '^flags' /proc/cpuinfo | tr ' ' '\n' | grep -E '^(avx512f|avx512bw|avx512vbmi|bmi2)$'"
# avx512bw avx512f avx512vbmi bmi2
```

Los cuatro. La máquina usa un AMD EPYC 9354P, una CPU de servidor reciente con soporte completo de AVX-512. Si el triaje se hubiera detenido aquí, la respuesta habría sido "expuesto, parchear todo lo que sea Java esta noche".

![Las tres precondiciones: la CPU califica, la comprobación del JDK falla, así que nunca se llega a la ruta de entrada](/img/blog-java4shell-preconditions.svg)

## Paso 2: ¿hay algún Java que parchear?

La CPU es solo un eslabón de la cadena. El segundo eslabón es un JDK afectado, así que la siguiente pregunta fue simple: ¿qué contenedores ejecutan Java?

```bash
for c in $(docker ps --format '{{.Names}}'); do
  docker exec "$c" sh -c 'command -v java && java -version 2>&1 | head -1
    find / -xdev -name libjvm.so 2>/dev/null | head -2'
done
```

Lo ejecutamos con `rdc term connect <repo>@hostinger` para cada repositorio de la máquina. El `find` de `libjvm.so` detecta JVM incluidas dentro de la carpeta de una app y fuera del `PATH`, que es como Elasticsearch, por ejemplo, distribuye su JDK.

El resultado fue vacío. Ningún `java`, ningún `libjvm.so`, en ninguno de los 43 contenedores en ejecución.

Un resultado vacío no prueba nada hasta que la sonda ha demostrado que puede encontrar algo. Así que repetimos el mismo bucle, esta vez buscando `python3`, que sabemos que vive en los contenedores de ERPNext. Encontró Python 3.14 en cada uno de ellos. La sonda funciona: el servidor simplemente no tiene Java.

Revisamos dos lugares más antes de cerrar la pregunta. El host no tenía Java ni `/usr/lib/jvm`. Los repositorios sin nada en ejecución no tenían imágenes de Java en sus daemons de Docker. Uno de ellos tenía un checkout de nuestro propio monorepo, y sus archivos compose mencionaban `cassandra:5.0` y `elasticsearch:8.11.0`. Eso apuntaba al siguiente paso.

## Paso 3: las plantillas que publicamos

Rediacc publica plantillas de apps listas para usar: un `docker-compose.yaml` más un Rediaccfile por app. Un servidor que nosotros no operamos puede desplegarlas. Así que una imagen de Java en una plantilla es exposición para todo cliente con la CPU adecuada, aunque nuestro propio servidor esté limpio.

```bash
git grep -nE "image:\s*(cassandra|neo4j|solr|elasticsearch|keycloak|kafka|jenkins|tomcat|openjdk|eclipse-temurin)"
```

Cuatro plantillas arrancan una JVM. En dos de ellas la configuración de la imagen en el registry ya nombra el JDK. En las otras dos no, así que ejecutamos cada imagen una vez y preguntamos:

```bash
docker run --rm --entrypoint sh cassandra:5.0 -c 'java -version 2>&1 | head -1'
# openjdk version "17.0.21.1" 2026-11-17
```

| Plantilla | Tag en la plantilla | JDK dentro hoy | Estado |
|---|---|---|---|
| Cassandra | `cassandra:5.0` | 17.0.21.1+2 | corregido upstream, reconstruida el 20 nov |
| Neo4j | `neo4j:5-community` | 21.0.13.1+2 | corregido upstream, reconstruida el 20 nov |
| Solr | `solr:9-slim` | 17.0.21.1+2 | corregido upstream, reconstruida el 20 nov |
| Elasticsearch | `elasticsearch:8.11.0` | 21.0.1 (incluido) | **vulnerable**, aún sin release corregida de Elastic |

![Fijado frente a flotante: la imagen fijada de Elasticsearch conservó un JDK de 2023, los tags flotantes se reconstruyeron con el arreglo](/img/blog-java4shell-pinned-vs-floating.svg)

## La lección del pinning, revisada

El post anterior terminó con "fijar tags exactos". Esta ronda añade una nota al pie a esa regla.

Fijar es lo correcto para las apps que operamos y actualizamos a propósito. El pin hace visible la versión en ejecución, y un tag flotante puede apuntar a un arreglo mientras el servidor sigue con una imagen vieja, porque `docker compose up -d` no descarga una imagen que ya tiene.

Para las plantillas que la gente despliega desde cero, el panorama se invierte. Los tres tags mayores flotantes (`5.0`, `5-community`, `9-slim`) recibieron el JDK parcheado tres días después del arreglo, sin ningún cambio de nuestra parte. El único pin exacto, `8.11.0`, congeló Elasticsearch en una imagen construida en noviembre de 2023, con un JDK que ninguna reconstrucción de ese tag va a arreglar.

Así que la regla que conservamos tiene dos mitades. Las apps de producción llevan tags exactos y una actualización deliberada. Las plantillas también llevan pins, porque Elasticsearch y Kibana deben ejecutar la misma versión, pero ahora cada pin de plantilla está listado en nuestro registro de pins, donde los gates de frescura marcan un pin que se queda atrás en vez de dejarlo ahí tres años.

## Paso 4: la mitigación, probada en un nodo real

Elastic anunció que el arreglo llegará como una actualización del JDK incluido en las próximas releases 8.19.26, 9.4.10, 9.5.7 y 9.6.0. Hasta que exista una de ellas, la guía oficial es el flag de la JVM. En la plantilla, eso es una palabra más en `ES_JAVA_OPTS`:

```yaml
environment:
  - "ES_JAVA_OPTS=-Xms${ES_HEAP_SIZE} -Xmx${ES_HEAP_SIZE} -XX:-UseBASE64Intrinsics"
```

![Qué cambia el flag: el JIT conserva el decodificador Java simple en lugar del intrínseco AVX-512](/img/blog-java4shell-intrinsic-flag.svg)

Un flag en un archivo compose es solo una afirmación hasta que la JVM lo confirma. Lo comprobamos dos veces. Primero, el propio JDK incluido, con y sin el flag:

```bash
J=/usr/share/elasticsearch/jdk/bin/java
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = true   {product} {default}
docker run --rm --entrypoint $J elasticsearch:8.11.0 -XX:-UseBASE64Intrinsics -XX:+PrintFlagsFinal -version | grep ' UseBASE64Intrinsics '
#  bool UseBASE64Intrinsics = false  {product} {command line}
```

Después, un clúster real de un solo nodo arrancado con las opciones de la plantilla. Quedó en verde, y su propia API listó el flag entre los argumentos de la JVM:

```bash
curl -s localhost:19200/_nodes/jvm | jq '.nodes[].jvm.input_arguments | map(select(test("BASE64")))'
# ["-XX:-UseBASE64Intrinsics"]
```

## Qué salió mal

**La comprobación de la CPU casi decidió la respuesta.** Es la precondición más visible, toma un solo comando y dijo "expuesto". Solo la segunda comprobación, la de una JVM real, convirtió una emergencia de medianoche en un cambio de plantilla.

**Una suite de pruebas corrió donde no debía.** Para verificar la edición de la plantilla, ejecutamos la suite de ciclo de vida del paquete de plantillas en una estación de trabajo. Esa suite está pensada para un repositorio de Rediacc con licencia, no para un host Docker pelado, y pasó más de diez minutos arrancando otras plantillas. También mostró que una plantilla ajena escribía su secreto generado en su propia carpeta de código fuente, un archivo que nadie querría en un commit. Esa plantilla ahora escribe el secreto fuera del árbol de código, y la suite se niega a arrancar sin el repositorio que necesita.

**No había nada que forkear.** Nuestro paso de seguridad habitual, un fork del repositorio de producción antes de cualquier cambio, no tuvo objetivo esta vez. El cambio vivía en un archivo de plantilla en git, así que la red de seguridad fue un commit revisable y una prueba de arranque en vivo, no un snapshot.

## Las decisiones y por qué

| Opción que teníamos | Lo que elegimos | Por qué |
|---|---|---|
| Tratar la comprobación de la CPU como la respuesta | Buscar una JVM real | La CPU decía expuesto; sin JVM no había nada que explotar. |
| Confiar en una sonda vacía | Ejecutar un control que debe encontrar algo | Un resultado vacío de una sonda rota se ve igual que un servidor limpio. |
| Leer la versión del JDK desde el registry | Ejecutar cada imagen una vez | Dos de las cuatro imágenes no registran la versión del JDK en su configuración. |
| `-XX:UseAVX=2` | `-XX:-UseBASE64Intrinsics` | Más acotado: apaga una rutina, no todas las aceleraciones AVX-512, y una JVM en ARM sigue arrancando. |
| Subir Elasticsearch al 8.19 más reciente ahora | Mantener 8.11.0, añadir el flag y subir cuando salga la release corregida | Las releases más nuevas de hoy todavía incluyen un JDK afectado, y Kibana tiene que moverse en el mismo paso. |
| Pins exactos en todas partes | Pins exactos más un gate de frescura en cada pin de plantilla | Un pin sin alarma congeló un JDK de 2023; el gate conserva el pin y añade la alarma. |

## La checklist que conservamos

1. Comprobar todas las precondiciones, no solo la primera que coincide.
2. Buscar el runtime en sí (`java`, `libjvm.so`), no solo el nombre de un producto.
3. Probar cada sonda vacía con un control.
4. Revisar lo que publicamos, no solo lo que operamos.
5. Leer la versión dentro de la imagen; ejecutar la imagen cuando la configuración no dice nada.
6. Preferir la mitigación más acotada y confirmarla en el proceso en ejecución.
7. Seguir la release corregida del proveedor y quitar la mitigación cuando llegue.

Igual que en la ronda anterior, un agente de IA (Claude Code) hizo el trabajo con `rdc`, con acceso a producción concedido por el operador antes de empezar la sesión. Esta vez producción no cambió en absoluto: cada paso en el servidor fue una lectura, y el único arreglo entró en una plantilla, a través de git, con una prueba en vivo detrás.
