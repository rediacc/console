---
title: "Canales de Release"
description: "Comprender los canales de release Edge y Stable, sus diferencias y cómo elegir."
category: "Concepts"
order: 2
language: es
sourceHash: "33795f3fa77f4aa5"
sourceCommit: "a97009927c347f7090e4f4f60f3948997654ae4b"
---

Rediacc publica actualizaciones a través de dos canales de release: **Stable** y **Edge**. Cada canal sirve a una audiencia diferente y tiene sus propias ventajas e inconvenientes.

## Canal Stable

Stable es el canal predeterminado para todos los usuarios. Los releases se promueven desde Edge tras un período de prueba de 7 días sin problemas reportados.

- Recomendado para cargas de trabajo de producción y planes de pago
- Desplegado después de 7 días de pruebas en Edge
- Las correcciones críticas pueden enviarse directamente cuando sea necesario
- Dominios: `eu.rediacc.com`, `us.rediacc.com`, `asia.rediacc.com`

## Canal Edge

Edge recibe cada cambio inmediatamente después de fusionarse a main. Es la última versión del software, desplegada de forma continua.

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

Los usuarios de Edge en el plan Community reciben el doble de límites de recursos sin costo adicional:

| Recurso | Community Stable | Community Edge |
|---|---|---|
| Tamaño del repositorio | 10 GB | 20 GB |
| Emisiones de licencias por mes | 500 | 1.000 |
| Activaciones de máquinas | 2 | 4 |

Si necesitas límites más altos o funcionalidades de planes de pago, crea una cuenta en el canal Stable y actualiza desde allí.

## Cuentas Separadas

Edge y Stable funcionan en infraestructura separada con bases de datos independientes. Una cuenta creada en Edge no existe en Stable, y viceversa. No hay ruta de migración entre canales. Si comienzas en Edge y luego quieres un plan de pago, deberás crear una nueva cuenta en Stable.

## Cómo Funcionan las Promociones

1. Cada fusión a la rama main se despliega en Edge inmediatamente.
2. Después de 7 días sin problemas, Edge se promueve a Stable automáticamente.
3. Las correcciones críticas pueden enviarse a ambos canales simultáneamente.

Esto significa que Stable siempre está como máximo 7 días por detrás de Edge. El período de prueba detecta regresiones antes de que lleguen a los usuarios de producción.

## ¿Qué Canal Debo Elegir?

**Elige Stable si:**
- Ejecutas cargas de trabajo de producción
- Necesitas planes de pago (Professional, Business, Enterprise)
- Prefieres máxima fiabilidad sobre las últimas funcionalidades

**Elige Edge si:**
- Quieres probar nuevas funcionalidades anticipadamente
- Estás evaluando la plataforma
- Quieres límites gratuitos generosos para proyectos secundarios
- Te sientes cómodo con código más reciente y menos probado

## Instalación

Consulta [Instalación](/es/docs/installation) para los comandos de instalación desde cualquier canal, incluyendo la configuración del gestor de paquetes y las etiquetas de Docker.

## Gestión del Canal en el CLI

El CLI usa automáticamente el canal configurado durante la instalación o el inicio de sesión. Para cambiar de canal:

```bash
rdc update --channel edge      # Cambiar a Edge
rdc update --channel stable    # Cambiar a Stable
```

Cuando ejecutas `rdc subscription login` y seleccionas una región Edge, el CLI configura automáticamente el canal de actualizaciones Edge. No se necesita la marca `--channel` manual.
