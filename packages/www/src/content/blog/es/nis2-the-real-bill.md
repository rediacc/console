---
title: "Lo que nos dijeron los compradores en el primer ciclo de auditorías NIS2"
description: "Las cinco herramientas del stack de cumplimiento que las entidades esenciales mid-market ensamblan silenciosamente en 2026, lo que consolida un plano de control self-hosted y las partidas presupuestarias que siguen siendo tuyas de todos modos."
author: Muhammed Fatih Bayraktar
publishedDate: 2026-05-09
category: guide
tags:
  - nis2
  - guia-comprador
  - cumplimiento
  - coste
  - mid-market
featured: false
language: es
sourceHash: "3fbb581ec14e3f80"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
translatedFrom: en
---

En diciembre de 2025, el BSI alemán emitió 47 notificaciones formales a entidades que consideraba dentro del alcance de NIS2 pero no registradas. ANSSI en Francia inició un ejercicio paralelo. ACN en Italia comenzó a perseguir aproximadamente 2.000 entidades que consideraba sin registrar. La primera oleada de entidades esenciales e importantes del segmento mid-market entró en su primer ciclo de auditorías NIS2.

Desde entonces hemos hablado por llamada con unas treinta de ellas. Sectores distintos, tamaños distintos, principalmente Alemania e Italia con un puñado de Países Bajos y Estonia. Las conversaciones riman. Cada equipo tiene un proveedor de backup, un plan de DR que puede o no haber sido probado, una historia sobre staging que es verdad a medias, y un presupuesto de adquisición aprobado antes de que NIS2 apareciera en ninguna presentación.

Esta entrada es la versión estructural de esas conversaciones. Lo que un CFO o un comprador tiene que firmar realmente en 2026, lo que cambia un plano de control self-hosted en la factura, y cómo es el coste residual honesto. Deliberadamente no es una calculadora TCO. Los compradores con los que hablamos no necesitan otra hoja de cálculo; necesitan un mapa estructural de a dónde va el dinero y qué partidas se solapan.

Si quieres el argumento de riesgo en la cadena de suministro detrás de la afirmación "el self-hosting importa", consulta el [post complementario sobre el artículo 21(2)(d)](/es/blog/nis2-supply-chain-self-hosted). Si quieres el argumento a nivel SRE sobre por qué las pruebas de penetración anuales ya no son suficientes, consulta el [post complementario sobre efectividad continua](/es/blog/nis2-effectiveness-without-theatre). Esta entrada se sitúa entre ambos, en la conversación presupuestaria.

## El número macro, y lo que significa y lo que no

El estudio de 2024 de Frontier Economics para la Comisión Europea situó el coste anual directo del cumplimiento de NIS2 en toda la UE en 31.200 millones de EUR. La cifra se cita ampliamente; también se malinterpreta ampliamente.

Los 31.200 millones de EUR se reparten entre aproximadamente 160.000 entidades esenciales e importantes. Por organización, la media se sitúa en el rango de 150.000 a 250.000 EUR, con el sector y el tamaño explicando la mayor parte de la varianza. Una entidad esencial mid-market de 250 empleados en fabricación o sanidad está en el extremo superior de ese rango. Una entidad importante de 60 empleados en un sector menos intensivo en datos está en el extremo inferior.

La propia guía de costes de implementación de ENISA (Anexo IV del Reglamento de Ejecución (UE) 2024/2690) es coherente con el número de Frontier pero lo desglosa de forma diferente: aproximadamente un 35-45 por ciento en herramientas, un 30-40 por ciento en personal y formación, un 15-20 por ciento en certificación y auditoría, un 5-10 por ciento en contratos de respuesta a incidentes y servicios gestionados.

Lo que esto significa para un CFO que firma el presupuesto de 2026: la capa de herramientas es aproximadamente de 50.000 a 120.000 EUR al año para mid-market, dependiendo de lo que ya esté en marcha. Esa capa de herramientas es la que vamos a recorrer.

Lo que no significa: que comprar un bundle listo para NIS2 resuelva el problema. Los presupuestos de formación de personal y certificación son mayores que el presupuesto de herramientas para la mayoría de los equipos, y ningún proveedor de herramientas los reduce. Una propuesta de vendedor que afirme una reducción del 50 por ciento en costes NIS2 casi siempre hace los cálculos contra la línea exclusiva de herramientas, no contra el coste total del programa.

## El stack de cinco herramientas que los equipos mid-market ensamblaron silenciosamente

A lo largo de las treinta conversaciones con compradores, el stack tiene el mismo aspecto en el 90 por ciento de los casos. Cinco categorías, con uno o dos proveedores nombrados por categoría. Las etiquetas de categoría son estables; las elecciones de proveedor varían.

**1. Proveedor de backup.** Veeam Data Platform Foundation o Premium es la respuesta modal. Cohesity DataProtect, Rubrik Security Cloud, Commvault, Acronis Cyber Protect en el extremo más pequeño. Coste anual en el rango de 15.000 a 60.000 EUR para mid-market. Normalmente la partida presupuestaria más antigua; precede a NIS2 por años.

**2. Sitio de DR o DR-as-a-service.** Ya sea una región cloud secundaria con un runbook, una tenencia de Veeam Cloud Connect o Rubrik Cloud Vault, o un contrato con un proveedor de DR gestionado. Coste anual de 8.000 a 35.000 EUR. Rara vez se prueba en la práctica; el runbook suele ser más aspiracional que operativo.

**3. Herramienta de datos de prueba o enmascaramiento de datos.** Delphix (ahora Perforce DevOps Data) es el estándar enterprise. Tonic.ai, Redgate Test Data Manager, ocasionalmente un script rsync-y-enmascaramiento construido a medida. Coste anual de 25.000 a 90.000 EUR para las opciones con licencia. La mayoría de los equipos en nuestras llamadas no tienen esta partida presupuestaria; tienen lo que esperan que sea un staging suficientemente bueno. La conversación de auditoría del artículo 21(2)(e) es lo que lo pone en el presupuesto.

**4. Contrato de prueba de penetración.** Un contrato de retención con una empresa de pruebas de seguridad o una plataforma autónoma como Pentera o Horizon3.ai. Coste anual de 15.000 a 50.000 EUR para las herramientas autónomas, de 20.000 a 80.000 EUR para los compromisos dirigidos por humanos. La mayoría de los equipos tienen esto. La mayoría lo hace una o dos veces al año.

**5. Plataforma GRC.** Drata, Vanta, OneTrust, AuditBoard, Hyperproof, DataGuard, Kertos. A veces una hoja de cálculo propia para los equipos más pequeños. Coste anual de 12.000 a 60.000 EUR. Se usa para el registro de proveedores, la atestación del marco de controles, la recopilación de evidencias y (cada vez más) el soporte de auditoría SOC 2 o ISO 27001.

Cinco partidas presupuestarias, de tres a cinco proveedores nombrados, normalmente de 75.000 a 295.000 EUR al año antes de personal y formación. La varianza es amplia pero la estructura es consistente.

Los cinco contratos a menudo no se comunican entre sí. Los registros de auditoría no están unificados. Los planes de salida se redactan por separado. Las revisiones de proveedores se hacen por separado, a veces por diferentes responsables de adquisiciones. Esta es la forma estructural que NIS2 hace incómoda.

## Dónde están los solapamientos

Cada categoría del stack se solapa con al menos otra.

**Backup se solapa con DR.** Los proveedores de backup modernos afirman todos ser capaces de DR. Veeam Data Platform con Cloud Connect es un producto de DR. Rubrik con Cloud Vault es un producto de DR. Las dos partidas presupuestarias a menudo pagan por capacidades adyacentes en el mismo proveedor. Los compradores que no consolidaron las partidas históricamente tenían razones operativas (equipos separados, SLAs separados); bajo la expectativa de NIS2 de "fuente única de verdad para la recuperación", la justificación se debilita.

**Backup se solapa con datos de prueba.** Veeam Instant Recovery, Rubrik Live Mount, Cohesity SmartFiles ofrecen todos alguna forma de backup montable para pruebas. No son sustitutos completos de Delphix (la capa de enmascaramiento es separada, la integración de base de datos es menos profunda) pero para muchos casos de uso de datos de prueba la herramienta de backup es la mitad de la respuesta. La mayoría de los equipos no lo saben.

**La prueba de penetración se solapa con las pruebas autónomas.** La prueba de penetración humana basada en retención y las pruebas continuas al estilo Pentera a veces se presentan como alternativas, a veces como complementos. En la práctica, un comprador con ambas paga dos veces por capacidades adyacentes. Un comprador sin ninguna tiene una brecha en el artículo 21(2)(f).

**GRC se solapa con todo.** Drata afirma integración con backup, DR, identidad, gestión de vulnerabilidades, formación y respuesta a incidentes. Las integraciones varían en profundidad. Una plataforma GRC con integración superficial a una herramienta de backup produce evidencia de cumplimiento que no es lo mismo que la evidencia propia de la herramienta de backup; los auditores comienzan a preguntar cuál es la canónica.

Los solapamientos no son un desperdicio. Son la consecuencia de un stack ensamblado durante una década, antes de que NIS2 hiciera estructural la pregunta de consolidación.

## Dónde están las brechas

Las brechas son más interesantes que los solapamientos, porque las brechas son lo que NIS2 saca a la luz.

**Validación de parches contra datos reales de producción.** Ninguna de las cinco categorías hace esto bien. Las herramientas de backup montan el backup; el entorno montado es el backup recuperado, no la producción actual. Las herramientas de datos de prueba enmascaran datos de producción; el entorno enmascarado es realista en forma pero pierde los deltas de configuración. Los contratos de prueba de penetración prueban lo que se les apunta, que es staging en el 90 por ciento de los casos. La brecha entre "tenemos herramientas" y "podemos probar un parche CVE contra un entorno equivalente a producción actual en menos de una hora" es real y estructural.

**Evaluación de efectividad continua.** La cadencia anual es lo que hacen la mayoría de los equipos. El artículo 21(2)(f) quiere algo más frecuente. Ninguna de las cinco categorías produce evidencia semanal o quincenal por defecto. El comprador o bien realiza simulacros personalizados (poco frecuente, caro) o acepta la cadencia anual y espera que el auditor la acepte (cada vez más, no lo hace).

**Colapso del registro de cadena de suministro.** Cada uno de los cinco proveedores es su propia entrada de registro. Cada uno lleva su propio DPA, SCC, lista de subprocesadores y plan de salida. El registro tiene cinco entradas de nivel 1 antes de que se añadan herramientas de formación de personal, herramientas de identidad, herramientas de observabilidad e IaaS. La conversación sobre la cadena de suministro, en términos de NIS2, es una conversación de gestión del registro tanto como una conversación de seguridad. (Consulta el [post sobre cadena de suministro](/es/blog/nis2-supply-chain-self-hosted) para el argumento estructural.)

**Flujo de trabajo de notificación del artículo 23.** La advertencia temprana de 24 horas, la notificación de 72 horas y el informe de un mes no los produce automáticamente ninguna de las cinco categorías. Requieren un SIEM, un SOC (propio o externalizado) y una persona que sepa presentar ante el CSIRT nacional. Los equipos más pequeños a menudo no tienen esto. El primer incidente es la experiencia de aprendizaje dolorosa.

## Lo que Rediacc consolida

Rediacc es un plano de control con un registro de auditoría unificado, que reemplaza la capacidad central de cuatro de las cinco categorías para infraestructura self-hosted.

**Backup** funciona en dos modos. El modo en caliente es un snapshot BTRFS consistente con el crash, sin tiempo de inactividad. El modo en frío realiza un ciclo stop-snapshot-start. Ambos se programan con temporizadores systemd. Ambos envían a múltiples destinos vía rclone. Los volúmenes están cifrados con LUKS. El operador tiene la clave. Rediacc-la-empresa nunca ve texto plano. Consulta [Backup y Restauración](/es/docs/backup-restore) y [Estrategia de Backup Cruzado](/es/docs/cross-backup).

**DR**: mismo primitivo que el backup, más `rdc repo migrate` para el movimiento de datos entre máquinas, más el primitivo de fork para la puesta en marcha rápida del estado recuperado en una máquina paralela. El sitio de DR puede ser otra máquina Hetzner, una máquina OVH, un rack on-prem, cualquier lugar al que llegue SSH. Ninguna nube de proveedor de DR en la ruta de datos.

**Datos de prueba y clonación de stack completo** funciona con reflink de BTRFS. El fork es de tiempo constante, sin importar el tamaño del repositorio. Stack completo significa datos, configuraciones, contenedores y servicios. Hicimos fork de un repositorio de 128 GB en 7,2 segundos en nuestra [prueba PocketOS](/es/blog/i-tested-rediacc-against-the-pocketos-incident). El fork es la producción actual, no una copia de staging reducida. Consulta [Actualizaciones Sin Riesgo](/es/docs/risk-free-upgrades).

**Restauración instantánea**: `rdc repo backup pull` desde cualquier destino rclone a un fork nuevo, puesto en marcha bajo un subdominio específico del fork cubierto por el certificado wildcard del repositorio padre. Sin confusión de DNS, sin baile de certificados.

**Registro de auditoría unificado.** Más de 70 tipos de eventos en todo el plano de control. Cubren inicios de sesión, tokens de API, escrituras de configuración, ciclo de vida del repositorio, backup, sincronización, sesiones de terminal y operaciones de máquina. La cadena está enlazada por hash en la estación de trabajo del operador. `rdc audit verify` la comprueba de extremo a extremo.

Para una entidad esencial mid-market de 250 empleados, la consolidación pasa de cuatro proveedores nombrados (backup, DR, datos de prueba, restauración instantánea) a uno. Una licencia, un registro de auditoría, un conjunto de decisiones de actualización, una entrada de registro.

La quinta categoría, GRC, no se consolida. Volvemos a eso.

## Lo que sigue siendo tuyo de todos modos

Esta es la sección que determina si el resto de la entrada es honesta. La tabla de dos columnas:

| Eliminado por Rediacc | Sigue siendo tuyo, partida por partida |
|---|---|
| Licencia del proveedor de backup | Plataforma GRC (Drata, Vanta, OneTrust, AuditBoard, DataGuard) para el registro de proveedores, atestación del marco de controles, recopilación de evidencias y soporte de auditoría SOC 2 o ISO 27001 |
| Contrato del sitio de DR o tenencia de DR-as-a-service | Costes de auditoría de certificación (ISO 27001, SOC 2, BSI C5 si los necesitas; Rediacc no está certificada aún, por lo que ese coste lo asumes mientras tanto) |
| Licencia de herramienta de datos de prueba o enmascaramiento | Presupuesto de formación de personal y concienciación en seguridad (NIS2 artículo 21(2)(g)) |
| Licencia de recuperación instantánea en el proveedor de backup | Solución corporativa de MFA más amplia; Rediacc tiene TOTP en el portal, no una plataforma corporativa de MFA |
| | Contrato de prueba de penetración o plataforma de pruebas autónomas; Rediacc proporciona el entorno objetivo, no la capacidad de prueba |
| | SIEM y SOC para la detección y notificación del artículo 23; Rediacc proporciona artefactos de grado forense, no la capa de notificación operativa |
| | Proveedor de IaaS (Hetzner, OVH, tu colo, tu bare metal); Rediacc se ejecuta sobre la infraestructura, no en lugar de ella |
| | Personal que gestiona el programa. Rediacc es una capa de herramientas, no un equipo de seguridad |

El lado derecho de la tabla es más largo que el izquierdo. Esa es la forma honesta de lo que cuesta NIS2. Eliminar el solapamiento de backup-y-DR-y-datos-de-prueba ahorra dinero real y entradas de registro reales; no convierte un programa de seguridad en una suscripción SaaS.

Un comprador que lea esto y concluya "puedo reemplazar Drata con Rediacc" va a decepcionar a su auditor. La lectura correcta es: la consolidación del proveedor de plano de datos que Rediacc permite es lo que las herramientas GRC no pueden hacer, y el trabajo de registro y evidencias que hacen las herramientas GRC es lo que Rediacc no hace. Los dos son complementarios.

Tres enlaces más si quieres profundizar. El mapeado público está en [NIS2 y DORA](/es/docs/legal-nis2-dora). El marco más amplio está en [Visión General de Cumplimiento](/es/docs/legal-overview). El lado comercial de Rediacc está en [Suscripción y Licencias](/es/docs/subscription-licensing).

## Un escenario de referencia, estructural no numérico

Tomemos una empresa manufacturera alemana de 250 empleados. Clasificación de "entidad importante" del Annex II. Datos de producción en 4 a 6 servidores, principalmente self-hosted con una o dos herramientas SaaS (CRM, nóminas). Ingresos anuales de 80 millones de EUR. Equipo de seguridad existente de 3 personas.

**Antes**, su stack de plano de datos:

- Veeam Data Platform Foundation, 24.000 EUR/año
- Veeam Cloud Connect para DR, 12.000 EUR/año
- Un esquema rsync-más-pg_dump propio para datos de prueba, gratuito en licencia pero cuesta al SRE medio día cada dos semanas
- Prueba de penetración anual, 22.000 EUR
- Drata para GRC, 18.000 EUR/año

Cinco contratos. Dos de ellos (Veeam, Veeam Cloud Connect) son con el mismo proveedor pero SKUs diferentes. Las partidas del plano de datos totalizan 36.000 EUR/año antes de contar la prueba de penetración o GRC. El equipo produce una prueba de recuperación anual, ninguna evidencia de efectividad continua, y un registro de proveedores con cinco entradas solo en el lado del plano de datos.

**Después**, con Rediacc en Hetzner para las cargas de trabajo self-hosted:

- Rediacc Business tier, 8.400 EUR/año (cubre el tamaño de sus repositorios)
- IaaS de Hetzner para primario y secundario, 9.600 EUR/año combinados (ya en el presupuesto; ninguna partida nueva)
- El contrato de prueba de penetración se mantiene (22.000 EUR)
- Drata se mantiene (18.000 EUR)
- El esquema propio de datos de prueba se retira; el medio día del SRE cada dos semanas pasa a ejecutar la rutina de efectividad semanal

Consolidación del plano de datos: 5 partidas a 1 (Rediacc) más la línea de IaaS existente. La sección del plano de datos del registro de proveedores pasa de 5 entradas a 2. La historia de efectividad continua son ahora simulacros semanales con evidencia de registro de auditoría encadenado por hash; la historia de la prueba de recuperación está ahora respaldada por la salida de `rdc machine backup status` y un simulacro de restauración por semana.

Los números son ilustrativos, no promesas. Tu stack es diferente. La forma, de cuatro a cinco partidas colapsando en una más la IaaS existente, es como se ve una conversación real con un comprador.

## Una nota sobre lo que esto no es

Esta entrada no es un ataque a Veeam ni una calculadora TCO. Veeam tiene la mayor cuota de mercado de backup de VM en Europa por buenas razones; su producto es maduro, su red de partners es amplia, su marketing NIS2 es sólido, y un comprador que elige Veeam en 2026 no está cometiendo un error. Los números del escenario de referencia son ilustrativos, extraídos de conversaciones reales con compradores, no benchmarks. Ejecuta el análisis estructural contra tus propios contratos.

Lo que esto es: un enfoque desde el lado del comprador para un CFO que está renegociando un contrato de backup, DR o cumplimiento en los próximos doce meses y quiere saber qué cambia un plano de control self-hosted en las partidas presupuestarias.

## Qué hacer a continuación

Si te diriges a un ciclo de renovación y el presupuesto está abierto, tres movimientos concretos:

1. **Extrae las tres mayores partidas de seguridad e infraestructura del año pasado.** Envíalas a tu DPO, a tu CISO y a tu auditor. Pregunta cuáles ya eran redundantes antes de que NIS2 lo hiciera visible. La mayoría de los equipos encuentran al menos un solapamiento por el que han estado pagando.
2. **Mapea tu stack de plano de datos actual contra la lista de cinco categorías anterior.** Anota qué categorías tienen un proveedor, cuáles tienen dos y cuáles no tienen ninguno. Las celdas "ninguno" son las brechas que NIS2 va a sacar a la luz.
3. **Ejecuta el ejercicio del registro de proveedores del [post sobre cadena de suministro](/es/blog/nis2-supply-chain-self-hosted)** para cada proveedor de plano de datos. Cuenta las entradas del registro. El número suele ser mayor de lo que el equipo esperaba.

Si estamos en la lista corta, la oferta es concreta. Envía tus tres mayores partidas del presupuesto de seguridad e infraestructura del año pasado. Te diremos cuáles se pueden consolidar y cuáles no, por escrito, en una semana. La respuesta incluirá las brechas, porque nombrar las brechas es lo que hace que el resto de la respuesta sea de confianza.

Tres documentos más si quieres profundizar. [Backup de coste cero](/es/docs/zero-cost-backup) explica por qué funcionamos más ligero en almacenamiento que los incumbentes. [Estrategia de Backup Cruzado](/es/docs/cross-backup) cubre el DR intercontinental. [Suscripción y Licencias](/es/docs/subscription-licensing) es el lado comercial.
