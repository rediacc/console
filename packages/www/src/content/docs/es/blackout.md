---
title: Continuidad bancaria durante el apagón
description: >-
  Mantenga las operaciones bancarias durante cortes de energía con duplicación
  de datos intercontinental.
category: Use Cases
tags:
  - backup
  - migration
subcategory: resilience
order: 6
language: es
sourceHash: "8817b7a0a9304cd0"
sourceCommit: "b8e332b73573133a282b5c508bc049af1fbeb581"
---

> **Cuando se apagan las luces, su negocio permanece encendido.**

**Nota:** Este es un **ejemplo de caso de uso** que demuestra cómo Rediacc puede resolver este problema. Como startup, estos escenarios representan aplicaciones potenciales en lugar de estudios de casos completos.

**Escenario de crisis:** Un apagón masivo afectó a España y Portugal el 28 de abril de 2025, provocado por una línea de transmisión dañada en Francia. El corte de energía derribó la infraestructura de TI crítica, lo que provocó que los principales bancos y empresas de tecnología perdieran el acceso a sus sistemas.

## El problema

La red eléctrica ibérica se enfrentó a una cascada de fallos catastróficos:

* Un **incendio en el suroeste de Francia** dañó una línea de transmisión crítica 
* Los daños provocados por la **desconexión repentina** de las interconexiones transfronterizas 
* España y Portugal quedaron **aislados eléctricamente** de la red europea

**Impacto en las empresas:** 
* Los centros de datos en toda España experimentaron **pérdida de energía inmediata** 
* Los generadores de respaldo no se activaron en varias ubicaciones debido a fallas en el sistema de control. 
* Los sistemas bancarios se desconectaron, impidiendo transacciones en todo el país.

**Desafíos de la infraestructura de TI:** 
* **Los sistemas de respaldo locales** fueron ineficaces ya que estaban ubicados en la misma región afectada 
* **Procedimientos de recuperación de emergencia** dependían del acceso local a servidores físicos 
* **Los planes de continuidad del negocio** no tuvieron en cuenta el corte de energía a nivel nacional que duró más de 4 horas

## Impacto de la crisis

La interrupción del servicio de TI provocó: 
* **Colapso del sistema financiero** con retrasos en las transacciones estimados en 4.500 millones de euros 
* Los datos comerciales críticos se vuelven inaccesibles durante más de 14 horas 
* Las principales plataformas de comercio electrónico experimentan un cierre total 
* Los sistemas de servicio al cliente fallan en múltiples industrias

## Solución Rediacc

Un importante grupo bancario español que implementó la solución de replicación transcontinental de Rediacc mantuvo operaciones durante toda la crisis:

![Banking Continuity During Blackout](/img/blackout-continuity.svg)

### 1. **Duplicación de datos intercontinental** 
* Las bases de datos bancarias centrales y los sistemas de transacciones se **replicarían continuamente** en centros de datos en los Estados Unidos 
* Los datos de los clientes y los registros de transacciones se mantendrían sincronizados dentro del retraso de replicación que permitan su enlace y su volumen de datos

### 2. **Transición operativa perfecta** 
* Si los servidores españoles se quedaran sin energía, el tráfico se **redireccionaría automáticamente** a los sistemas con sede en EE. UU. 
* Los clientes notarían solo una breve interrupción mientras se completa la redirección, en lugar de una caída tan larga como el propio apagón de la red

### 3. **Continuación del servicio remoto** 
* Los centros de llamadas en países no afectados podrían acceder a los sistemas replicados y seguir atendiendo a los clientes 
* Las aplicaciones de banca móvil seguirían funcionando al conectarse a centros de datos alternativos

## Resultado potencial

**Continuidad del negocio:** 
* Los competidores estuvieron sin servicio más de 14 horas. Un banco con esta arquitectura seguiría operando durante toda esa ventana

**Continuidad del servicio:** 
* Podría seguir procesando transacciones mientras las instituciones sin una segunda región no podrían hacerlo

**Protección financiera:** 
* Se evitarían las pérdidas por fallos de transacciones que se acumulan por cada hora que un sistema de pagos está caído 
* No se perderían ni corromperían datos, por lo que no haría falta ninguna operación de recuperación
