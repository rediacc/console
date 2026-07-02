---
title: >-
  Tu pentesting anual es teatro de cumplimiento. El artículo 21(2)(f) de NIS2
  acaba de convertirlo en un problema.
description: >-
  Evaluación continua de la efectividad, el fork de tiempo constante que la hace
  económica, y el calendario de notificación del artículo 23 que no podrás
  cumplir sin artefactos de calidad forense.
author: Rediacc
publishedDate: 2026-05-09T00:00:00.000Z
category: guide
tags:
  - nis2
  - sre
  - dr-testing
  - efectividad
  - notificacion-incidentes
featured: false
language: es
sourceHash: 0e471ac41759e4cb
sourceCommit: 8062f196566d6ba5f90b084e5484cf722b4bdf16
translatedFrom: en
---

> **Resumen.** La mayoría de los programas de seguridad prueban la recuperación una vez al año, contra un entorno de staging creado a partir de producción en algún momento del verano pasado. Se encarga un pentest contra un entorno que no se parece a producción, se obtiene un informe sin hallazgos graves y se archiva. El artículo 21(2)(f) de NIS2 acaba de introducir una frase en la que los auditores van a apoyarse con fuerza: "políticas y procedimientos para evaluar la eficacia" de las medidas. Anual no es continuo. El staging desactualizado no es el sistema bajo prueba.
>
> - La directiva dice: los apartados 21(2)(e) y (f) juntos exigen recuperación y pruebas de seguridad que funcionen de verdad, bajo demanda, contra producción actual.
> - El coste de hacerlo bien con herramientas de la clase Delphix, Veeam Instant Recovery o Rubrik Live Mount es lo que lleva a la mayoría de los equipos a optar silenciosamente por staging.
> - Cuando un fork de producción tarda siete segundos, la economía cambia. Los ejercicios semanales se vuelven realistas. La efectividad continua se vuelve documentable.
> - El régimen de notificación del artículo 23 (alerta temprana a las 24 horas, notificación a las 72 horas, informe mensual) es imposible de cumplir sin artefactos de calidad forense. Nosotros proporcionamos los artefactos; el SOC, el SIEM y el flujo de presentación ante ENISA siguen siendo tu responsabilidad.

Entra en cualquier equipo SRE de tamaño mediano y haz una pregunta: ¿cuándo fue la última vez que hicisteis una recuperación completa de extremo a extremo, no una verificación de ficheros de backup, sino que levantasteis el sistema recuperado con aplicaciones, bases de datos y configuraciones y validasteis que funciona? La respuesta honesta, en la mayoría de los equipos, es "en el tabletop del año pasado." Después todo el mundo vuelve al trabajo.

El artículo 21(2)(f) de NIS2 introduce una frase en la que los auditores van a apoyarse con fuerza:

> "las políticas y los procedimientos para evaluar la eficacia de las medidas para la gestión de riesgos de ciberseguridad"

No dice "anual." Dice "políticas y procedimientos." Leído junto al artículo 21(2)(e), que exige:

> "la seguridad en la adquisición, el desarrollo y el mantenimiento de sistemas de redes y de información, incluida la gestión y divulgación de las vulnerabilidades"

la obligación es continua, no periódica. La guía de implementación de ENISA de 2024 (Anexo IV del Reglamento de Ejecución (UE) 2024/2690) <!-- nis2-quote-skip: ENISA Implementing Regulation 2024/2690, separate source --> confirma la orientación con frases como "evaluación continua" y "evidencia documentada de pruebas que cubran los entornos de producción actuales, no instantáneas heredadas ni de staging."

Si tu historia de efectividad es "pentest anual contra staging," 2026 va a ser incómodo.

Este artículo está dirigido a responsables SRE, directores de operaciones y los ingenieros de seguridad que ejecutan realmente los ejercicios. Es también el artículo que nombra la palanca que un proveedor establecido usará en cualquier contrapropuesta: servicios de notificación gestionada y conectores SIEM para los plazos del artículo 23. Nosotros no resolvemos eso. Te damos los artefactos. El flujo de notificación, el SOC y el motor de presentación ante ENISA siguen siendo tu responsabilidad.

## Leyendo 21(2)(e) y (f) juntos

El artículo 21 enumera diez medidas mínimas. Dos de ellas tratan sobre cómo se construye y cómo se verifica.

e) **Seguridad en la adquisición, el desarrollo y el mantenimiento**: esta es la medida del lado de la oferta. Cuando aceptas un parche CVE, cuando despliegas un nuevo microservicio, cuando ejecutas una ventana de mantenimiento, el cambio tiene que validarse contra el entorno real al que va dirigido. La guía de ENISA es explícita en que los entornos de staging que difieren de producción en forma de datos, escala, secretos o configuración no satisfacen la obligación de prueba para cambios relevantes desde el punto de vista de la seguridad.

f) **Evaluación de la efectividad**: esta es la medida de verificación. Sean cuales sean los controles que tengas, necesitas políticas y procedimientos para confirmar que realmente funcionan. La expresión "eficacia" está haciendo un trabajo real. Es la diferencia entre "tenemos un backup" (el control existe) y "demostramos que podemos restaurar desde él el martes pasado y el sistema restaurado pasó un smoke test" (el control es efectivo).

Leídos juntos, las dos medidas exigen que los cambios relevantes desde el punto de vista de la seguridad se prueben en entornos equivalentes a producción actuales, y que las pruebas produzcan evidencia de que el cambio funcionó. Anual es demasiado infrecuente. El staging desactualizado es el objetivo equivocado. Una restauración que no se ha validado no es efectiva.

La respuesta tradicional a esta obligación es lo que la mayoría de los equipos ya hace: declarar que staging es similar a producción, ejecutar ejercicios contra staging con una cadencia anual, escribir un runbook que describa lo que sucedería en un incidente real, y esperar que el regulador no haga demasiadas preguntas. Eso funcionó cuando el regulador era la autoridad de protección de datos del RGPD y el incidente era un evento de privacidad. NIS2 pone a un regulador diferente en el asiento (el CSIRT nacional, o el BSI en Alemania, la ANSSI en Francia, la ACN en Italia), y ese regulador está haciendo preguntas operativas.

## La trampa del staging desactualizado

Tres cosas hacen que el staging deje de ser producción cuando la mayoría de los equipos están probando contra él.

**Forma de los datos**: los datos de producción tienen casos extremos de cola larga. El cliente con el campo de notas de 8.000 caracteres, la cuenta heredada con un NULL donde todas las demás filas tienen un valor, la tabla unida que devolvió 12 millones de filas para el tenant que importó todo su historial de CRM. El staging tiene el 1% del volumen de producción y la cola larga no está en la muestra.

**Escala**: una consulta que responde en 50 ms contra 10.000 filas en staging responde en 8 segundos contra 12 millones en producción. Un escenario de pentest que no encuentra una vulnerabilidad de agotamiento en staging la encuentra en producción de inmediato. La forma de la vulnerabilidad depende de la escala de los datos.

**Deriva de configuración**: producción ha acumulado variables de entorno, roles IAM, políticas de red, secretos rotados tres veces, un certificado SSL renovado la semana pasada, un feature flag que se suponía que iba a desactivarse en marzo pero que siguió activo. El staging tiene una copia limpia de la configuración del verano pasado más lo que se añadió para el proyecto más reciente. Las diferencias son exactamente donde se esconden los bugs de seguridad.

Por lo tanto, cuando el parche pasa en staging, la confianza del equipo está mal puesta. Cuando el pentest informa de que staging está limpio, el informe es engañoso. Cuando el ejercicio de recuperación restaura staging correctamente, el equipo no ha validado la recuperación de producción.

Los auditores en 2026 no discuten si staging es suficientemente bueno. Están pidiendo evidencia de pruebas contra producción actual. La evidencia tiene que tener marca de tiempo, tiene que mostrar que el sistema bajo prueba se parecía a producción en el momento de la prueba, y tiene que mostrar que la prueba produjo un resultado.

La mayoría de los equipos no pueden producir esa evidencia hoy, porque el coste de ejecutar ejercicios contra producción actual es prohibitivo con las herramientas tradicionales.

## El coste de hacerlo bien con herramientas tradicionales

El mercado tiene respuestas. Las respuestas son caras.

**Veeam Instant Recovery**: levantar una VM directamente desde un backup, montarla, apuntar una interfaz de red hacia ella. Usado para pruebas de recuperación consistentes con la aplicación. Capaz de probar la recuperación contra un backup reciente; el entorno de staging se convierte en el backup recuperado. Ligero en capacidad porque las lecturas de disco provienen del repositorio de backup. Coste: las licencias de Veeam Data Platform Premium escalan por número de VM, y la prueba de recuperación todavía tiene que ser planificada y operada por un ingeniero. La mayoría de los equipos ejecuta esto una vez al trimestre.

**Rubrik Live Mount**: concepto similar, montaje instantáneo de un snapshot de backup para pruebas. Mejor integración con cargas de trabajo nativas en la nube. El mismo patrón operativo. La misma sobrecarga de ingeniería por prueba.

**Delphix (Perforce DevOps Data)**: virtualiza bases de datos fuente para que dev obtenga clones casi instantáneos. Resuelve el problema de "datos con forma de producción en dev." Solo para bases de datos. No clona servicios de aplicación, configuraciones, secretos ni estado de contenedores. La licencia anual alcanza seis cifras para equipos de mercado medio.

**Tonic.ai, Redgate Test Data Manager**: enmascaran o sintetizan datos para dev y pruebas. Buena solución para la compensación privacidad-realismo. La forma y escala de datos se parecen a prod. Pero estas herramientas clonan los datos, no la pila de aplicación. Úsalas para QA, no para simulacros de seguridad donde la configuración es el bug.

**Construcción personalizada**: tomar un backup en caliente, restaurarlo en un entorno paralelo, ejecutar la prueba, desmontarlo. Conceptualmente posible. Operativamente un esfuerzo de ingeniería de varios días por ejercicio. El equipo hace esto una vez porque se vio obligado, y luego nunca más.

Clonar prod completo, incluyendo el estado de la aplicación, siempre ha significado una de tres cosas. Copiar cada byte (lento, caro a escala). Hacer snapshot de la VM (funciona para IaaS, falla para contenedores y Kubernetes). O virtualizar solo la base de datos. Los tres cuestan más por ejercicio a medida que el entorno crece.

Cuando el coste por prueba escala con el tamaño, los ejercicios se convierten en eventos poco frecuentes. Los eventos poco frecuentes no satisfacen la evaluación continua de la efectividad.

## Qué cambia cuando un fork de producción tarda siete segundos

Rediacc usa reflinks de BTRFS para el forking de repositorios. El mecanismo es copy-on-write a nivel de sistema de archivos: el fork comparte bloques con el padre hasta que cualquiera de los dos escribe nuevos datos, momento en el que solo los bloques modificados divergen. La operación de fork en sí misma es de tiempo constante independientemente del tamaño del repositorio.

En nuestra [entrada sobre la prueba de PocketOS](/es/blog/i-tested-rediacc-against-the-pocketos-incident), hicimos fork de un repositorio de producción de 128 GB en 7,2 segundos de extremo a extremo. El reflink en sí fue de 2,3 segundos. La mayor parte del resto es provisionar un nuevo daemon de Docker, montar el volumen cifrado con LUKS2, y levantar la pila de servicios en una nueva subred de IP loopback.

La forma del fork importa tanto como la velocidad. Un fork de Rediacc es de pila completa. El repositorio forkeado contiene:

- El volumen cifrado con LUKS2 con todos los ficheros de datos y el estado de la base de datos.
- La configuración del daemon de Docker y el estado de los contenedores.
- Los hooks de ciclo de vida del Rediaccfile (`up`, `down`, `info`).
- La subred de IP loopback del repositorio (un `/26` nuevo reservado para el fork).
- El ID de red del repositorio, el socket del daemon y el namespace de montaje.

Lo que no contiene por defecto son los secretos que tus servicios necesitan para comunicarse con SaaS externos (Stripe, relés de correo, claves DKIM, claves de firma de webhooks). Para esos, `rdc repo secret` mantiene las credenciales completamente fuera de la imagen del fork, de modo que las llamadas a SaaS externos desde un fork son explícitas, no heredadas. Consulta [Repositorios](/es/docs/repositories) para el modelo de secretos.

Esta forma, pila completa con manejo explícito de secretos, es lo que hace que el fork sea adecuado como objetivo para las pruebas de seguridad. El fork es el sistema de producción, con los datos de producción actuales, la configuración de producción actual, el estado actual de los contenedores, hace diez segundos. Ese es el sistema contra el que el auditor quiere que estés probando.

Para los casos de uso documentados, consulta [Actualizaciones sin Riesgo](/es/docs/risk-free-upgrades) y [Tutorial: Forking](/es/docs/tutorial-forking).

## Una rutina de efectividad continua que puedes ejecutar semanalmente

A continuación se describe una rutina concreta que satisface los artículos 21(2)(e) y (f) para un repositorio de producción, ejecutable con una cadencia semanal por un único SRE.

**Paso 1**: Fork de producción.

```bash
rdc repo fork --parent prod-app --tag effectiveness-2026w19 -m hostinger
```

El fork se nombra con la semana ISO para que el log de auditoría se lea solo. El repositorio se activa bajo un subdominio del fork (`<service>-fork-effectiveness-2026w19.prod-app.<machine>.<basedomain>`). El certificado wildcard del padre lo cubre. Sin nuevo handshake TLS.

**Paso 2**: Aplicar el parche bajo prueba, en el fork.

```bash
rdc repo up --name prod-app:effectiveness-2026w19 -m hostinger
rdc term connect -m hostinger -r prod-app:effectiveness-2026w19 -c "apt-get install -y openssl=3.5.5-1"
```

La sesión de terminal se ejecuta como el usuario sin privilegios `rediacc` (UID 7111), en un namespace de montaje separado, con `DOCKER_HOST` limitado al socket del daemon del fork. El acceso entre repositorios está bloqueado a nivel de kernel (el fork no puede alcanzar la subred loopback de producción). Consulta [Arquitectura § Aislamiento de Docker](/es/docs/architecture) para el modelo de aislamiento.

**Paso 3**: Ejecutar el smoke test contra el fork.

```bash
curl -fsS https://app-fork-effectiveness-2026w19.prod-app.hostinger.example.com/health
# (aquí va tu smoke test específico del proyecto)
```

**Paso 4**: Ejecutar el ejercicio de restauración. Usar el backup en caliente más reciente de producción, traído a un objetivo alineado con el fork.

```bash
rdc repo backup pull --from offsite-b2 --name prod-app:restore-2026w19 -m hostinger
rdc repo up --name prod-app:restore-2026w19 -m hostinger
# verificar que el fork restaurado responde al mismo smoke test
curl -fsS https://app-fork-restore-2026w19.prod-app.hostinger.example.com/health
```

Esta es la prueba de recuperación que los artículos 21(2)(c) y (f) piden: no "se verificó la integridad del fichero de backup" sino "el sistema recuperado responde a un smoke test."

**Paso 5**: Registrar el resultado en el log de auditoría y luego desmontar.

```bash
rdc audit log --since "1 hour ago" > /tmp/effectiveness-2026w19.json
rdc repo destroy --name prod-app:effectiveness-2026w19 -m hostinger --force
rdc repo destroy --name prod-app:restore-2026w19 -m hostinger --force
```

El log de auditoría captura cada paso (creación del fork, repo up, sesiones de terminal, backup pull, repo destroy). Tiene encadenamiento de hash. `rdc audit verify` en la estación de trabajo del operador confirma que la cadena no ha sido modificada desde que se escribieron los eventos. Consulta [Seguridad de Cuenta § Postura de Seguridad del CLI para Agentes de IA](/es/docs/account-security) para el modelo de auditoría.

El tiempo de reloj de pared total para la rutina, en un repositorio de 128 GB, es inferior a 15 minutos. La mayor parte corresponde al smoke test y al viaje de red de ida y vuelta para el backup pull. Las operaciones de fork en sí mismas son cuestión de segundos.

Un único SRE ejecutando esto una vez a la semana produce 52 registros de efectividad con marca de tiempo y log de auditoría al año. Esa es la forma de evidencia que un auditor está pidiendo.

¿Quieres la historia completa de recuperación? [Estrategia de Backup Cruzado](/es/docs/cross-backup) cubre ejercicios entre máquinas y continentes. [Backup y Restauración](/es/docs/backup-restore) es la introducción. Para un evento de corrupción parcial, consulta [Recuperación en el Tiempo](/es/docs/time-travel-recovery).

## Artículo 23: el calendario de notificación que no puedes cumplir sin artefactos

El artículo 23 de NIS2 es el reloj de notificación de incidentes. Tres plazos:

- **24 horas** desde la toma de conocimiento de un incidente significativo: una alerta temprana al CSIRT nacional o autoridad competente. Indica que el incidente está ocurriendo y proporciona información inicial sobre el impacto transfronterizo.
- **72 horas** desde la toma de conocimiento: una notificación completa del incidente. Incluye evaluación de gravedad, indicadores iniciales de compromiso, tipo de amenaza e impacto conocido.
- **Un mes** desde la notificación: un informe final. Descripción detallada, causa raíz, mitigaciones aplicadas, riesgo continuo.

Este es un reloj apretado. Es también un reloj que corre mientras el incidente sigue en curso. La versión más dolorosa del artículo 23 es aquella en la que el equipo está restaurando servicios, preservando evidencia forense, coordinando con las fuerzas del orden, informando al equipo ejecutivo y redactando la alerta temprana, todo ello en las primeras 24 horas.

Las herramientas de backup estándar fuerzan una elección: restaurar el sistema para recuperar el servicio, o preservar el sistema para investigar. Una vez que restauras desde el backup, la evidencia en vivo del compromiso desaparece. Una vez que congelas el sistema comprometido para investigar, no estás sirviendo a los clientes. Ambas son malas en un plazo del artículo 23.

El mecanismo de fork resuelve la elección. El estado comprometido puede ser forkeado (el repositorio padre se convierte en el snapshot forense) y un fork paralelo puede levantarse desde el backup limpio más reciente para servir tráfico. El fork forense es de solo lectura para análisis. El fork de servicio responde a los clientes. Ambos existen simultáneamente en la misma máquina, compartiendo bloques mediante reflink, que es por qué esto es operativamente asequible.

Concretamente, en un incidente:

```bash
# Instantánea del estado comprometido para análisis forense. El fork es el snapshot.
rdc repo fork --parent prod-app --tag forensic-2026-05-09T14-23Z -m hostinger

# Levantar un fork de servicio desde el último backup limpio. Etiqueta diferente.
rdc repo backup pull --from offsite-b2 --name prod-app:serving-2026-05-09T14-30Z -m hostinger
rdc repo up --name prod-app:serving-2026-05-09T14-30Z -m hostinger
# Cortar el tráfico al nuevo fork de servicio mediante DNS o el servidor de rutas.
```

El fork forense responde a la pregunta del regulador en la hora 60: "muéstrenos el estado exacto de sus sistemas en el momento del compromiso." El fork de servicio responde a la pregunta del cliente. El log de auditoría con 70+ eventos responde a "quién hizo qué, cuándo" de forma encadenada por hash y verificable.

Eso es lo que Rediacc proporciona al operador. Lo que no proporcionamos:

- **El SIEM**. No transmitimos a Splunk, Datadog, Sentinel ni a tu stack propio. El log de auditoría es JSONL local en la estación de trabajo del operador; redirigirlo a un SIEM es el trabajo de integración del operador.
- **El SOC**. No gestionamos una capacidad de detección 24x7. No producimos alertas. No hacemos triaje.
- **La notificación gestionada**. No presentamos el informe ante ENISA. No redactamos la alerta temprana. No coordinamos con el CSIRT nacional en tu nombre.

Esta es la palanca que un proveedor establecido usará contra nosotros. Veeam Data Platform con integraciones de Coveware, Rubrik con su brazo de servicios gestionados, y algunas firmas especializadas en retención de IR (Mandiant, Kroll, S-RM en Europa) venden exactamente la capa operativa que Rediacc no tiene. Pretender lo contrario es el movimiento de marketing que nos mete en problemas. La posición defendible es: Rediacc te da artefactos de calidad forense que esos servicios no pueden producir por sí solos; esos servicios te dan la capa de notificación operativa que Rediacc no puede proporcionar. Son complementarios. Un programa NIS2 necesita ambos.

## Lo que Rediacc no ejecuta por ti

Dos cosas que un SRE debe saber de antemano, antes de decidir si el resto del artículo es de su interés.

**Rediacc no ejecuta pentests**. El fork como objetivo es el entorno, no la capacidad de prueba. Un pentest adversarial real sigue siendo tu red team o tu firma de pruebas contratada (Pentera, Horizon3.ai para autónomo; firmas de consultoría especializadas para el dirigido por personas). Rediacc elimina su excusa de que el entorno de prueba era irreal. No elimina el coste de la prueba.

**Rediacc no escribe tus runbooks**. Los comandos del CLI anteriores son las piezas móviles. Las decisiones sobre cuándo hacer fork, cuándo hacer failover, cómo comunicarse con los clientes, cuándo involucrar a las fuerzas del orden, son decisiones de runbook. Esas todavía necesitan ser redactadas, ejercitadas y actualizadas por tu equipo. El artículo 21(2)(b) de NIS2 (gestión de incidentes) es una obligación de proceso, no de herramientas, y nosotros satisfacemos una parte de ella, no toda.

En el lado de las compras (certificaciones, GRC, el problema del registro de proveedores), consulta el [artículo sobre la cadena de suministro](/es/blog/nis2-supply-chain-self-hosted). En el lado del coste (lo que permanece en el presupuesto una vez que te autoalojas), consulta el [artículo sobre la factura real](/es/blog/nis2-the-real-bill).

La lectura correcta de todo esto: Rediacc es una capa de herramientas, no un programa de seguridad. Elimina excusas y produce evidencia. No ejecuta el programa por ti.

## Lo que un auditor quiere ver en 2026

Tres artefactos. Prodúcelos y la conversación sobre los artículos 21(2)(e) y (f) se acorta.

**Artefacto 1: la cadencia de ejercicios de fork**. Un log con marca de tiempo de ejercicios de efectividad ejecutados con una cadencia semanal o quincenal durante los últimos doce meses en ciclo rotativo. Cada entrada muestra el repositorio padre, la etiqueta del fork, el parche o cambio bajo prueba, el resultado del smoke test y la marca de tiempo del desmontaje. El log de auditoría producido por `rdc audit log --since` captura todo esto.

**Artefacto 2: el log de auditoría de esos ejercicios, encadenado por hash**. La cadena de hash en el log de auditoría es lo que transforma "ejecutamos 47 ejercicios el año pasado" de una afirmación en evidencia. `rdc audit verify` valida la cadena de extremo a extremo. El resultado de la validación es la salida de un único comando que un auditor puede volver a ejecutar.

**Artefacto 3: el rastro de verificación de backups**. Para cada estrategia de backup programada, la unidad systemd produce un archivo sidecar de estado en `/var/run/rediacc/cold-backup-<guid>.status.json` por repositorio y por ejecución, y una línea de log de resumen final. `rdc machine backup status` expone ambos. Combinado con el ejercicio de restauración semanal del Paso 4 de la rutina anterior, esto da al auditor un rastro de "backup tomado y restauración probada," no solo de "backup tomado." Consulta [Monitorización](/es/docs/monitoring) para la superficie de diagnóstico.

Los artefactos juntos responden a la pregunta "¿son efectivos tus controles?" con marcas de tiempo y una cadena de hash. No atestaciones. Evidencia.

## Lo que esto significa para la próxima reunión de planificación trimestral

Si tu equipo está entrando en la planificación del Q3 y el artículo 21(2)(f) está en el backlog de seguridad, tres movimientos concretos:

1. Audita tu historia de efectividad actual. Extrae los últimos doce meses de informes de pentest, ejercicios de recuperación y tickets de validación de parches. Cuenta cuántos de ellos tuvieron producción actual como objetivo. La cuenta honesta suele ser inferior a cinco.
2. Elige un repositorio de producción y ejecuta la rutina semanal anterior contra él durante un mes. La rutina está diseñada para ser operable por un único SRE sin sobrecarga de planificación. Después de cuatro semanas, tienes cuatro registros de efectividad con marca de tiempo; eso es más de lo que la mayoría de los equipos produce en un año.
3. Ten la conversación sobre quién cubre el SIEM, el SOC y el flujo de trabajo de notificación del artículo 23. Si la respuesta es "todavía no hemos llegado a eso," el lugar correcto para empezar no es Rediacc, sino una capacidad de detección 24x7. Somos complementarios a esa conversación; no somos el inicio de ella.

Si quieres ver el tiempo del fork en tu repositorio más grande, la oferta es simple. Ejecútalo en una llamada con nosotros. Si el fork tarda más de diez segundos, no nos debes nada. Si tarda siete, pasaremos el resto de la llamada repasando la rutina en tu stack.

La historia del coste estructural (lo que se elimina del resto del stack de seguridad y lo que permanece en la línea de presupuesto) está en el artículo complementario sobre [la factura real](/es/blog/nis2-the-real-bill). Para el ángulo del registro de proveedores y la contratación, consulta [el artículo 21(2)(d) y el autoalojamiento](/es/blog/nis2-supply-chain-self-hosted).

Para el mapa público de lo que Rediacc hace contra cada artículo de NIS2, consulta [NIS2 y DORA](/es/docs/legal-nis2-dora).
