---
title: "Política de divulgación de vulnerabilidades"
description: "Cómo notificar una vulnerabilidad de seguridad en Rediacc: alcance, puerto seguro, cómo informar y qué tiempos de respuesta esperar."
category: "Legal"
tags:
  - security
  - compliance
subcategory: foundations
order: 9
language: es
sourceHash: "612e816f7a8be282"
sourceCommit: "f9ac63ac37dff49f6c980f00fdacb7e41099ce81"
---

Rediacc agradece los informes de vulnerabilidades de seguridad en sus productos y servicios. Esta política describe qué entra en el alcance, cómo informar y qué puede esperar a cambio quien lo hace. El archivo de contacto legible por máquina está en [`/.well-known/security.txt`](https://www.rediacc.com/.well-known/security.txt) (RFC 9116).

## Alcance

Dentro del alcance:

- la CLI `rdc` y el orquestador de máquinas `renet`
- el servidor de cuentas, su portal web y su API
- los sitios web de Rediacc bajo `rediacc.com` y `rediacc.cloud`
- los artefactos de las versiones: binarios, imágenes de contenedor e instaladores

Fuera del alcance:

- hallazgos que requieren acceso físico a una máquina, o un equipo comprometido que ya controla quien informa
- denegación de servicio por volumen, spam o ingeniería social contra el personal
- informes de escáneres automáticos sin un impacto demostrado
- vulnerabilidades en software de terceros que Rediacc solo redistribuye sin modificar; esas corresponden al proyecto original, y se agradece recibir aquí una copia

## Cómo informar

Envíe el informe a [security@rediacc.com](mailto:security@rediacc.com). Incluya:

- el producto afectado y su versión, o la URL
- los pasos para reproducirlo, o una prueba de concepto
- el impacto que se espera
- si el problema ya es público o se está explotando
- una dirección de contacto para el seguimiento, y si desea que se le mencione

Se prefieren los informes en inglés. No incluya datos reales de clientes: basta una prueba mínima del acceso.

## Puerto seguro

Rediacc no emprenderá ni apoyará acciones legales contra quien actúe de buena fe conforme a esta política, lo que significa que la persona:

- prueba solo con sus propias cuentas, máquinas y datos, o con activos que pertenecen a Rediacc
- se detiene en cuanto demuestra el problema, y no lee, modifica, copia ni elimina datos de terceros
- no degrada el servicio para otros usuarios
- informa con prontitud y mantiene los detalles en privado hasta la fecha de divulgación coordinada indicada más abajo

El trabajo que respeta estos límites se considera autorizado, y Rediacc lo confirmará ante cualquier tercero que lo pregunte.

## Tiempos de respuesta

| Paso | Objetivo |
|------|----------|
| Acuse de recibo del informe | 2 días hábiles |
| Primera evaluación, con la gravedad | 5 días hábiles |
| Actualizaciones de estado mientras siga abierto | al menos cada 14 días |
| Corrección o mitigación de un problema crítico | 14 días desde la evaluación |
| Corrección o mitigación de otros problemas confirmados | 90 días desde la evaluación |

Los objetivos son metas: si un informe necesita más tiempo, se explica el motivo y se fija una nueva fecha.

## Divulgación coordinada

Los detalles se publican junto con la corrección, normalmente dentro de los 90 días siguientes a la primera evaluación. Quien desee una publicación anterior o posterior indica la fecha en el informe, y ambas partes acuerdan una. Una vulnerabilidad que ya se explota en la práctica se trata como un incidente, según se describe en la [página de respuesta a incidentes](/es/docs/security-incident-response).

## Reconocimiento

Un informe confirmado se reconoce en las notas de la versión o en el aviso, con el nombre o alias que elija quien lo envió. Rediacc no mantiene un programa de recompensas con pago.

## Relacionado

- [Respuesta a incidentes](/es/docs/security-incident-response)
- [Seguridad de la cuenta y API](/es/docs/account-security)
