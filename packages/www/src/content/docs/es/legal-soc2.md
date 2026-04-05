---
title: "Cumplimiento de SOC 2"
description: "Cómo Rediacc se ajusta a los Criterios de Servicio de Confianza de SOC 2 para seguridad, disponibilidad y confidencialidad."
category: "Legal"
order: 2
language: es
sourceHash: "96eff23962051882"
---

SOC 2 (Controles de Sistema y Organización 2) es un marco desarrollado por el Instituto Americano de Contadores Públicos Certificados (AICPA) para evaluar los controles de una organización relacionados con seguridad, disponibilidad, integridad del procesamiento, confidencialidad y privacidad.

Referencia: [AICPA SOC 2](https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2)

## Mapeo de Criterios de Servicio de Confianza

| Principio de confianza | Criterio | Capacidad de Rediacc |
|-----------------------|----------|---------------------|
| **Seguridad** (CC6) | Controles de acceso lógico, cifrado | Cifrado LUKS2 AES-256 en reposo. Credenciales almacenadas solo en la configuración local del operador (`~/.config/rediacc/`), nunca en el servidor. Acceso basado en clave SSH. Docker daemons aislados por repositorio. |
| **Disponibilidad** (A1) | Recuperación y resiliencia del sistema | `rdc repo backup push/pull` con copias cifradas fuera del sitio a SSH, S3, B2, Azure o GDrive. Snapshots CoW para rollback instantáneo. Actualizaciones basadas en fork para cambios sin tiempo de inactividad. |
| **Integridad del procesamiento** (PI1) | Procesamiento preciso y completo | Los hooks de ciclo de vida determinísticos del Rediaccfile (`up`/`down`) aseguran despliegues consistentes. `rdc repo validate` verifica la integridad del repositorio y la salud del respaldo después de apagados inesperados u operaciones de respaldo. |
| **Confidencialidad** (C1) | Protección de datos contra acceso no autorizado | Cifrado por repositorio con credenciales LUKS únicas. Aislamiento de red vía iptables, Docker daemons separados y subredes de IP loopback. Los contenedores de diferentes repositorios no pueden verse entre sí. El almacén de configuración de conocimiento cero cifra las configuraciones del lado del cliente antes de subirlas. El servidor solo almacena blobs opacos que no puede descifrar. |
| **Privacidad** (P1-P8) | Manejo de datos personales | Autoalojado: sin egreso de datos durante operaciones. Rastro de auditoría para todo acceso a datos. Gestión de claves de cifrado bajo control del cliente. El almacén de configuración usa derivación de clave dividida (passkey PRF + secreto del servidor) para que ninguna parte pueda acceder a los datos por sí sola. |

## Rastro de auditoría

Rediacc registra más de 40 tipos de eventos a nivel de cuenta que cubren:

- **Autenticación**: inicio de sesión, cierre de sesión, cambios de contraseña, habilitación/deshabilitación de 2FA, revocación de sesiones
- **Autorización**: creación/revocación de tokens API, cambios de roles, membresía de equipos
- **Configuración**: push/pull del almacén de configuración, gestión de miembros, fallos de acceso (discrepancia de IP, denegación de SDK)
- **Licencias**: activación de máquinas, emisión de licencias, cambios de suscripción

Estos registros son accesibles a través del panel de administración (con filtrado por usuario, equipo y fecha) y `rdc audit` CLI para exportación programática. Las operaciones a nivel de máquina (fork, respaldo, despliegue) se ejecutan por SSH en tu infraestructura, por lo que esos rastros de auditoría residen en tus registros del sistema.

## Gestión de cambios

El flujo de trabajo basado en fork soporta gestión de cambios controlada:

1. Hacer fork de un repositorio de producción (`rdc repo fork`)
2. Aplicar y probar cambios en el fork
3. Validar el fork de forma independiente
4. Promover el fork a producción (`rdc repo takeover`)

Cada paso se registra con marcas de tiempo e identificación del actor.

## Control de acceso

- **Acceso a máquinas**: Solo autenticación con clave SSH. Sin SSH basado en contraseña.
- **Tokens API**: Permisos con alcance definido, vinculación IP opcional, revocación automática al remover del equipo.
- **Aislamiento de repositorios**: Cada repositorio tiene su propio socket de Docker daemon. El acceso a un repositorio no otorga acceso a otro en la misma máquina.
- **Tokens del almacén de configuración**: Tokens rotativos de un solo uso con vinculación IP en el primer uso, expiración automática de 24 horas y ventana de gracia de 3 solicitudes para concurrencia. Acceso de miembros gestionado vía intercambio de claves X25519 con revocación inmediata.
