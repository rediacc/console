---
title: "NIS2 y DORA"
description: "Cómo Rediacc aborda la directiva de ciberseguridad NIS2 de la UE y los requisitos de resiliencia operativa digital de DORA."
category: "Legal"
tags:
  - compliance
subcategory: regulations
order: 8
language: es
sourceHash: "e1cdb4848a2124ae"
sourceCommit: "5f4fc4c93d74073e5a9b8f8431444495a7f641b6"
---

NIS2 y DORA son regulaciones de la UE que imponen requisitos de ciberseguridad y resiliencia operativa a organizaciones de infraestructura critica y del sector financiero. Ambas entraron en vigor en 2025 y se aplican ampliamente en las industrias de la UE.

## Directiva NIS2

La Directiva de Seguridad de Redes e Información 2 (NIS2) establece requisitos de ciberseguridad para entidades "esenciales" e "importantes" en sectores como energia, transporte, salud, infraestructura digital y administracion publica.

Texto completo: [Directiva (UE) 2022/2555](https://eur-lex.europa.eu/eli/dir/2022/2555/oj)

### Mapeo de requisitos NIS2

| Requisito NIS2 | Capacidad de Rediacc |
|---------------|---------------------|
| Medidas de gestion de riesgos (Art. 21) | Cifrado LUKS2 en reposo, aislamiento de red por repositorio, acceso solo SSH, registro de auditoria (70+ tipos de eventos incluyendo operaciones de máquina) |
| Manejo de incidentes (Art. 21(2)(b)) | Los registros de flujo de red por repositorio, en un nivel que elige el cliente (destino, puerto y protocolo; en niveles superiores proceso, nombre DNS y aperturas de archivos sensibles), se envían como lotes firmados y encadenados por hash a un bucket en el que los administradores del cliente no pueden escribir, solo en planes de pago. Una línea de tiempo de investigación por repositorio verifica la cadena en el navegador, y «Declare incident» inicia los relojes de plazo. Los registros de flujo muestran volumen y destino, no contenido. Los planes Free y Community no registran nada. El aislamiento por repositorio limita el radio de impacto. Los 70+ tipos de eventos de auditoría (autenticación, tokens, configuración, licencias, operaciones de máquina) registran quién hizo qué. |
| Continuidad del negocio (Art. 21(2)(c)) | `rdc repo push/pull` con respaldo cifrado a multiples destinos. Snapshots CoW para rollback instantaneo. |
| Seguridad de la cadena de suministro (Art. 21(2)(d)) | El autoalojamiento elimina riesgos de cadena de suministro SaaS. Ningun proveedor de nube tercero procesa tus datos. |
| Seguridad de red (Art. 21(2)(e)) | Docker daemons por repositorio, reglas iptables, aislamiento de IP loopback (subredes /26). |
| Cifrado (Art. 21(2)(h)) | Cifrado LUKS2 AES-256 obligatorio. Almacen de configuracion de conocimiento cero con AES-256-GCM. |
| Control de acceso (Art. 21(2)(i)) | Autenticacion por clave SSH, tokens API con alcance definido y vinculacion IP, autenticacion de dos factores (TOTP). |
| Reporte de incidentes, alerta temprana 24h (Art. 23) | «Declare incident» registra el momento en que se toma conocimiento y de él corren tres relojes: 24 horas para la alerta temprana, 72 horas para la notificación del incidente y un mes natural tras la notificación para el informe final (Art. 23(4)). Cada etapa se prepara como un informe firmado en PDF, JSON y STIX 2.1, con un mapa de campos de cada campo del informe a la Directiva. Valorar si un incidente es significativo, y qué se envía al CSIRT o a la autoridad competente, sigue siendo juicio y trámite del cliente. |

### Riesgo de cadena de suministro

La seguridad de la cadena de suministro es una preocupacion central de NIS2 (Art. 21(2)(d)). Las organizaciones deben evaluar y gestionar riesgos de sus proveedores de servicios TIC y suministradores.

Rediacc autoalojado elimina la mayor superficie de ataque de la cadena de suministro, y sí, sé que suena obvio. Aquí es por qué importa: ningun SaaS tercero maneja tus datos, ningun proveedor de nube tiene acceso logico a tu infraestructura, y ningun entorno multi-tenant crea exposicion a la postura de seguridad de otros clientes. Los incumplimientos de proveedores SaaS han causado daños en cascada en miles de organizaciones. [El ataque de ransomware a Blackbaud en 2020 expuso datos de mas de 13,000 organizaciones clientes, costando 49.5 millones de dolares en acuerdos.](https://www.sec.gov/newsroom/press-releases/2023-48)

---

## DORA (Ley de Resiliencia Operativa Digital)

DORA establece requisitos para gestion de riesgos TIC, reporte de incidentes, pruebas de resiliencia y gestion de riesgos de terceros para el sector financiero de la UE. Se aplica a bancos, companias de seguros, firmas de inversion, proveedores de servicios de criptoactivos y sus proveedores criticos de TIC terceros.

Texto completo: [Reglamento (UE) 2022/2554](https://eur-lex.europa.eu/eli/reg/2022/2554/oj)

### Mapeo de requisitos DORA

| Requisito DORA | Capacidad de Rediacc |
|---------------|---------------------|
| Marco de gestion de riesgos TIC (Art. 6) | Cifrado, aislamiento, registro de auditoria y respaldo forman la capa de controles tecnicos. |
| Proteccion y prevencion (Art. 9) | Cifrado LUKS2 AES-256 en reposo. Aislamiento de red previene movimiento lateral. Acceso solo SSH. |
| Deteccion (Art. 10) | Los detectores de anomalías se ejecutan en la máquina (también sin conexión) y en el servidor sobre los registros de flujo enviados, y emiten un aviso de seguridad ante tráfico inusual. Los detectores señalan desviaciones de una línea base aprendida por repositorio; no prueban una brecha y solo cubren repositorios con captura activa en un plan de pago. Los 70+ tipos de eventos de auditoría (ciclo de vida de repositorio, respaldo, sincronización, terminal) siguen disponibles con filtrado por usuario y equipo en el panel de administración y el portal, y en los registros del sistema para defensa en profundidad. |
| Respuesta y recuperacion (Art. 11) | Snapshots CoW para rollback instantaneo. `rdc repo push/pull` para recuperacion multi-destino. Pruebas de recuperacion ante desastres basadas en fork. |
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
