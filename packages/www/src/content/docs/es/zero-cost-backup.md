---
title: "Entornos de desarrollo similares a producción en minutos"
description: "Reduce la configuración del entorno de días a minutos con deduplicación a nivel de bloque."
category: Use Cases
order: 7
language: es
sourceHash: "2aa115fc621f5258"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

> **Reduzca la configuración del entorno de días a minutos con una arquitectura de almacenamiento con deduplicación inteligente.**

**Nota:** Este es un **ejemplo de caso de uso** que muestra cómo Rediacc acelera el trabajo de desarrollo. Somos una startup sin clientes de pago todavía, así que trátalo como un escenario para el que hemos diseñado el producto, no como un estudio de caso terminado.

## El problema

Mehmet gestiona DevOps en una empresa de comercio electrónico. Su equipo necesita **entornos similares a los de producción** para las pruebas, la puesta en escena y el desarrollo. El motivo:

**Donde el enfoque antiguo falla:**
* Configurar entornos similares a los de producción lleva **horas o días**
* Los desarrolladores esperan que el aprovisionamiento de infraestructura complete las pruebas.
* Las inconsistencias del entorno provocan problemas de "funciona en mi máquina"

Los ciclos de desarrollo se arrastraban porque crear un nuevo entorno tardaba días. Ese cuello de botella:

* Disminuyó significativamente la **velocidad de desarrollo** 
* Creé dependencias y tiempos de espera en el proceso de desarrollo.

## Impacto de la crisis

* Los costos de almacenamiento se volvieron **insostenibles** para el presupuesto de TI 
* Las ventanas de respaldo excedieron el tiempo de mantenimiento disponible 
* El rendimiento del sistema se degrada durante las operaciones de copia de seguridad 
* El riesgo de pérdida de datos aumentó debido a copias de seguridad incompletas

## Solución Rediacc

Mehmet encontró Rediacc. Con él:

![Diagrama de copia de seguridad](/img/backup-optimization.svg)

### Tecnología de copia de seguridad inteligente 
* **Parece que se realizan copias de seguridad completas**, pero solo se almacenan físicamente **los datos modificados** 
* Por ejemplo, si hay **cambios diarios promedio de 100 GB** en una base de datos de 10 TB, el sistema **registra solo esos 100 GB** 
* Las copias de seguridad funcionan **completamente y sin problemas durante la restauración**, incluso si se almacenan como un solo archivo

### Ventajas clave

**1. Ahorro de costos** 
* Incluso con cambios diarios de **100 GB** en una base de datos de 10 TB, el costo de almacenamiento mensual se limita a **~3 TB** (era **~300 TB** con el sistema anterior)

**2. Funciona con cualquier stack**
* Rediacc no se limita a SQL Server. Funciona de manera compatible con **MySQL, PostgreSQL, MongoDB** y todas las demás bases de datos.
* No es necesario **conocimiento separado** para diferentes sistemas

**3. Ciclos más rápidos, menos hardware**
* El tiempo de respaldo se reduce de **horas a minutos** 
* La carga en el disco y los recursos de red disminuye en un 99,99% (dependiendo del índice de actualización de los datos totales entre instantáneas)

## Resultado

Con Rediacc, el equipo:
* Reducción de los costos de almacenamiento en un **99,99 % (dependiendo del índice de actualización de los datos totales entre instantáneas)** 
* Procesos estandarizados de copia de seguridad y restauración. 
* Satisfizo todas sus necesidades con **una solución única** para diferentes sistemas de bases de datos
