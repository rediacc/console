---
title: Recuperación del viaje en el tiempo
description: Recupere datos borrados accidentalmente de hace semanas con viajes en el tiempo basados ​​en instantáneas.
category: Use Cases
order: 2
language: es
---

> ** Cuando otras pierden datos para siempre, puedes viajar en el tiempo. **

**Nota:** Este es un **ejemplo de caso de uso** que demuestra cómo Rediacc puede resolver este problema. Como startup, estos escenarios representan aplicaciones potenciales en lugar de estudios de casos completos.

**Escenario de crisis:** Un empleado recién contratado **borró accidentalmente** datos críticos de la base de datos activa hace 3 semanas. El sistema de respaldo de la empresa solo mantuvo respaldos durante 2 semanas, lo que hizo que la recuperación de datos fuera casi imposible por medios convencionales.

## El problema

Mehmet es un experto en sistemas responsable de la base de datos de una gran empresa de compras online. Una mañana, tras las quejas de los clientes, se da cuenta de que algunos registros de pedidos anteriores **no son visibles** en el sistema. La investigación revela que un empleado recién contratado **borró accidentalmente** algunos datos críticos de la base de datos activa hace 3 semanas, **conectándose a la base de datos activa en lugar del entorno de prueba**.

**Sistema de respaldo existente:** 
* Las copias de seguridad completas se realizan una vez por semana. 
* **Las copias de seguridad incrementales** se registran diariamente

**Dilema:** La eliminación tuvo lugar **antes de la fecha de las copias de seguridad completas**, por lo que los datos perdidos no están en las copias de seguridad. Las copias de seguridad diarias **solo registran los datos más recientes**, por lo que **los elementos eliminados no se pueden recuperar**.

## Impacto de la crisis

Debido a la pérdida de datos: 
* Los clientes **no pueden procesar solicitudes de reembolso** 
* Se producen inconsistencias en el sistema de pago. 
* Las quejas se difundieron rápidamente en las redes sociales.

**Resultados:** 
* El equipo de atención al cliente está bajo **intensa presión** 
* La reputación de la empresa está **rápidamente dañada** 
* Los esfuerzos de recuperación manual de datos logran **sólo un 15% de éxito**

**Desafío adicional:** 
* Para reducir los costos de almacenamiento, la empresa mantiene **solo las últimas 2 semanas de copias de seguridad** 
* Los datos eliminados no están en las **copias de seguridad recientes**

## Solución Rediacc

Mehmet ofrece una solución similar a una "máquina del tiempo" con Rediacc:

### 1. **Instantáneas** 
* Rediacc toma automáticamente instantáneas del sistema cada hora 
* Estas instantáneas también cubren los momentos justo antes de que se eliminaran los datos.

### 2. **Regresando en el tiempo** 
* Mehmet selecciona la fecha y hora en que se produjo la eliminación en la interfaz de Rediacc 
* Restaura una instantánea del sistema de hace 3 semanas a una nueva instancia en 1 minuto

### 3. **Recuperación completa** 
* Los datos perdidos se restauran completa y consistentemente

## Resultado

* La reputación de la empresa fue reparada **en 24 horas** 
* La pérdida financiera se evitó en un **95%** 
* Rediacc demostró que se pueden realizar copias de seguridad frecuentes **sin aumentar los costos de almacenamiento**