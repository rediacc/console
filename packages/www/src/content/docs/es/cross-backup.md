---
title: Estrategia de copia de seguridad cruzada
description: Proteja los datos contra desastres con copias de seguridad intercontinentales eficientes y una recuperación rápida.
category: Use Cases
order: 5
language: es
---

> **Cuando ocurre un desastre, ¿sobrevivirán sus datos? Con Rediacc, siempre lo hace.**

**Nota:** Este es un **ejemplo de caso de uso** que demuestra cómo Rediacc puede resolver este problema. Como startup, estos escenarios representan aplicaciones potenciales en lugar de estudios de casos completos.

**Escenario de crisis:** Después de una llamada de un cliente, se descubrió que los servicios no funcionaban debido a una **falla del disco**. La última copia de seguridad del servidor de respaldo remoto tenía **3 semanas**, lo que provocó una pérdida significativa de datos.

## El problema

La empresa se da cuenta de los riesgos de realizar copias de seguridad de los datos **sólo en la misma máquina**: 
* Fallos de hardware 
* Ciberataques 
* Desastres físicos como guerra, terremotos, incendios, inundaciones. 
* Protección insuficiente contra la pérdida de datos

**Buscar solución:** 
* Se decide realizar una copia de seguridad de 20 TB de datos en **un servidor remoto** 
* Sin embargo, con los métodos tradicionales, esta copia de seguridad tarda **2 semanas** y ocupa **99,99% (dependiendo del índice de actualización de los datos totales entre instantáneas)** del ancho de banda.

## Impacto de la crisis

Después de una llamada de un cliente: 
*Se nota que **los servicios no funcionan** 
* Se detecta una **falla de disco** 
* Al verificar el servidor de respaldo remoto, se entiende que **el último respaldo se realizó hace 3 semanas**

**Resultados:** 
* Los intentos de recuperación manual del disco **fallan** 
* Debido a 3 semanas de pérdida de datos, **los contratos de los clientes se cancelan** 
* La reputación de la empresa **está gravemente dañada**

## Solución Rediacc

### 1. **Primera copia de seguridad** 
* La primera vez que se transfieren 20 TB de datos a un servidor remoto, se necesitan 2 semanas.

### 2. **Copias de seguridad cruzadas por hora** 
* Cada hora, se crea una percepción de copia de seguridad completa, pero **solo se transfieren los datos modificados**

### 3. **Preparación para escenarios de desastre** 
* Se puede realizar una copia de seguridad de los datos incluso en servidores **intercontinentales** 
* Incluso si la máquina principal falla, los datos de hace tan solo 1 hora se **activan en cuestión de minutos**

## Resultado

**Ahorro de tiempo:** 
* El tiempo de respaldo se redujo de **2 semanas a un promedio de 4 minutos** 
* El riesgo de pérdida de datos se redujo a **1 hora**

**Optimización de costos:** 
* El consumo de ancho de banda disminuyó un **98%**

**Continuidad ininterrumpida del negocio:** 
* Cuando el servidor principal falló, la copia de seguridad remota se activó en **7 minutos**