---
title: Recuperación del viaje en el tiempo
description: "Recupere datos borrados hace semanas usando instantáneas btrfs, incluso después de que sus copias de seguridad normales ya las hayan descartado."
category: Use Cases
order: 2
language: es
sourceHash: "4c1fcb1667a89759"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

> ** Cuando otras pierden datos para siempre, puedes viajar en el tiempo. **

**Nota:** Este es un **ejemplo de caso de uso** que muestra cómo Rediacc maneja este tipo de problema. Somos una startup. Son escenarios realistas para los que el producto fue diseñado, no estudios de caso de clientes que ya hayamos entregado.

**Escenario de crisis:** Un empleado recién contratado **borró accidentalmente** filas críticas de la base de datos activa hace 3 semanas. El sistema de respaldo solo conserva 2 semanas de historial. Con una configuración normal, esos datos se pierden para siempre.

## El problema

Mehmet gestiona la base de datos de una gran plataforma de comercio electrónico. Una mañana los clientes empiezan a quejarse de que registros de pedidos anteriores **no son visibles**. Investiga. Un ingeniero recién contratado había **borrado accidentalmente** filas críticas de la base de datos activa hace 3 semanas, **conectándose a la base de datos activa en lugar del entorno de prueba**. El error clásico que todo DBA ha cometido alguna vez o ha visto cometer a un junior.

**Sistema de respaldo existente:** 
* Las copias de seguridad completas se realizan una vez por semana. 
* **Las copias de seguridad incrementales** se registran diariamente

**El dilema:** la eliminación ocurrió **antes de la fecha de las copias de seguridad completas**, por lo que los datos perdidos no están en ningún archivo de copia de seguridad. Las copias de seguridad diarias **solo registran los datos más recientes**, por lo que **los elementos eliminados no se pueden recuperar**.

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

Esta es la configuración de "máquina del tiempo" que Mehmet construye con Rediacc:

![Time Travel Recovery](/img/time-travel-recovery.svg)

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
