---
title: Estrategia de copia de seguridad cruzada
description: "Tu copia de seguridad falla en el momento en que falha su máquina. Rediacc replica instantáneas en una máquina separada para que una falla de disco no se lleve todo consigo."
category: Use Cases
order: 5
language: es
sourceHash: "39dbeac1faec121c"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

> **Cuando ocurre un desastre, ¿sobrevivirán sus datos? Con Rediacc, siempre lo hace.**

**Nota:** Este es un **ejemplo de caso de uso** que demuestra cómo Rediacc puede resolver este problema. Estos escenarios representan aplicaciones potenciales, no estudios de casos completos.

**Escenario de crisis:** Una llamada de cliente revela la interrupción: **falla de disco**. La última copia de seguridad del servidor de respaldo remoto tenía **3 semanas de antigüedad**. Son semanas de datos, desaparecidos.

## El problema

Mantener tu única copia de seguridad en la misma máquina que los datos que protege no es una estrategia. Aquí está lo que confirma esa falla:
* Fallos de hardware
* Ciberataques
* Desastres físicos como guerra, terremotos, incendios, inundaciones
* Protección insuficiente contra la pérdida de datos

**Buscando una solución:**
* Se decide realizar una copia de seguridad de 20 TB de datos en **un servidor remoto**
* Sin embargo, con los métodos tradicionales, esta copia de seguridad tarda **2 semanas** y ocupa **99,99% (según la proporción de actualización del total de datos entre instantáneas)** del ancho de banda

## Impacto de la crisis

Después de una llamada de cliente:
* Se nota que **los servicios no funcionan**
* Se detecta una **falla de disco**
* Al verificar el servidor de respaldo remoto, se entiende que **el último respaldo se realizó hace 3 semanas**

**Resultados:**
* Los intentos de recuperación manual del disco **fallan**
* Debido a 3 semanas de pérdida de datos, **los contratos de los clientes se cancelan**
* La reputación de la empresa **está gravemente dañada**

## Solución Rediacc

![Cross Backup Strategy](/img/cross-backup.svg)

### 1. **Primera copia de seguridad**
* La primera vez que se transfieren 20 TB de datos a un servidor remoto, tarda 2 semanas

### 2. **Copias de seguridad cruzadas cada hora**
* Cada hora, se crea la percepción de una copia de seguridad completa, pero **solo se transfieren los datos modificados**

### 3. **Preparación para escenarios de desastre**
* Se puede realizar una copia de seguridad de los datos incluso en servidores **intercontinentales**
* Incluso si la máquina principal falla, los datos de hace tan solo 1 hora se **activan en cuestión de minutos**

## Resultado

**Ahorro de tiempo:**
* El tiempo de respaldo se redujo de **2 semanas a un promedio de 4 minutos**
* El riesgo de pérdida de datos se redujo a **1 hora**

**Reducción de costos:**
* El consumo de ancho de banda disminuyó un **98%**

**Continuidad del negocio:**
* Cuando el servidor principal falló, la copia de seguridad remota se activó en **7 minutos**
