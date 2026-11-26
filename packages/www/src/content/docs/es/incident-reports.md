---
title: "Informes de incidentes: por fases, firmados y verificables"
description: "Genere la alerta temprana, la notificación y el informe final de un incidente en un repositorio de cliente como JSON, STIX 2.1 o PDF. Cada informe va firmado con Ed25519, incluye un enlace de verificación con QR y asigna sus campos a NIS2, al formato 2025/302 y al art. 33.3 del RGPD."
category: "Guides"
tags:
  - security
  - compliance
subcategory: data-protection
order: 11
language: es
sourceHash: "d7f6e084c5c1d0d9"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

# Informes de incidentes

Un incidente declarado ([respuesta a incidentes](/es/docs/incident-response)) genera tres informes por fases que el cliente presenta ante un regulador. Rediacc genera los documentos a partir de la evidencia. Si un incidente es significativo o notificable sigue siendo un juicio del cliente, y todos los informes lo dicen.

## Fases

Cada fase añade las secciones que se indican abajo y conserva las de la fase anterior, así que una sección que ninguna fase pide se omite en lugar de quedar en blanco.

| Fase | Plazo | Añade |
|---|---|---|
| Alerta temprana | 24 horas después del conocimiento | Cabecera, línea de tiempo, indicadores de compromiso, impacto malicioso sospechado y transfronterizo |
| Notificación | 72 horas después del conocimiento | Evaluación inicial, impacto en los datos (categorías, cifras aproximadas, Estados miembros) y técnicas ATT&CK |
| Final | Un mes natural después de la notificación | Causa raíz y medidas de mitigación |

El informe final sigue a una notificación, así que la notificación se genera primero.

Cada hecho de un informe indica cómo se conoce: observado en la evidencia, introducido por el cliente o inferido. Un hecho inferido lleva una confianza y el motivo del detector. La evaluación, las categorías de datos, los Estados miembros, la causa sospechada, las acciones realizadas, el punto de contacto y las técnicas son datos que el cliente introduce en la página del incidente antes de generar.

## Formatos

| Formato | Uso |
|---|---|
| JSON | La forma canónica y verificable |
| STIX 2.1 | Un paquete de indicadores para herramientas de inteligencia de amenazas |
| PDF | Un documento legible con Noto Sans incrustada (latino, cirílico y turco) o Noto Sans Arabic; los informes en japonés, coreano y chino se rechazan hasta que se fijen sus fuentes. Lleva el aviso legal, un código QR y el hash del informe en el pie de cada página |

Desde la página del incidente, cada fase tiene un botón de descarga por formato. Desde la línea de comandos:

```bash
rdc incident export <id> --stage early-warning
rdc incident export <id> --stage notification --format stix
rdc incident export <id> --stage final --format pdf --out ./reports
```

El formato predeterminado es JSON. `--format` solo se aplica con `--stage`. El archivo se escribe con su identificador de informe.

## Firma y verificación

Cada informe se firma con una clave de informe Ed25519, y el identificador, la fase y el hash del informe constan en un registro público. La firma cubre el contenido canónico del informe, así que se detecta cualquier cambio posterior a la firma.

Un informe se comprueba en tres lugares:

- La página de verificación en `/account/verify/report/<id>`, que abre el código QR del PDF. La comprobación se ejecuta en el navegador contra la clave de informe publicada y no se sube nada. Un archivo JSON se comprueba por completo. Un PDF no se puede volver a hashear en el navegador, así que la página confirma que el PDF lleva el hash del informe y remite al archivo JSON para una comprobación completa.
- La línea de comandos, para un informe JSON:

```bash
rdc forensics verify --report ./reports/<report-id>.json
```

El comando termina con código 1 cuando el contenido o la firma no coinciden. Un PDF se verifica mediante el informe JSON a partir del cual se creó.

- El sello de evidencia dentro del informe, que registra el resultado de Verify evidence para la ventana: quién verificó, con qué versión y cuándo.

## Correspondencia de campos

Cada campo del informe se asigna a los regímenes bajo los que el cliente notifica, de modo que el contenido se pueda trasladar sin volver a escribirlo. La correspondencia abarca tres regímenes: NIS2 art. 23.4, el formato de notificación de incidentes del Reglamento de Ejecución (UE) 2025/302 y el art. 33.3 del RGPD. Ejemplos:

| Campo del informe | NIS2 | RGPD |
|---|---|---|
| Momento del conocimiento | Art. 23(4)(a) | Art. 33(1) |
| Cronología | Art. 23(4)(d) | Art. 33(3)(a) |
| Punto de contacto | Art. 23(4) | Art. 33(3)(b) |

Un campo sin equivalente en un régimen explica por qué, en lugar de omitirse. La notificación del art. 33.3 del RGPD no tiene número de referencia ni hora de cierre, por ejemplo.

## Lo que un informe no afirma

En cada fase se imprimen dos declaraciones:

- Los registros de flujo prueban volumen y destino, no contenido.
- Si el incidente es significativo o notificable es un juicio del cliente.

Rediacc no presenta nada ante un regulador en nombre del cliente.
