---
title: "Canales de Release"
description: "Cómo difieren Edge y Stable, y qué canal usar."
category: "Concepts"
order: 2
language: es
sourceHash: "5fdcb0e8944f5d60"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

Rediacc distribuye actualizaciones a través de dos canales: **Stable** y **Edge**. Funcionan en infraestructura separada y tienen sus propias ventajas e inconvenientes.

## Canal Stable

Stable es el canal predeterminado. Un release solo llega a él tras permanecer en Edge durante 7 días sin problemas reportados.

- Recomendado cuando prefieres una cadencia de actualización conservadora y quieres acceso a planes de pago
- Desplegado después de 7 días de pruebas en Edge
- Las correcciones críticas pueden enviarse directamente cuando sea necesario
- Dominios: `eu.rediacc.com`, `us.rediacc.com`, `asia.rediacc.com`

## Canal Edge

Edge incorpora cada cambio en el momento en que se fusiona a main. Es la versión en vivo del software, desplegada de forma continua.

- Últimas funcionalidades y correcciones, desplegadas en cada fusión
- 2X de límites del plan Community (ver tabla a continuación)
- Gratis para siempre. No hay planes de pago disponibles en Edge.
- Cuentas separadas de Stable. Los datos no se transfieren entre canales.
- Dominios: `edge-eu.rediacc.com`, `edge-us.rediacc.com`, `edge-asia.rediacc.com`

## Comparación

| | Stable | Edge |
|---|---|---|
| **Cadencia de despliegue** | Tras 7 días de prueba | Cada fusión a main |
| **Estabilidad** | Probado durante 7 días | Código más reciente, menos tiempo de prueba |
| **Límites del plan Community** | 10 GB de repos, 500 emisiones/mes, 2 máquinas | 20 GB de repos, 1.000 emisiones/mes, 4 máquinas |
| **Planes de pago** | Disponibles (Professional, Business, Enterprise) | No disponibles |
| **Cuentas** | Independientes | Independientes (separadas de Stable) |
| **Ideal para** | Producción, cargas de trabajo de pago | Pruebas, evaluación, proyectos secundarios, acceso anticipado |

## Límites 2X en Edge

Usa Edge en el plan Community y tus límites de recursos se duplican, sin costo adicional:

| Recurso | Community Stable | Community Edge |
|---|---|---|
| Tamaño del repositorio | 10 GB | 20 GB |
| Emisiones de licencias por mes | 500 | 1.000 |
| Activaciones de máquinas | 2 | 4 |

¿Necesitas límites más altos o funcionalidades de pago? Crea tu cuenta en Stable y actualiza desde allí.

## Cuentas Separadas

Edge y Stable funcionan en infraestructura separada con bases de datos independientes. Una cuenta en uno no existe en el otro, y no hay ruta de migración. Si empiezas en Edge y luego decides que quieres un plan de pago, deberás crear una cuenta nueva en Stable desde cero.

## Cómo Funcionan las Promociones

1. Cada fusión a la rama main se despliega en Edge inmediatamente.
2. Después de 7 días sin problemas, Edge se promueve a Stable automáticamente.
3. Las correcciones críticas pueden enviarse a ambos canales simultáneamente.

Así que Stable va como máximo 7 días por detrás de Edge. La ventana de prueba detecta regresiones en Edge antes de que lleguen a Stable.

## ¿Qué Canal Debo Elegir?

**Elige Stable si:**
- Prefieres una cadencia de actualización conservadora con una ventana de prueba de 7 días
- Necesitas planes de pago (Professional, Business, Enterprise)
- Prefieres máxima fiabilidad sobre las últimas funcionalidades

**Elige Edge si:**
- Quieres probar nuevas funcionalidades anticipadamente
- Estás evaluando la plataforma
- Quieres límites gratuitos generosos para proyectos secundarios
- Te sientes cómodo con código más reciente y menos probado

## Instalación

Consulta [Instalación](/es/docs/installation) para los comandos de instalación, la configuración del gestor de paquetes y las etiquetas de Docker de cada canal.

## Gestión del Canal en el CLI

El CLI usa el canal que configuraste en la instalación o el inicio de sesión. Para cambiar:

```bash
rdc update --channel edge      # Cambiar a Edge
rdc update --channel stable    # Cambiar a Stable
```

Ejecuta `rdc subscription login` y elige una región Edge, y el CLI configura el canal de actualizaciones Edge automáticamente. No se requiere la opción `--channel`.
