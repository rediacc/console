---
title: "Canales de Release"
description: "Cómo difieren Edge y Stable, y qué canal usar."
category: "Concepts"
tags:
  - cli
  - operations
subcategory: platform
order: 2
language: es
sourceHash: "29d62173c5cf044a"
sourceCommit: "abc292b1b7ca5096423e098c12a9b23bdabda16b"
---

Rediacc distribuye las actualizaciones del CLI a través de dos canales: **Stable** y **Edge**. Ambos se conectan al mismo producto, así que la cuenta, el plan y los límites son idénticos en cualquiera de los dos. Los canales solo se diferencian en lo pronto que te llega una versión.

## Canal Stable

Stable es el canal predeterminado. Un release solo llega a él tras permanecer en Edge durante 7 días sin problemas reportados.

- Recomendado cuando prefieres una cadencia de actualización conservadora
- Desplegado después de 7 días de pruebas en Edge
- Las correcciones críticas pueden enviarse directamente cuando sea necesario

## Canal Edge

Edge incorpora cada cambio en el momento en que se fusiona a main. Es la versión en vivo del software, desplegada de forma continua.

- Publicado en cada fusión a main
- Las mismas cuentas, planes y límites que Stable
- Ideal para probar las novedades cuanto antes

## Un producto, dos canales

Tu cuenta vive en tu región de datos, en `eu.rediacc.cloud`, `us.rediacc.cloud` o `asia.rediacc.cloud`, sea cual sea el canal que uses. Cambiar de canal no afecta a tu cuenta, tus datos ni tu suscripción. Para las regiones, consulta [Regiones de Datos](/es/docs/data-regions).

## Comparación

| | Stable | Edge |
|---|---|---|
| **Cadencia de despliegue** | Tras 7 días de prueba | Cada fusión a main |
| **Estabilidad** | Probado durante 7 días | Código más reciente, menos tiempo de prueba |
| **Planes y límites** | Iguales | Iguales |
| **Cuenta y datos** | Compartidos | Compartidos |
| **Ideal para** | Producción, cargas de pago | Acceso anticipado, evaluación |

## Cómo Funcionan las Promociones

1. Cada fusión a la rama main se despliega en Edge inmediatamente.
2. Después de 7 días sin problemas, Edge se promueve a Stable automáticamente.
3. Las correcciones críticas pueden enviarse a ambos canales simultáneamente.

Así que Stable va como máximo 7 días por detrás de Edge. La ventana de prueba detecta regresiones en Edge antes de que lleguen a Stable.

## ¿Qué Canal Debo Elegir?

**Elige Stable si:**
- Prefieres una cadencia de actualización conservadora con una ventana de prueba de 7 días
- Prefieres máxima fiabilidad sobre las últimas funcionalidades

**Elige Edge si:**
- Quieres probar nuevas funcionalidades anticipadamente
- Estás evaluando la plataforma
- Te sientes cómodo con código más reciente y menos probado

## Instalación

Consulta [Instalación](/es/docs/installation) para los comandos de instalación, la configuración del gestor de paquetes y las etiquetas de Docker de cada canal.

## Gestión del Canal en el CLI

El CLI usa el canal que configuraste en la instalación. Para cambiar:

```bash
rdc update --channel edge      # Cambiar a Edge
rdc update --channel stable    # Cambiar a Stable
```
