---
title: "Article 21(2)(d) es una pregunta sobre proveedores. El autoalojamiento es la respuesta que deja de deberse."
description: "Por qué el registro de TIC de terceros se reduce cuando el plano de datos nunca abandona su entorno. Una lectura práctica de NIS2 Article 21(2)(d) para CISOs y responsables de compras que renegocian DPAs en 2026."
author: Rediacc
publishedDate: 2026-05-09
category: guide
tags:
  - nis2
  - supply-chain
  - self-hosted
  - sovereignty
  - compliance
featured: false
language: es
sourceHash: "ffdb86da48dacc58"
sourceCommit: "8062f196566d6ba5f90b084e5484cf722b4bdf16"
translatedFrom: en
---

> **Resumen ejecutivo.** NIS2 Article 21(2)(d) convierte el riesgo de la cadena de suministro en una cuestión de nivel directivo, no en una nota a pie de página del departamento de compras. La directiva no exige el autoalojamiento. Sin embargo, pregunta qué hay en su ruta de datos y qué le ocurre a usted cuando uno de esos proveedores tiene un mal día. La infraestructura autoalojada colapsa tres de las cuatro capas que tiene la ruta de datos SaaS habitual. No las colapsa todas, y pretender lo contrario es el movimiento de marketing que pone a un CISO en una posición difícil ante un auditor.
>
> - El texto de la directiva y las orientaciones de ENISA, en lenguaje claro.
> - Las cuatro capas de la ruta de datos SaaS que la mayoría de los equipos olvida documentar.
> - Lo que el modelo de dos herramientas de Rediacc elimina de su registro de proveedores y lo que deja en él.
> - Una lista de verificación de seis preguntas para cualquier proveedor que afirme ser "compatible con NIS2."

En julio de 2020, Blackbaud pagó un rescate y lo comunicó al mundo después. Notificó a más de 13.000 organizaciones clientes a posteriori, afrontó demandas colectivas en siete jurisdicciones y acabó pagando 49,5 millones de dólares en acuerdos con fiscales generales estatales y una multa de 3 millones de dólares de la SEC por divulgaciones engañosas. Cada una de esas 13.000 organizaciones tenía un Acuerdo de Tratamiento de Datos (DPA) con Blackbaud. La mayoría había revisado el informe SOC 2 de Blackbaud. Muchas tenían a Blackbaud en un registro de riesgo de proveedores, con una clasificación por nivel, una fecha de renovación y un propietario nominado.

Nada de ello detuvo el efecto en cascada. Los datos estaban en el lado de Blackbaud del perímetro. Cuando su entorno de copias de seguridad fue vulnerado, todas las organizaciones clientes quedaron expuestas de forma simultánea.

NIS2 Article 21(2)(d) plantea una pregunta más difícil que "¿auditó a su proveedor?" Pregunta qué hay en la ruta de datos y qué le ocurre a usted cuando ese proveedor tiene un mal día. La respuesta, para la mayoría de los equipos, es: "somos ellos, y no nos habíamos dado cuenta."

Esta entrada está dirigida a CISOs y responsables de compras que renegocian DPAs en 2026. Es la lectura desde la perspectiva de la ruta de datos de Article 21(2)(d), no la lectura desde la perspectiva de las certificaciones. También es honesta sobre lo que la infraestructura autoalojada no resuelve, porque la sección de brechas es lo que un auditor preguntará y lo que un folleto de marketing omitirá.

## Lo que Article 21(2)(d) obliga realmente

El texto de la directiva dice, con una ligera condensación para mayor claridad:

> "Los Estados miembros velarán por que las entidades esenciales e importantes tomen las medidas técnicas, operativas y de organización adecuadas y proporcionadas para gestionar los riesgos que se planteen para la seguridad de los sistemas de redes y de información que utilizan dichas entidades [...] e incluirán al menos los siguientes elementos: [...] d) la seguridad de la cadena de suministro, incluidos los aspectos de seguridad relativos a las relaciones entre cada entidad y sus proveedores o prestadores de servicios directos"

Dos aspectos de ese texto son relevantes para un comprador.

En primer lugar, la obligación recae sobre usted, no sobre el proveedor. Las certificaciones del proveedor, su SOC 2, su ISO 27001, son datos de entrada para su evaluación de riesgos. No son un sustituto de ella. Si su proveedor tiene una postura de cumplimiento perfecta y sufre una brecha de todos modos, la pregunta del regulador versará sobre la gestión de riesgos de sus proveedores, no sobre la de ellos.

En segundo lugar, la obligación va más allá del contrato. Las orientaciones de implementación de ENISA de 2024, el Anexo IV del Reglamento de Ejecución (UE) 2024/2690 de la Comisión, establece la práctica esperada: mantener un registro de proveedores de TIC, clasificarlos por criticidad, evaluar cada uno en cuanto al riesgo para sus operaciones y los datos que tratan, y renovar la evaluación con una cadencia definida. El Anexo IV nombra explícitamente "los proveedores de los proveedores" como parte del ámbito de aplicación, que es donde la mayoría de los equipos descubre que su registro de proveedores no es realmente un registro, sino una lista de contratos con una etiqueta.

Si analiza esto desde el lado de las compras, la traducción práctica es: todo proveedor con acceso lógico a sus datos de producción debe ser enumerado, puntuado, monitorizado y reemplazable. "Reemplazable" es la parte que rompe la mayoría de los acuerdos existentes.

## Las cuatro capas de la ruta de datos SaaS que la mayoría de los equipos olvida documentar

Siéntese con un responsable de compras y analice lo que ocurre cuando el producto de un proveedor de copias de seguridad escribe un único registro. La ruta de datos honesta tiene el siguiente aspecto, de arriba abajo:

1. La **aplicación del proveedor**. El código que ingiere sus datos, toma decisiones de enrutamiento y aplica la lógica de negocio. Se ejecuta en la infraestructura del proveedor. La mantiene, parchea y monitoriza el propio proveedor.
2. La **nube del proveedor**. La región del hiperescalador o el centro de datos propio del proveedor donde se ejecuta la aplicación. Volúmenes de almacenamiento, red, IAM. Con frecuencia un hiperescalador con quien el proveedor tiene un acuerdo de subencargado.
3. La **custodia de claves del proveedor**. Las claves de cifrado que protegen los datos en reposo en la nube del proveedor. En la mayoría de los acuerdos SaaS, es el proveedor quien las tiene. Las "claves gestionadas por el cliente" están a veces disponibles como opción de nivel superior; en esos casos, las claves siguen estando en un KMS del hiperescalador al que el IAM del proveedor puede llamar.
4. Los **subencargados del proveedor**. Los servicios de terceros que utiliza el proveedor (CDN, observabilidad, facturación, herramientas de soporte al cliente) que pueden tener en tránsito o almacenar sus datos, o metadatos derivados de ellos.

Cada una de esas cuatro capas es una entrada en su registro de proveedores de Article 21(2)(d). Cada una tiene su propio historial de incidentes, su propio radio de impacto en caso de brecha, su propia superficie de negociación contractual. Cuando renueva con el proveedor SaaS, renueva las cuatro de forma implícita, porque el contrato del proveedor SaaS es el único que puede negociar.

El incidente de Blackbaud fue una brecha en la capa 2 (nube del proveedor) que se propagó a través de la capa 1 (aplicación del proveedor) y fue visible para todos los clientes debido a la capa 3 (custodia de claves del proveedor; en su caso, claves del lado del servidor sin separación por inquilino en la base de datos afectada). Los subencargados de Blackbaud no fueron el vector de la brecha, pero los clientes descubrieron tres de ellos que no habían enumerado.

## Blackbaud, la custodia de claves al estilo Druva y el patrón en cascada

Tres detalles de los expedientes ante la SEC de Blackbaud son los que importan para una lectura desde la perspectiva de NIS2.

En primer lugar, Blackbaud conservaba las claves de cifrado de los datos de los clientes, incluido el entorno de copias de seguridad que fue el objetivo de la brecha. Las claves gestionadas por el cliente no estaban disponibles. En el litigio ante la SEC posterior al incidente, esto se calificó como una brecha de control, no como una infracción, porque los contratos de Blackbaud lo permitían. La perspectiva de NIS2 sobre el mismo acuerdo, en virtud de Article 21(2)(d), es más exigente, porque el cliente no puede evaluar de forma significativa el riesgo de un control sobre el que no tiene visibilidad.

En segundo lugar, la brecha afectó a datos de copia de seguridad más antiguos que la base de datos en vivo. Las organizaciones clientes cuyos datos en vivo habían sido eliminados de los sistemas primarios de Blackbaud seguían teniendo datos expuestos a través del entorno de copias de seguridad. Este es el patrón en cascada: una vulneración del proveedor alcanza datos históricos que el cliente creía que ya estaban fuera del ámbito de aplicación.

En tercer lugar, más de 13.000 organizaciones clientes recibieron notificaciones de brecha. Muchas de ellas eran pequeñas organizaciones sin ánimo de lucro y centros educativos que no tenían capacidad operativa para responder, ni un plan de recuperación ante desastres, ni un segundo proveedor de copias de seguridad al que hacer conmutación por error. El incidente del proveedor se convirtió, en ese sentido, en su propio incidente.

En el caso de una copia de seguridad SaaS moderna al estilo Druva, la arquitectura es mejor en algunos aspectos (la separación de claves por inquilino es más habitual, BYOK está disponible en niveles superiores), pero la ruta de datos de cuatro capas es la misma. La aplicación del proveedor, la nube del proveedor (normalmente AWS), la custodia de claves (a veces del proveedor, a veces BYOK en el KMS del cliente, a veces híbrida), los subencargados. Una brecha en cualquier capa alcanza a todos los clientes de forma simultánea, porque los datos de todos los clientes están en el mismo lado del perímetro.

Este es el argumento estructural. No es un ataque contra Druva. Druva opera con mayor rigor que Blackbaud. El argumento es que la estructura de cualquier producto de copia de seguridad diseñado como SaaS convierte las brechas de las capas 2 y 3 en una obligación conforme al artículo 21(2)(d) que el cliente no puede cumplir de forma significativa.

## El autoalojamiento colapsa tres de las cuatro capas

Rediacc está construido de forma diferente. La arquitectura completa está documentada en la [página de Arquitectura](/es/docs/architecture), pero la forma relevante para la cadena de suministro son dos binarios que se comunican sobre SSH:

- `rdc` se ejecuta en la estación de trabajo del operador. Lee un archivo de configuración JSON plano (en `~/.config/rediacc/`), se conecta a las máquinas propias del operador sobre SSH y despacha comandos.
- `renet` se ejecuta en el servidor propio del operador, con privilegios de root, y gestiona imágenes de disco cifradas con LUKS2, daemons de Docker aislados y el proxy inverso.

El operador nunca accede a la infraestructura de Rediacc-la-empresa para ejecutar una copia de seguridad, una restauración o un fork. No hay nube de Rediacc-la-empresa en la ruta de datos. La credencial LUKS2 del repositorio se almacena en el archivo de configuración local del operador (modo `0600`), nunca en el servidor, nunca se envía a Rediacc. La ruta de datos tiene el siguiente aspecto:

1. **Estación de trabajo del operador.** Ejecuta `rdc`. Almacena la credencial LUKS2.
2. **Servidor propio del operador.** Ejecuta `renet`. Almacena los repositorios cifrados con LUKS2.
3. **Destino de copia de seguridad propio del operador.** Cualquier almacenamiento compatible con rclone (S3, B2, OneDrive, MinIO on-prem). Recibe los volúmenes cifrados.

No existe una capa 4. Rediacc-la-empresa no es subencargada para ningún operador que no haya optado por el experimental [adaptador Cloud](/es/docs/architecture). Para los operadores autoalojados, la relación con Rediacc-la-empresa es una licencia de software, no un acuerdo de tratamiento de datos.

Este es el argumento de la ruta de datos, y es el argumento correcto con el que liderar en una conversación sobre el registro de proveedores. Un competidor SaaS puede ofrecer claves gestionadas por el cliente (y la mayoría de los modernos lo hacen). Un competidor SaaS no puede ofrecer "no somos un subencargado."

El segundo punto, una vez que el argumento de la ruta de datos está asentado, es la custodia de claves. Con Rediacc, la credencial LUKS2 está en el archivo de configuración del operador, sin más. No existe custodia de claves en garantía, ni servicio de recuperación que Rediacc-la-empresa pueda ejecutar si el operador pierde la credencial. Esta es también la arquitectura recomendada para el [almacén de configuración de conocimiento cero](/es/docs/config-storage), donde la clave de cifrado se deriva en el lado del cliente a partir de una extensión PRF de passkey y el servidor almacena blobs opacos. El servidor no puede leer las claves SSH, las credenciales LUKS2, las direcciones IP ni ninguna configuración en texto claro. Rotar el token de acceso no otorga al servidor lectura retroactiva.

Para Article 21(2)(h) (cifrado), esto importa. Para Article 21(2)(d) (cadena de suministro), importa más, porque elimina la última vía de acceso lógico de Rediacc-la-empresa a los datos del operador.

## Lo que el autoalojamiento no colapsa

El autoalojamiento desplaza la lista de proveedores; no la elimina. Tres aspectos sobre los que un auditor seguirá preguntando:

**1. Sigue teniendo proveedores, simplemente diferentes.** El proveedor de hardware (Hetzner, Hostinger, OVH, su colocation, su propio metal desnudo). El hipervisor (KVM, VMware). El sistema operativo (Debian, Ubuntu, RHEL). El registro de contenedores (Docker Hub, GHCR, su registro privado). Las imágenes base que sus servicios descargan. Cada uno de ellos es una entrada de Article 21(2)(d). El autoalojamiento desplaza la lista de proveedores; no la elimina.

**2. Rediacc todavía no tiene ISO 27001, SOC 2 ni BSI C5.** Están en la hoja de ruta, no disponibles aún. Para un equipo de compras que utiliza las certificaciones como mecanismo de filtrado, esto supone una fricción real. El contraargumento defendible es el que este artículo ha venido desarrollando: el argumento de la ruta de datos implica que la mayor parte de lo que esas certificaciones atestiguan (controles de seguridad de la nube del proveedor, gestión de acceso del personal del proveedor, gestión de subencargados del proveedor) no está en el ámbito de aplicación, porque Rediacc-la-empresa no está en la ruta de datos. Ese argumento debe plantearse con cuidado y solidez, no como sustituto de las certificaciones cuando estas son lo que el comprador necesita.

**3. La capa GRC sigue siendo suya.** Rediacc proporciona al operador un registro de auditoría con cadena de hash de más de 70 eventos (`rdc audit verify` valida la cadena de extremo a extremo). No le proporciona un registro de proveedores, un marco de controles ni un flujo de trabajo de recopilación de evidencias. Eso sigue viniendo de Drata, Vanta, OneTrust o uno de los competidores europeos. La entrada complementaria sobre [el coste real](/es/blog/nis2-the-real-bill) cubre en detalle la estructura de costes de esa complementariedad.

## El DPA que ya no tiene que negociar

Para concretar esto, aquí hay una fila de registro "antes frente a después" de una conversación real de compras, anonimizada. El comprador es una empresa alemana de fabricación con 280 empleados, clasificada como "entidad importante" del Anexo II. Su entrada original en el registro de proveedores para copias de seguridad era la siguiente:

| Campo | Antes |
|---|---|
| Proveedor | Acme Backup SaaS |
| Nivel | Crítico |
| Datos tratados | Base de datos de producción, datos personales de clientes, registros financieros |
| Subencargados | AWS (eu-central-1), Datadog, Stripe, Zendesk |
| Estado del contrato | DPA firmado en 2023, SCCs adjuntas, anexo de medidas revisado por última vez en enero de 2025 |
| Custodia de claves | Gestionada por el proveedor (opción BYOK no disponible en el nivel actual) |
| Plan de salida | "El proveedor se compromete a facilitar la exportación de datos en CSV en un plazo de 30 días desde la resolución" |
| Última evaluación | 2025-T1, brecha detectada en custodia de claves, diferida a la renovación |

Tras migrar a Rediacc en Hetzner:

| Campo | Después |
|---|---|
| Proveedores | (1) Rediacc OÜ, licencia de software; (2) Hetzner, IaaS |
| Nivel | (1) No crítico (sin plano de datos); (2) Crítico (plano de datos, pero controlado por el cliente) |
| Datos tratados | (1) Ninguno; (2) Volúmenes cifrados, el cliente conserva las claves |
| Subencargados | (1) Ninguno para autoalojado; (2) Solo internos de Hetzner, listados en su DPA |
| Estado del contrato | (1) Licencia de software, no se necesita DPA; (2) DPA de Hetzner + SCCs ya en vigor |
| Custodia de claves | Cliente (credencial LUKS2 en la configuración del operador, no en el servidor) |
| Plan de salida | "rdc repo backup pull desde cualquier destino compatible con rclone. Los volúmenes están cifrados con LUKS2; el operador conserva la credencial." |
| Última evaluación | (2) cubierta por la revisión IaaS existente |

Dos entradas en el registro en lugar de una. La entrada de nivel crítico corresponde al proveedor IaaS, para quien el comprador ya tenía un DPA en vigor y un plan de salida probado, porque IaaS es una relación que la mayoría de los equipos sabe gestionar. La entrada de Rediacc es no crítica porque es una licencia de software, no un procesador de datos.

Esta es la razón estructural por la que un CISO acaba queriendo menos dependencias SaaS en el plano de datos, aunque el coste de adquisición parezca similar en una hoja de cálculo. La entrada del registro no tiene la misma forma.

## Lista de verificación para compras

Para cualquier proveedor que afirme ser "compatible con NIS2" en un ciclo de ventas de 2026, seis preguntas:

**1. ¿Dónde está la clave de cifrado de nuestros datos en reposo?** Si la respuesta es "en nuestro HSM" o "en el KMS de nuestro cliente al que podemos llamar vía IAM," el proveedor está en su cadena de custodia de claves. Si es "en su archivo de configuración local, nunca en nuestra infraestructura," no lo está.

**2. ¿Quién en su empresa puede leer técnicamente nuestros datos, con independencia de los términos legales?** No "quién está autorizado a hacerlo" sino "quién podría, si quisiera y el registro de auditoría estuviera desactivado." Si la respuesta es distinta de cero, esa es su población para una evaluación de riesgo interno.

**3. ¿Se prueba la restauración contra un clon real de producción o contra datos de prueba sintéticos?** Article 21(2)(c) y (e) leídos conjuntamente exigen que la copia de seguridad restaure realmente. Un proveedor que solo valida contra datos sintéticos no está validando la recuperación, sino la integridad del archivo de copia de seguridad. (Para más información, consulte la entrada complementaria sobre [evaluación continua de eficacia](/es/blog/nis2-effectiveness-without-theatre).)

**4. ¿Registra su registro de auditoría el tipo de actor, humano o agente, detrás de cada acción?** La actividad de agentes de IA es la categoría de mayor crecimiento en los registros de auditoría. Un registro de auditoría de 2026 que no distinga humano de agente parecerá una brecha en 2027.

**5. Enumere todos los subencargados que tienen acceso lógico a nuestros datos, incluidos los metadatos.** "Acceso lógico" es la expresión correcta. "Acceso lógico incluidos los metadatos" es la mejor, porque el acceso solo a metadatos es lo que habitualmente tienen los subencargados de facturación, observabilidad y soporte al cliente, y es suficiente para filtrar información estructural sensible aunque la carga útil esté cifrada.

**6. ¿Cuál es su plan de salida si son adquiridos por un comprador no europeo en 2027?** El marco de adecuación del RGPD, la Cloud Act y la FISA 702 son objetivos en movimiento. La afirmación de residencia de datos de un proveedor hoy no es una garantía en tres años. La pregunta del comprador es qué ocurre con la ruta de datos si cambia la titularidad del proveedor.

Un proveedor que responde limpiamente a las seis preguntas es inusual. Un proveedor que responde a cuatro de seis y reconoce abiertamente las otras dos es más fiable que uno que responde a las seis con confianza. La señal de credibilidad es la disposición a nombrar lo que no está resuelto.

## Lo que esto significa para el próximo ciclo de renovación

Si vas a afrontar una renovación de backup o recuperación ante desastres en los próximos doce meses y el Article 21(2)(d) está en el baremo de compras, tres pasos concretos:

1. Dibuja en una pizarra la ruta de datos de cuatro capas de tu proveedor actual. Si no sabes nombrar el tercer subencargado en la cadena, tienes un problema de exhaustividad del registro que es anterior a NIS2 y la renovación es el momento de corregirlo.
2. Aplica la lista de seis preguntas anterior a tu proveedor actual. Envía las respuestas a tu DPO y a tu auditor y pregunta si las brechas son asumibles. Si las brechas incluyen la capa 3 (custodia de claves) o la capa 4 (subencargados que no habías enumerado), ahí está la palanca.
3. Mira cómo sería un registro de proveedores alternativo con un plano de control autoalojado. Compara las entradas del registro, no los costes de licencia. Los costes de licencia son similares, dentro de un factor de dos; las entradas del registro tienen formas distintas. (La entrada complementaria sobre [el coste estructural de la pila NIS2](/es/blog/nis2-the-real-bill) detalla lo que se colapsa y lo que permanece.)

Si somos la alternativa en tu lista corta, la oferta es concreta. Envíanos tu cuestionario de proveedores. Lo completaremos contra una instancia desplegada, con nuestras respuestas reales a tus preguntas, incluidas las brechas. Si quieres revisar la arquitectura antes de enviar la documentación, reservaremos una revisión de arquitectura de 30 minutos con nuestro equipo de ingeniería. El camino hacia una entrada de registro defendible no es un folleto brillante. Son las respuestas, incluidas las incómodas.

¿Quiere el mapa de Rediacc artículo por artículo? Consulte [NIS2 y DORA](/es/docs/legal-nis2-dora). ¿Necesita el marco más amplio? Lea [Resumen de cumplimiento](/es/docs/legal-overview). Para la residencia de datos, consulte [Soberanía de datos](/es/docs/legal-data-sovereignty). Para entender por qué el autoalojamiento importa, consulte [On-Premise](/es/docs/on-premise).
