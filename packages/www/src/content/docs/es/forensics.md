---
title: "Análisis forense: evidencia desde dentro de un repositorio comprometido"
description: "Registros de flujos de red y de aperturas de archivos sensibles por repositorio, con el nivel de detalle que elige el cliente, enviados cada 30 segundos como lotes firmados y encadenados. Cubre los tres niveles de captura, el disparador de picos, las cuotas del plan, la detección sin conexión y en el servidor, y qué puede leer el servidor."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 9
language: es
sourceHash: "c349f479d246dee4"
sourceCommit: "0531ce955ea0d1658b8fceefd6aa44e3c270521c"
---

# Análisis forense

El análisis forense responde a dos preguntas cuando el software que se ejecuta dentro de un repositorio ha sido comprometido: cuándo se sacaron datos y cuáles fueron. Rediacc no puede cerrar un agujero en software de terceros, así que la función registra evidencia que sobrevive al compromiso. Los registros los escribe un recolector con permisos de root en la máquina, fuera del sandbox del repositorio, y se envían a un bucket al que los administradores del cliente no tienen acceso.

Los registros muestran volumen, destino y momento. Los registros de flujo prueban volumen y destino, no contenido. El [flujo de trabajo de incidentes](/es/docs/incident-response) los lee, y los [informes de incidentes](/es/docs/incident-reports) los convierten en documentos firmados para un regulador.

## Qué se registra

La captura es por repositorio. Los repositorios usan la red del host, por lo que el tráfico se atribuye por cgroup (el slice propio del repositorio), nunca por dirección IP.

| Registro | Contenido |
|---|---|
| Flujo de red | Hora, proceso, dirección y puerto de destino, protocolo, bytes enviados y recibidos, nombre DNS si se conoce, y ASN y país del destino si se conocen |
| Apertura de archivo | Hora, proceso y ruta, para una ruta que coincide con la lista de rutas sensibles |
| Latido | Una marca firmada en cada lote, de modo que un recolector detenido se ve como un hueco y no como silencio |

La lista sensible por defecto abarca archivos `.env`, archivos de claves y certificados (`*.pem`, `*.key`, `id_rsa*`, `id_ed25519*`), bases de datos de contraseñas (`*.kdbx`), volcados y archivos de bases de datos (`*.sql`, `*.dump`, `*.bak`, `*.sqlite*`) y directorios de datos de bases de datos como `pgdata`. Un repositorio puede ampliar la lista o sustituirla por sus propios patrones.

Nunca se registran el contenido de los paquetes ni el contenido de los archivos.

## Niveles de captura

Cada repositorio tiene un único nivel, y el más bajo es el predeterminado. Un nivel superior registra todo lo que registra uno inferior.

| Nivel | Registrado |
|---|---|
| `basic` | Un resumen cada 5 minutos por destino, puerto y protocolo, con bytes de entrada y salida |
| `standard` | Un registro de flujo cada minuto, con proceso y nombre DNS |
| `full` | Standard, más aperturas de archivos en rutas sensibles |

El nivel se establece por repositorio:

```bash
rdc forensics level mail basic
rdc forensics level mail standard
rdc forensics level mail full
```

El recolector limita el nivel a lo que incluye el plan. Cuando un plan no tiene cuota forense, el repositorio no registra nada.

### El disparador de picos

Todos los niveles arman un disparador. Cuando los bytes salientes de un repositorio en un minuto superan diez veces su propia media móvil (y los 50 MiB por minuto), una vez que el repositorio lleva 24 horas observado, el repositorio pasa a Full durante 24 horas. Un minuto que dispara no alimenta la media, de modo que una exfiltración no puede elevar la línea base que debería detectar la siguiente.

## Planes y cuotas

El análisis forense es para planes de pago y solo registra mientras el plan está pagado. Una mejora de plan empieza sin historial.

| Plan | Cuota forense |
|---|---|
| Free, Community | 0 (no se registra nada) |
| Professional | 25 GB |
| Business | 125 GB |
| Enterprise | 512 GB, o una cuota personalizada fijada por los administradores de Rediacc |

La cuota es una cuarta parte de la cuota de copias de seguridad del plan y se contabiliza aparte de estas. Más cuota solo se obtiene con una mejora de plan.

Cuando la cuota se llena, se expulsan primero los registros más antiguos (FIFO). Los últimos 7 días están bloqueados y nunca se expulsan, porque el bucket los bloquea durante 7 días. Si solo los bytes bloqueados ya superasen la cuota, se rechazan los lotes nuevos. Si la ingesta prevista de 7 días no cupiese, el nivel se limita a Basic. Los propietarios y administradores reciben un aviso al llegar al 80 por ciento de la cuota, cuando el límite baja a Basic y cuando se rechaza un lote.

Los registros que caen dentro de un incidente declarado quedan fuera de la expulsión hasta 30 días después de cerrarse el incidente. Consulte la [respuesta a incidentes](/es/docs/incident-response).

## Envío e integridad

El recolector corta un lote cada 30 segundos. Cada lote se firma con la clave de spool de la máquina y lleva el hash del lote anterior, de modo que un lote eliminado o editado rompe la cadena. Los lotes se suben mediante URL prefirmadas que solo permiten crear, generadas a partir del blob de licencia de la máquina, así que la máquina puede añadir registros pero no sobrescribirlos ni borrarlos. Si se pierde la conectividad, los lotes esperan en un spool local firmado y se envían cuando vuelve la conexión.

La compactación nocturna fusiona los lotes en un archivo diario por repositorio y un archivo de cabeceras por máquina, donde figura cada cabecera firmada y se marca cualquier hueco. Los archivos diarios de auditoría de la cuenta se encadenan de la misma manera, por organización y día.

`rdc forensics verify` y el botón Verify evidence de la página de investigación recalculan estas cadenas. Consulte la [respuesta a incidentes](/es/docs/incident-response).

## Detección

La detección de anomalías se ejecuta dos veces. Un detector estadístico en la máquina reacciona al instante y pasa el repositorio a Full. El servidor ejecuta sus propios detectores en la ingesta, de modo que la detección sobrevive a un host comprometido. No se ejecuta ninguna IA por cada registro.

Los detectores están en capas y cada repositorio aprende de su propio tráfico:

| Detector | Busca |
|---|---|
| Líneas base por hora de la semana | Bytes, conexiones, destinos distintos, nombres DNS nuevos y procesos nuevos fuera del ritmo habitual del repositorio para esa hora de la semana |
| Half-Space Trees | Un flujo distinto de los flujos vistos antes |
| ECOD y HBOS | Lotes de flujos que puntúan como atípicos, con las características que determinaron la puntuación |
| Primera vez | Un proceso que abre un archivo sensible que no había abierto antes |

Cada hallazgo lleva los motivos por característica que lo produjeron, y la explicación es una plantilla construida a partir de esos motivos. Sin conexión no hay modelo de lenguaje. Un hallazgo se convierte en un aviso de la cuenta y un correo a propietarios, administradores y al contacto de seguridad. Cuando la máquina está sin conexión, actúa de inmediato en local (captura Full y un registro en su spool firmado) y entrega la alerta cuando vuelve la conectividad, conservando la hora original de detección.

### Paquetes de modelos

Los parámetros de los detectores se publican como paquetes firmados en `data.rediacc.com/models/`: archivos direccionados por contenido, un manifiesto firmado con una clave de modelo Ed25519 sin conexión integrada en renet, una versión mínima de renet y una versión que solo aumenta, por lo que se rechaza un downgrade. Un paquete se verifica antes de instalarse, y el anterior se puede restaurar.

```bash
renet models status
renet models update
renet models rollback
```

Las instalaciones aisladas de la red reciben el mismo paquete firmado dentro de `rdc server bundle`, salvo que se pase `--no-models`.

## Qué puede leer el servidor

El servidor de cuentas lee los registros, porque la línea de tiempo, la verificación y los detectores del servidor los necesitan: destinos, puertos, nombres de proceso, nombres DNS, contadores de bytes y rutas de archivos sensibles. No recibe el contenido de los paquetes ni el contenido de los archivos.

La dirección de un cliente entrante se guarda truncada en los registros (a /24 en IPv4 y a /48 en IPv6), y la dirección completa se almacena en una sección aparte que se elimina a los 30 días. El hash de la sección eliminada permanece en la cabecera firmada, así que la cadena sigue verificándose y el verificador informa de la dirección como censurada. Los destinos salientes se conservan completos, porque son la evidencia.

Los clientes abren los registros mediante una investigación, que exige un plan de pago, el rol de propietario o administrador y una reautenticación reciente, y cada consulta queda auditada. El soporte de Rediacc solo ve datos forenses con una autorización limitada en el tiempo que emite el cliente. Las condiciones de tratamiento están en el [acuerdo de tratamiento de datos](/es/data-processing-agreement).
