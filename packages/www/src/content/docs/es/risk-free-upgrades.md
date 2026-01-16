---
title: Actualizaciones sin riesgos
description: Pruebe las actualizaciones de la base de datos sin riesgos mediante la clonación instantánea y las instantáneas cada hora.
category: Use Cases
order: 4
language: es
---

> **Pruébalo todo. No arriesgues nada. Actualice con confianza.**

**Nota:** Este es un **ejemplo de caso de uso** que demuestra cómo Rediacc puede resolver este problema. Como startup, estos escenarios representan aplicaciones potenciales en lugar de estudios de casos completos.

**Escenario de crisis:** Durante una actualización de la base de datos, se produjo un **error inesperado** que impidió volver a la versión anterior o continuar con la nueva. Los clientes no podían acceder a los sistemas y más de 5000 empleados no podían trabajar.

## El problema

Mehmet es un administrador de sistemas experimentado que gestiona bases de datos a gran escala. Decide **actualizar una base de datos PostgreSQL de 100 TB de la versión 13 a la 14**. Su plan:

1. **Realice una copia de seguridad** → Sin embargo, la copia de seguridad demora **varios días** debido al tamaño de los datos. 
2. **Realice la actualización el fin de semana** → Se notifica a los departamentos de una interrupción el **sábado 01:00-05:00**

## Impacto de la crisis

* Se produce un **error inesperado** durante la actualización 
* La base de datos **no puede volver a la versión anterior ni pasar a la nueva versión** 
* Incluso los equipos de soporte externos no pueden resolver el problema.

**Impactos:** 
* Los clientes **no pueden acceder a los sistemas de pago y pedido** 
* Los empleados de la empresa (**5000+ personas**) no pueden trabajar 
* Comienza la pérdida de reputación** y aumentan las quejas

**Solución temporal:** 
* La última copia de seguridad se carga en **un nuevo servidor** → **El costo del hardware se duplica** 
* Los datos de los jueves y viernes son **solo en el entorno en vivo**, por lo que se produce una pérdida de datos 
* **Se crean dos bases de datos con diferentes versiones** → Aumentan las inconsistencias

## Solución Rediacc

Mehmet resuelve el problema fundamentalmente con Rediacc:

### 1. **Clonación instantánea** 
* Se crea un **clon de la base de datos de 100 TB en cuestión de segundos** 
* Las pruebas de actualización se realizan **sin afectar el sistema en vivo**

### 2. **Instantáneas por hora** 
* Se determina **qué paso ha estado fallando desde cuándo** durante el proceso de actualización 
* Las operaciones problemáticas se **identifican de antemano** y se corrigen

### 3. **Actualización perfecta** 
* Si la actualización falla, **el entorno en vivo no se ve afectado** 
* Si la actualización se realiza correctamente, el nuevo entorno en vivo se convierte en el último clon.

## Resultado

**Ahorro de tiempo y costos:** 
* El tiempo de respaldo se redujo de **7 días a 10 segundos**

**Actualización sin riesgos:** 
* Los errores se detectaron de antemano en el entorno de prueba → **No hay problemas en el sistema en vivo**

**Tiempo de inactividad cero:** 
* Los clientes y empleados **no sintieron ninguna interrupción**