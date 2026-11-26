---
title: Modelo de seguridad
description: Quién puede ver qué en el almacenamiento de configuración, cómo se acotan las claves, qué alcanzan los agentes y el MCP remoto, y qué se puede recuperar.
category: Guides
tags:
  - security
  - account
subcategory: account
order: 14
language: es
sourceHash: "bd31f15e75569945"
sourceCommit: "45ae253620c97f781ac426d3a84bca6b9a8bc528"
---

# Modelo de seguridad

Esta página explica qué protege el almacenamiento de configuración, qué clave abre qué y a qué puede acceder cada tipo de llamante. Para los pasos de configuración consulta [Almacenamiento de configuración](/es/docs/config-storage); para sesiones y tokens, [Seguridad de la cuenta y API](/es/docs/account-security).

## Quién puede ver qué

Una configuración almacenada se cifra en tres capas. La capa del SDK y la de la frase de contraseña de la organización las gestiona el servidor. La capa intermedia es la clave de cifrado de contenido (CEK), que solo pueden abrir los titulares de una ranura de clave: un secreto de ranura guardado en el dispositivo se combina con un secreto que guarda el servidor, y ninguna de las dos mitades la abre por sí sola.

| El atacante tiene | Ve el contenido de la configuración | Motivo |
|---|---|---|
| Solo una copia de la base de datos | No | Los blobs de configuración están en el almacenamiento de objetos, no en la base de datos |
| La base de datos y el almacenamiento de objetos | No | La capa de la frase de contraseña de la organización necesita el secreto del Worker, y la capa de la CEK, un secreto de ranura |
| Un compromiso total del servidor | No sin un secreto de ranura | Las capas del servidor caen, pero la CEK sigue protegida por la salida PRF del passkey o por el kit de recuperación de 160 bits, y ninguno de los dos se puede adivinar |
| El dispositivo de un miembro eliminado | Lo que ya descargó | Las versiones posteriores quedan cerradas tras una rotación de la CEK |
| Una URL de agente filtrada | Una configuración, como ese usuario | Consulta [Agentes y MCP remoto](#agentes-y-mcp-remoto) |

El servidor sigue viendo metadatos (ids de configuración, equipos, versiones, marcas de tiempo, tamaños de blob) y puede rechazar, retrasar o borrar solicitudes. Un operador que sirva código malicioso del portal puede leer las claves en el navegador. Cada blob está vinculado a su almacén, configuración, equipo y versión, así que el servidor no puede sustituir ni editar uno sin que se note, y la CLI rechaza cualquier versión anterior a una que ya haya visto.

## Alcance de las claves

- Un almacén de configuración por organización y una CEK por almacén. Los equipos son control de acceso en el servidor, no aislamiento criptográfico: un kit de recuperación o una ranura de clave abre la CEK de toda la organización.
- Las ranuras de clave son únicas por almacén, usuario y método, así que hay un kit de recuperación por usuario y organización. Un usuario en dos organizaciones tiene dos kits, y no existe un kit de equipo.
- Un secreto de máquina es uno por máquina y organización, y sirve para inscribir una máquina headless.
- Cada configuración tiene su propia clave de contenido bajo la CEK. Una concesión de agente lleva la clave de contenido de una sola configuración, por lo que con ella no se abre ninguna otra configuración de la organización.
- La política de autorización de cada configuración es un registro aparte, bajo una clave derivada de la CEK y del puntero del registro. Quien tiene la clave de una política solo abre los registros de ese puntero.

## Agentes y MCP remoto

Una concesión de agente es el tipo de titular de claves que hay detrás de una URL de MCP remoto. Lleva la clave de contenido de una configuración y las claves de política de la configuración de equipo de la propia concesión y de la configuración de nivel de organización, nunca la CEK, de modo que un agente lee exactamente lo que lee su persona.

- **Duración.** Una URL dura 7 días por defecto y 30 como máximo; después caduca o se revoca. Una concesión caducada se rechaza y el cliente vuelve a autorizar.
- **Alcance.** Una concesión llega a una configuración y pertenece a una región (eu, us o asia). Una URL presentada en otra región se rechaza indicando la región correcta y nunca se reenvía. Las instalaciones on-premise son de una sola región.
- **Política.** Un agente solo actúa donde lo permiten tanto la aceptación explícita de una persona como el techo de la política. El techo es la política de la organización acotada por la del equipo. Un agente no puede editar la política, leer valores secretos ni ampliar su propia concesión.
- **Radio de impacto.** Una URL filtrada actúa como ese usuario sobre su única configuración hasta que caduca o se revoca. No abre nada fuera del ejecutor alojado de su región.

La salida de las herramientas llega al proveedor de modelos que conecta el usuario, que Rediacc no elige.

### On-premise

No hay Cloudflare en el camino. Los secretos del Worker de la nube pasan a ser variables de entorno o configuración en el host del cliente, así que el acceso al host sustituye al límite del secreto del Worker de la tabla anterior, y las llamadas a herramientas se ejecutan en el ejecutor daemon propio del cliente.

## Política

La política es un registro aparte, sellado por entrada de configuración con datos autenticados que vinculan almacén, configuración, equipo, versión y generación de clave. El servidor no puede leerla, y un registro reproducido o intercambiado falla en su etiqueta de integridad. Los registros de política de versión 1 se rechazan.

Solo un propietario o administrador de la organización escribe la política de la organización, y solo un administrador de equipo (o un propietario o administrador) escribe la política de ese equipo. Una escritura exige 2FA y una sesión elevada, y un passkey vinculado cuando el almacén requiere passkeys. Todos los miembros y todos los ejecutores que les sirven la leen. Una clave que la organización bloquea se ignora en la política de un equipo.

## Qué se puede recuperar

| Situación | Recuperación |
|---|---|
| Passkey perdido | Desbloquea con el kit de recuperación y registra un passkey nuevo |
| Kit perdido | Regéneralo desde un passkey que funcione; la copia impresa anterior deja de servir |
| Ambos perdidos | Un propietario o administrador vuelve a añadir al miembro mediante el traspaso de miembros |
| El último titular de clave pierde ambos | Irrecuperable, y por eso se aconseja un segundo titular de clave |
| Miembro eliminado | Sus ranuras y tokens desaparecen al instante; una rotación de la CEK cierra las versiones posteriores a una clave que conservara |
| Rotación de la CEK | Reenvuelve la CEK bajo una nueva generación e invalida todos los kits de recuperación |

El servidor rechaza cualquier borrado de ranura, eliminación de miembro o salida de miembro que deje menos de dos titulares de clave y ninguna ranura de recuperación. Cada miembro recibe un kit de recuperación obligatorio al inscribirse, y conservarlo es responsabilidad del miembro.
