---
title: "NIS2 y DORA"
description: "Cómo Rediacc aborda la directiva de ciberseguridad NIS2 de la UE y los requisitos de resiliencia operativa digital de DORA."
category: "Legal"
order: 8
language: es
sourceHash: "be77425c2d3b38d2"
---

NIS2 y DORA son regulaciones de la UE que imponen requisitos de ciberseguridad y resiliencia operativa a organizaciones de infraestructura critica y del sector financiero. Ambas entraron en vigor en 2025 y se aplican ampliamente en las industrias de la UE.

## Directiva NIS2

La Directiva de Seguridad de Redes e Información 2 (NIS2) establece requisitos de ciberseguridad para entidades "esenciales" e "importantes" en sectores como energia, transporte, salud, infraestructura digital y administracion publica.

Texto completo: [Directiva (UE) 2022/2555](https://eur-lex.europa.eu/eli/dir/2022/2555/oj)

### Mapeo de requisitos NIS2

| Requisito NIS2 | Capacidad de Rediacc |
|---------------|---------------------|
| Medidas de gestion de riesgos (Art. 21) | Cifrado LUKS2 en reposo, aislamiento de red por repositorio, acceso solo SSH, registro de auditoria a nivel de cuenta (40+ tipos de eventos) |
| Manejo de incidentes (Art. 21(2)(b)) | 40+ tipos de eventos (autenticacion, tokens, configuracion, licencias) proporcionan rastro forense. Aislamiento por repositorio limita el radio de impacto. |
| Continuidad del negocio (Art. 21(2)(c)) | `rdc repo backup push/pull` con respaldo cifrado a multiples destinos. Snapshots CoW para rollback instantaneo. |
| Seguridad de la cadena de suministro (Art. 21(2)(d)) | El autoalojamiento elimina riesgos de cadena de suministro SaaS. Ningun proveedor de nube tercero procesa tus datos. |
| Seguridad de red (Art. 21(2)(e)) | Docker daemons por repositorio, reglas iptables, aislamiento de IP loopback (subredes /26). |
| Cifrado (Art. 21(2)(h)) | Cifrado LUKS2 AES-256 obligatorio. Almacen de configuracion de conocimiento cero con AES-256-GCM. |
| Control de acceso (Art. 21(2)(i)) | Autenticacion por clave SSH, tokens API con alcance definido y vinculacion IP, autenticacion de dos factores (TOTP). |
| Reporte de incidentes, alerta temprana 24h (Art. 23) | El registro de auditoria permite la deteccion y delimitacion rapida de incidentes. |

### Riesgo de cadena de suministro

La seguridad de la cadena de suministro es una preocupacion central de NIS2 (Art. 21(2)(d)). Las organizaciones deben evaluar y gestionar riesgos de sus proveedores de servicios TIC y suministradores.

Rediacc autoalojado elimina la mayor superficie de ataque de la cadena de suministro: ningun SaaS tercero maneja tus datos, ningun proveedor de nube tiene acceso logico a tu infraestructura, y ningun entorno multi-tenant crea exposicion a la postura de seguridad de otros clientes. [El ataque de ransomware a Blackbaud en 2020 expuso datos de mas de 13,000 organizaciones clientes, costando 49.5 millones de dolares en acuerdos.](https://www.sec.gov/newsroom/press-releases/2023-48)

---

## DORA (Ley de Resiliencia Operativa Digital)

DORA establece requisitos para gestion de riesgos TIC, reporte de incidentes, pruebas de resiliencia y gestion de riesgos de terceros para el sector financiero de la UE. Se aplica a bancos, companias de seguros, firmas de inversion, proveedores de servicios de criptoactivos y sus proveedores criticos de TIC terceros.

Texto completo: [Reglamento (UE) 2022/2554](https://eur-lex.europa.eu/eli/reg/2022/2554/oj)

### Mapeo de requisitos DORA

| Requisito DORA | Capacidad de Rediacc |
|---------------|---------------------|
| Marco de gestion de riesgos TIC (Art. 6) | Cifrado, aislamiento, registro de auditoria y respaldo forman la capa de controles tecnicos. |
| Proteccion y prevencion (Art. 9) | Cifrado LUKS2 AES-256 en reposo. Aislamiento de red previene movimiento lateral. Acceso solo SSH. |
| Deteccion (Art. 10) | 40+ tipos de eventos a nivel de cuenta. Panel de administracion con filtrado por usuario y equipo. Operaciones de maquina auditables via SSH y registros del sistema. |
| Respuesta y recuperacion (Art. 11) | Snapshots CoW para rollback instantaneo. `rdc repo backup push/pull` para recuperacion multi-destino. Pruebas de recuperacion ante desastres basadas en fork. |
| Riesgo TIC de terceros (Art. 28-30) | El autoalojamiento elimina completamente la clasificacion de "proveedor critico de TIC tercero". |
| Pruebas de resiliencia operativa digital (Art. 24-27) | La clonacion CoW permite pruebas de penetracion dirigidas por amenazas en entornos similares a produccion sin exposicion de datos. Clonar, probar, destruir. |

### Riesgo de proveedores TIC terceros

Los requisitos mas gravosos de DORA son sobre la gestion de proveedores criticos de TIC terceros (Art. 28-30). Las instituciones financieras deben mantener registros de proveedores TIC, realizar evaluaciones de riesgo, negociar provisiones contractuales especificas y planificar estrategias de salida.

Rediacc autoalojado evita esto completamente. Ningun proveedor TIC tercero que registrar, evaluar o monitorear. La institucion financiera controla su propia infraestructura directamente.

### Pruebas de resiliencia

DORA exige pruebas de resiliencia operativa digital, incluyendo pruebas de penetracion dirigidas por amenazas (TLPT) para grandes instituciones (Art. 26). La clonacion CoW maneja esto directamente:

1. Fork del entorno de produccion (instantaneo, misma maquina, sin transferencia de datos)
2. Ejecutar pruebas de penetracion contra el fork
3. Destruir el fork al finalizar

La produccion nunca se toca, pero el entorno de prueba es una replica exacta. Ningun dato sale de la maquina.
