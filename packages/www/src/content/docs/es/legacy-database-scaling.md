---
title: Escalado de bases de datos heredadas
description: Escale las bases de datos heredadas sin migrar aprovechando la replicación de datos y la distribución de consultas en tiempo real.
category: Use Cases
order: 3
language: es
---

> **Su base de datos heredada lo está frenando. Libérate sin romperlo.**

**Nota:** Este es un **ejemplo de caso de uso** que demuestra cómo Rediacc puede resolver este problema. Como startup, estos escenarios representan aplicaciones potenciales en lugar de estudios de casos completos.

**Escenario de crisis:** A pesar de escalar los servidores 10 veces con Kubernetes, el rendimiento solo mejoró 2 veces. Los clientes se quejaron de tiempos de consulta lentos, los costos aumentaron sin resultados satisfactorios y la reputación estaba en riesgo.

## El problema

Los servicios de la empresa en el entorno de la nube estaban **luchando por responder**. Como solución, el equipo de software: 
* Realicé **escalado horizontal con Kubernetes** y **aumenté el número de servidores 10 veces** 
* Sin embargo, el rendimiento mejoró **sólo 2 veces**

**Detección de cuellos de botella:** 
* Se entendió que el origen del problema era una **base de datos heredada que no se puede escalar** 
* La base de datos no podría funcionar de forma distribuida como en las arquitecturas modernas.

**Dilema:** 
* Migrar a una base de datos moderna **podría llevar años** → Requirió reescribir código, migración de datos y procesos de prueba 
* La pérdida de costos y tiempo fue inaceptable.

## Impacto de la crisis

* Los clientes se quejan debido a **tiempos de consulta lentos** 
* Los costos del servidor están aumentando, pero **el rendimiento no es satisfactorio** 
* El riesgo de **pérdida de reputación** aumenta en un mercado competitivo

## Solución Rediacc

El ingeniero de sistemas Yüksel, utilizando la función de respaldo cruzado de Rediacc:

![Escalado de base de datos heredado](/img/legacy-scaling.svg)

### 1. **Replicación de datos en tiempo real** 
* Los cambios en la base de datos heredada se transfirieron a otros servidores **a intervalos de 10 a 15 minutos** 
* **Solo se sincronizaron los datos modificados** → **El consumo de ancho de banda se redujo en un 95%**

### 2. **Distribución de consultas** 
* Las consultas de lectura se **distribuyeron a varias máquinas** 
* Las operaciones de escritura se mantuvieron **en la base de datos principal** para garantizar la coherencia.

### 3. **Escalamiento sin costo** 
* El sistema heredado fue soportado con servidores adicionales **sin ser modificado** 
* No es necesario adquirir nuevo hardware → **Los servidores en la nube se alquilaron por horas** para optimizar costos

## Resultado

**Aumento de rendimiento:** 
* Los tiempos de consulta se redujeron de **55 segundos a 7 segundos** 
* La capacidad del sistema aumentó **8 veces**

**Control de Costos:** 
* Ahorros al reescribir el sistema heredado → **Se preservaron los recursos financieros**

**Ganancia de tiempo:** 
* La solución se implementó **en 3 semanas** 
* Las quejas de los clientes se resolvieron en un **99,99 % (dependiendo del índice de actualización de los datos totales entre instantáneas)**