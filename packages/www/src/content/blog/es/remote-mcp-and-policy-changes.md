---
title: "MCP remoto: un agente que solo lee lo que su persona puede leer"
description: "El MCP remoto funciona en los tres Workers regionales. Un grant lleva la clave de una config y las claves de política de su persona, nunca la clave maestra, y ningún token sobrevive al grant."
author: Rediacc
publishedDate: 2026-11-25
category: announcement
tags:
  - mcp
  - ai-agents
  - security
  - policy
featured: false
language: es
sourceHash: "ce8dbe4241a2d7ab"
sourceCommit: "dda643f43f9dadc19e08a84858e87f115d428f85"
---

> **En resumen.** El MCP remoto da a un agente de IA una URL en lugar de una terminal. La pregunta de diseño nunca fue cómo conectar al agente, sino qué puede ver una vez conectado. La respuesta: exactamente lo que ve la persona que creó el grant, y nada más.
>
> - Un grant llega a **una config** y vive en **una región**.
> - Los tokens duran como máximo **1 hora** (acceso) y **30 días** (renovación), y nunca más que el propio grant.
> - El grant lleva la clave de contenido de una config y dos **claves de lectura de política**, nunca la clave maestra del config store.
> - El formato de los registros de política cambió. Los antiguos se rechazan y no hay ruta de migración.

## Una URL, no una shell de acceso

El servidor MCP local (`rdc mcp serve`) se ejecuta junto al agente y hereda el acceso de la máquina donde corre. El servidor remoto es distinto. En cada región funciona un Worker MCP en `mcp.<region>.rediacc.cloud`, y cada agente se conecta a la URL de un grant: `https://mcp.<region>.rediacc.cloud/g/<grantId>`. Las llamadas a herramientas se ejecutan en el ejecutor de la organización, no en el portátil de una persona desarrolladora.

Los clientes interactivos como claude.ai inician sesión con OAuth 2.1 y PKCE. Los agentes sin interfaz envían un bearer `rmcp_<grantId>.<secret>`. Ambas formas identifican el grant, y el id de la URL solo lo nombra.

## El grant es el límite

Un grant es un objeto pequeño y concreto. Nombra una config, una caducidad y un alcance: un indicador de solo lectura, una lista de herramientas permitidas y patrones de nombres de máquinas y repositorios.

De esa forma salen tres reglas:

- **Una config.** Un `tools/call` que nombra otra config se rechaza con `REDIACC_GRANT_SCOPE` antes de que se ejecute nada. Quien tiene tres configs autoriza tres grants.
- **Una región.** Los ids de grant empiezan por su región. Una petición que llega al Worker equivocado recibe un HTTP 421 con la URL correcta y nunca se reenvía.
- **Una vigencia.** Un token de acceso dura lo menor entre 1 hora y el tiempo que le queda al grant. Un token de renovación dura lo menor entre 30 días y el tiempo que le queda al grant. Cada renovación vuelve a consultar el grant, así que uno revocado deja de funcionar en el siguiente intercambio. Presentar dos veces un token de renovación revoca el grant.

La URL de un grant vive 7 días por defecto y 30 como máximo.

## Juzgado como su persona

Lo interesante es el material criptográfico. Un grant es un secreto dividido. El navegador genera un valor aleatorio y lo muestra una sola vez. El servidor de cuentas guarda solo el hash de una etiqueta derivada de él, y el ejecutor deriva la clave de slot únicamente mientras tiene las dos mitades. Lo que abre esa clave de slot es la clave de contenido de la config, nunca la clave maestra de la organización.

La misma clave de slot abre además dos **claves de política**. La política, es decir, las reglas de autorización de una entrada de config, vive ahora en su propio registro, sellado con una clave derivada de la clave del store y del puntero del registro: store, config, equipo y generación de clave. El grant lleva la clave de la config de su equipo y la de la config a nivel de organización. Son los dos registros de política que lee su persona, así que el ejecutor lee los mismos.

El efecto es que un agente se juzga como su persona. El techo es la política de la organización, acotada por la del equipo. El agente actúa solo donde un consentimiento humano y ese techo lo permiten a la vez. No puede editar la política, leer valores de secretos ni ampliar su propio grant. Una clave que la organización bloquea se ignora en la política de un equipo, y el agente se encuentra con ese resultado igual que la persona.

Atar cada clave a un puntero tiene un efecto secundario que conviene decir. Quien tiene una clave de política abre los registros de ese puntero bajo esa generación de clave y ninguno más. Un blob servido para otro store, otra config u otro equipo, o repetido bajo otra versión, falla la etiqueta de integridad.

## Qué cambia en las instalaciones existentes

- **Los registros de política son de versión 2.** Uno de versión 1, sellado con la propia clave del store, no se abre. Es una ruptura limpia a propósito.
- **Las escrituras alojadas pasan por la misma política.** Las escrituras de config hechas a través del ejecutor alojado se comprueban contra el techo de la política antes de guardarse.
- **Los agentes locales mantienen el mismo techo.** `REDIACC_ALLOW_CONFIG_EDIT` sigue habilitando a un agente para editar la config en los punteros que nombra, pero solo dentro de lo que permite la política.
- **Los grants caducados o rotados fallan con claridad.** `initialize` y `tools/list` siguen respondiendo, y cada llamada devuelve `REDIACC_GRANT_EXPIRED`, `REDIACC_GRANT_REVOKED` o `REDIACC_KEY_ROTATED` con una `reauthUrl`.

Cada grant admite 60 llamadas por minuto y 5 en curso.

## Qué consigue una URL filtrada

Una URL filtrada actúa como ese usuario sobre su única config hasta que caduca o se revoca. No abre ninguna otra config de la organización ni nada fuera del ejecutor alojado de su región. La salida de las herramientas sí llega al proveedor de modelos que el usuario conecta. Rediacc no elige ese proveedor.

La guía de configuración es [MCP Server Setup](/es/docs/ai-agents-mcp), y la estructura de claves está en el [modelo de seguridad](/es/docs/security-model).
