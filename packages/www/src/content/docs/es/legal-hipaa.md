---
title: "Cumplimiento de HIPAA"
description: "Cómo la arquitectura de cifrado y aislamiento de Rediacc se ajusta a los requisitos de salvaguardas de HIPAA para proteger información de salud."
category: "Legal"
order: 3
language: es
sourceHash: "f5fbdaa4a00491ea"
sourceCommit: "43aec6b89a55f69f994476d3a124e749d4d2223f"
---

La Ley de Portabilidad y Responsabilidad del Seguro de Salud (HIPAA) es una ley federal de los Estados Unidos que establece estándares para proteger la información sensible de salud de los pacientes (PHI). Se aplica a entidades cubiertas (proveedores de atención médica, planes de salud, cámaras de compensación) y sus socios comerciales.

Texto completo: [Ley Pública 104-191](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm)

## Mapeo de salvaguardas

HIPAA requiere salvaguardas administrativas, técnicas y físicas. La tabla a continuación las mapea a las capacidades de Rediacc.

### Salvaguardas técnicas

| Requisito | Referencia HIPAA | Capacidad de Rediacc |
|-----------|-----------------|---------------------|
| Control de acceso | [45 CFR 164.312(a)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Autenticación basada en clave SSH. Tokens API con vinculación IP y restricciones de alcance. Aislamiento de Docker daemon por repositorio previene acceso entre repositorios. |
| Controles de auditoría | [45 CFR 164.312(b)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Más de 40 tipos de eventos a nivel de cuenta que cubren autenticación, tokens API, operaciones de configuración y licencias. Rastreo por usuario y equipo. Exportación vía panel de administración o `rdc audit` CLI. |
| Controles de integridad | [45 CFR 164.312(c)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Los snapshots CoW preservan datos originales antes de modificaciones. `rdc repo validate` verifica la integridad del repositorio y salud del respaldo (contenedor LUKS, consistencia del sistema de archivos, configuración). |
| Cifrado en reposo | [45 CFR 164.312(a)(2)(iv)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Cifrado LUKS2 AES-256 en todos los volúmenes de repositorios. Credenciales almacenadas solo en la configuración local del operador, nunca en el servidor. El almacén de configuración usa cifrado de conocimiento cero AES-256-GCM con derivación de clave dividida. Ni siquiera el servidor puede descifrar las configuraciones almacenadas. |
| Seguridad de transmisión | [45 CFR 164.312(e)](https://www.govinfo.gov/content/pkg/PLAW-104publ191/html/PLAW-104publ191.htm) | Todas las operaciones remotas usan SSH. El transporte de respaldo está cifrado de extremo a extremo. Sin transferencia de datos sin cifrar. |

### Salvaguardas administrativas

| Requisito | Capacidad de Rediacc |
|-----------|---------------------|
| Gestión de acceso del personal | Tokens API con permisos de alcance definido. Control de acceso basado en equipos. Revocación automática de tokens al remover del equipo. |
| Procedimientos de incidentes de seguridad | Los registros de auditoría proporcionan rastro forense de todas las operaciones. El aislamiento por repositorio limita el radio de impacto. |
| Planificación de contingencia | `rdc repo push/pull` soporta respaldo cifrado a múltiples destinos. Los snapshots CoW permiten recuperación instantánea. |

### Salvaguardas físicas

| Requisito | Capacidad de Rediacc |
|-----------|---------------------|
| Controles de acceso a instalaciones | Autoalojado: tu organización controla la seguridad física de tus servidores. Sin dependencia de centros de datos de terceros para operaciones principales. |
| Seguridad de estaciones de trabajo | LUKS cifra todos los datos en reposo. Los repositorios no montados son blobs cifrados en disco, ilegibles sin las credenciales del operador. |

## Acuerdo de socio comercial (BAA)

Dado que Rediacc es software autoalojado que se ejecuta en tu infraestructura, no procesa, almacena ni transmite PHI a través de los sistemas de Rediacc (la empresa). El requisito típico de BAA se aplica a tu proveedor de infraestructura (proveedor de nube o instalación de colocación), no a Rediacc.

Rediacc opera como una herramienta de software en tus servidores, similar a un sistema operativo o motor de base de datos. No tiene acceso a tus datos. El almacén de configuración opcional sincroniza blobs cifrados a través de los servidores de Rediacc, pero su diseño de conocimiento cero significa que el servidor no puede descifrar los contenidos. Solo almacena texto cifrado opaco.

## Entornos de desarrollo con PHI

Al clonar entornos de producción que contienen PHI para propósitos de desarrollo, usa el hook del ciclo de vida `up()` del Rediaccfile para ejecutar scripts de sanitización que:

- Eliminan PHI de las tablas de la base de datos
- Reemplazan identificadores de pacientes con datos sintéticos
- Remueven tokens de sesión y claves API

Los desarrolladores obtienen infraestructura similar a producción con datos desidentificados, satisfaciendo el estándar de mínimo necesario de HIPAA.
