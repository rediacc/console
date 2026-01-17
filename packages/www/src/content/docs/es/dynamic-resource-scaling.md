---
title: Escalado dinámico de recursos
description: Cree una arquitectura en la nube con flexibilidad ilimitada para capacitación en IA y cargas de trabajo dinámicas.
category: Use Cases
order: 1
language: es
---

> **¿Es rígida su arquitectura en la nube? Construya con flexibilidad ilimitada.**

**Nota:** Este es un **ejemplo de caso de uso** que demuestra cómo Rediacc puede resolver este problema. Como startup, estos escenarios representan aplicaciones potenciales en lugar de estudios de casos completos.

**Escenario de crisis:** Los tiempos de entrenamiento de IA **se extendieron 2 o 3 veces**, lo que provocó retrasos en el proyecto. Los ingenieros experimentaron una pérdida significativa de productividad mientras esperaban recursos, lo que amenazó la ventaja competitiva de la empresa.

## El problema

Los ingenieros de software de la empresa están experimentando problemas de rendimiento con los servidores **locales** utilizados para el **entrenamiento del modelo de IA**: 
* Durante el **horario de oficina** (08:00-17:00), las solicitudes del servidor alcanzan el 99% de su capacidad 
* La capacitación que requiere una alta potencia de procesamiento hace que el hardware **sea insuficiente**

**Buscar solución:** 
* El costo de actualización del servidor **no se considera adecuado** debido a **6 a 7 horas de uso diario** 
* Aunque se considera la migración a la nube, el **costo de transferencia de datos** y las **dificultades de sincronización** son obstáculos

## Impacto de la crisis

* Los tiempos de entrenamiento de IA **se extienden 2-3 veces**, los proyectos se retrasan 
* Los ingenieros experimentan **pérdida de productividad** mientras esperan recursos 
* La empresa enfrenta el riesgo de **perder gradualmente su ventaja competitiva**

## Solución Rediacc

El ingeniero de sistemas Yüksel desarrolla **un modelo híbrido** con Rediacc:

![Escalado de nube híbrida](/img/hybrid-cloud-scaling.svg)

### 1. **Migración instantánea a la nube** 
* Durante el horario de oficina, los servicios locales se clonan en la nube **con todos los datos y configuraciones** 
* Se sincronizan 100 TB de datos en 9 minutos transfiriendo **sólo las partes cambiadas** gracias a Rediacc

### 2. **Escalado dinámico** 
* Se alquilan servidores en el entorno de la nube **tanto como sea necesario para la capacitación en IA** 
* La potencia de procesamiento se puede **aumentar 10 veces** según la demanda

### 3. **Sincronización nocturna** 
* Al final de la jornada laboral, **todos los cambios en la nube** se **extraen automáticamente** al entorno local 
*Los ingenieros que trabajan de noche continúan sus operaciones con **datos actualizados**

## Resultado

**Ventaja de costos:** 
* Al **alquilar recursos de la nube por horas**, el costo mensual se redujo en un **60 %** 
* Se eliminó la necesidad de actualizar los servidores locales **

**Aumento de rendimiento:** 
* Los tiempos de entrenamiento de IA se redujeron de **8 horas a 1,5 horas** 
* La productividad de los ingenieros aumentó un **40%**

**Trabajo flexible:** 
* **La coherencia de los datos** entre los entornos locales y de nube se garantizó sin problemas 
* Los equipos del turno de noche **tuvieron acceso instantáneo a datos actualizados**