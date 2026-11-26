---
title: "Respuesta a incidentes de seguridad"
description: "Cómo gestiona Rediacc sus propios incidentes de seguridad: los avisos escalonados a los clientes, los campos del art. 33(3) del GDPR, la vía de notificación de la CRA y qué reciben los clientes."
category: "Legal"
tags:
  - security
  - compliance
subcategory: foundations
order: 10
language: es
sourceHash: "4b237976bd64e55e"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

Esta página describe lo que ocurre cuando Rediacc sufre un incidente de seguridad propio, como el compromiso de sus sistemas o una vulnerabilidad de sus productos explotada activamente. Los incidentes dentro de los repositorios de un cliente los investiga y notifica el propio cliente, y Rediacc ofrece las herramientas de evidencias para ello. Los informes de vulnerabilidades procedentes del exterior se rigen por la [política de divulgación](/es/docs/security-disclosure-policy).

## Fases

Cada incidente tiene un reloj que arranca cuando Rediacc tiene conocimiento de él. La información se entrega por fases, porque el cuadro completo rara vez se conoce el primer día y el art. 33(4) del GDPR permite facilitarla de forma gradual.

| Fase | Plazo | Contenido |
|------|-------|-----------|
| Alerta temprana | en 24 horas | lo que se sabe hasta el momento y si se sospechan actos malintencionados |
| Notificación | en 72 horas | la naturaleza del incidente, una evaluación inicial y las medidas adoptadas |
| Informe final | en un mes desde la notificación; en una vulnerabilidad explotada activamente, 14 días después de que haya una medida correctiva o de mitigación disponible | una descripción detallada, la causa raíz y las medidas aplicadas y en curso |

## Los campos del art. 33(3)

Cada fase incluye los cuatro elementos que enumera el art. 33(3) del GDPR:

1. la naturaleza de la violación, con las categorías y el número aproximado de interesados y de registros de datos personales afectados
2. el nombre y los datos de contacto del punto de contacto para obtener más información
3. las posibles consecuencias
4. las medidas adoptadas o propuestas para poner remedio a la violación, incluidas las medidas para mitigar sus posibles efectos negativos

Cuando un valor aún no se conoce, la fase lo indica y da la fecha en que se conocerá.

## Qué reciben los clientes

Cuando un incidente afecta a una organización:

- cada fase se envía como aviso en el portal de la cuenta y como correo electrónico, a los propietarios y administradores de la organización y a su contacto de seguridad
- el aviso y el correo se envían con independencia de las preferencias de notificación, porque son comunicaciones de seguridad
- un banner en el portal enlaza con la página del incidente, que muestra todas las fases publicadas
- cada fase ofrece un paquete STIX 2.1 con los indicadores de compromiso, en un formato legible por máquina que las herramientas de seguridad pueden importar

Una organización que no está afectada no recibe nada. Los propietarios y administradores definen el contacto de seguridad de la organización en el portal, para que el correo llegue a la persona adecuada.

## Notificación a las autoridades

Rediacc notifica sus propios incidentes cuando la ley lo exige.

- **GDPR.** Cuando Rediacc actúa como encargado del tratamiento, el aviso escalonado informa al responsable sin dilación indebida (art. 33(2)), y el responsable decide si lo notifica a su autoridad de control. Cuando Rediacc es el responsable, notifica a la autoridad de control competente en un plazo de 72 horas siempre que sea posible (art. 33(1)).
- **Ley de Ciberresiliencia.** Desde el 11 de septiembre de 2026, el art. 14 del Reglamento (UE) 2024/2847 exige que un fabricante notifique una vulnerabilidad explotada activamente o un incidente grave que afecte a la seguridad de un producto con elementos digitales al CSIRT designado y a ENISA, a través de la plataforma única de notificación. Se aplican los mismos pasos de 24 horas, 72 horas e informe final, y el mismo registro del incidente alimenta tanto el aviso a los clientes como la notificación.

## Cómo comunicar un incidente sospechoso

Quien sospeche un incidente que afecte a Rediacc, incluido un cliente que observe un comportamiento inesperado en un componente de Rediacc, escribe a [security@rediacc.com](mailto:security@rediacc.com). Para informar de una vulnerabilidad se sigue la [política de divulgación](/es/docs/security-disclosure-policy).
