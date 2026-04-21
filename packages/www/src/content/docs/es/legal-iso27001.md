---
title: "Cumplimiento de ISO 27001"
description: "Cómo Rediacc se ajusta a los controles de seguridad de la información de ISO 27001 para cifrado, gestión de acceso y seguridad operativa."
category: "Legal"
order: 5
language: es
sourceHash: "fa8c17a9c2914241"
---

ISO/IEC 27001 es un estándar internacional para sistemas de gestión de seguridad de la información (SGSI), publicado por la Organización Internacional de Normalización (ISO) y la Comisión Electrotécnica Internacional (IEC). La versión actual es ISO/IEC 27001:2022.

Referencia: [ISO/IEC 27001:2022](https://www.iso.org/standard/27001)

Rediacc es un componente de la capa de controles técnicos dentro de un SGSI. La tabla a continuación mapea las capacidades de Rediacc a los dominios de control del Anexo A relevantes.

## Mapeo de controles del Anexo A

| Dominio de control | Control | Capacidad de Rediacc |
|-------------------|---------|---------------------|
| **A.8**, Gestión de activos | A.8.1 Inventario de activos | Cada repositorio es un activo discreto e identificable con un GUID único. `rdc machine query --name <machine> --repositories` lista todos los repositorios con tamaño, estado de montaje y cantidad de contenedores. |
| **A.8**, Gestión de activos | A.8.24 Uso de criptografía | Cifrado LUKS2 AES-256 obligatorio en todos los repositorios. Gestión de claves: credenciales almacenadas solo en la configuración local del operador, nunca en el servidor. |
| **A.9**, Control de acceso | A.9.2 Gestión de acceso de usuarios | Autenticación por clave SSH. Tokens API con vinculación IP, alcance por equipos y revocación automática al remover del equipo. Autenticación de dos factores (TOTP). |
| **A.10**, Criptografía | A.10.1 Controles criptográficos | LUKS2 con parámetros de clave configurables. Credenciales de cifrado por repositorio. Todo el transporte remoto por SSH. El almacén de configuración implementa cifrado de conocimiento cero: AES-256-GCM con derivación de clave HKDF, intercambio de claves X25519 para miembros y claves SDK con ventana temporal para revocación inmediata. |
| **A.12**, Seguridad operativa | A.12.3 Respaldo | `rdc repo backup push/pull` con almacenamiento cifrado fuera del sitio a múltiples destinos (SSH, S3, B2, Azure, GDrive). Snapshots CoW para recuperación en punto en el tiempo. `rdc repo validate` verifica la salud del respaldo y la integridad del repositorio. |
| **A.12**, Seguridad operativa | A.12.4 Registro y monitoreo | Más de 40 tipos de eventos a nivel de cuenta (autenticación, tokens API, configuración, licencias). Monitoreo de salud de máquinas vía `rdc machine query`. Monitoreo de estado de contenedores y recursos. |
| **A.13**, Seguridad de comunicaciones | A.13.1 Gestión de seguridad de red | Aislamiento de Docker daemon por repositorio. Reglas de iptables bloquean tráfico entre repositorios. Subredes de IP loopback (/26) por repositorio. Proxy inverso con terminación TLS para acceso externo. |
| **A.14**, Desarrollo de sistemas | A.14.2 Seguridad en el desarrollo | Entornos de desarrollo basados en fork proporcionan paridad con producción sin exposición de datos de producción. Los hooks del ciclo de vida de Rediaccfile permiten sanitización automatizada de datos en entornos clonados. |

## Gestión de activos

El modelo de repositorios de Rediacc soporta naturalmente los requisitos de inventario de activos:

- Cada repositorio tiene un GUID único asignado en la creación
- Los repositorios son enumerables por máquina (`rdc machine query --repositories`)
- El estado de cifrado, estado de montaje, cantidad de contenedores y uso de disco de cada repositorio son visibles
- Las relaciones de fork rastrean el linaje de entornos clonados

## Gestión de cambios

El flujo de trabajo fork-test-promote se alinea con los requisitos de gestión de cambios de ISO 27001:

1. **Fork**: Crear una copia aislada del entorno de producción
2. **Test**: Aplicar y validar cambios en el fork
3. **Promover**: Usar `rdc repo takeover` para intercambiar el fork a producción
4. **Auditoría**: Todas las operaciones se registran con marcas de tiempo e identificación del actor

## Mejora continua

- La exportación de registros de auditoría soporta revisiones de seguridad periódicas
- Las verificaciones de salud de máquinas (`rdc machine query --system`) soportan monitoreo operativo
- `rdc repo validate` verifica la salud del respaldo después de cada operación
