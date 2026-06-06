---
title: "Cumplimiento de SOC 2"
description: "Aquí está el punto sobre SOC 2: los auditores quieren evidencia de que tus controles funcionan. Rediacc te proporciona los registros, el rastro de gestión de cambios y todo lo demás que van a pedir."
category: "Legal"
order: 2
language: es
sourceHash: "27d2366f84e21d8c"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

Sé qué es SOC 2 porque he asistido a reuniones de auditoría. Los auditores utilizan el marco de la AICPA para verificar que tus controles realmente funcionan, no solo si dices que funcionan. Cinco Criterios de Servicio de Confianza: seguridad, disponibilidad, integridad del procesamiento, confidencialidad y privacidad.

Referencia: [AICPA SOC 2](https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2)

## Mapeo de Criterios de Servicio de Confianza

| Principio de confianza | Criterio | Capacidad de Rediacc |
|-----------------------|----------|---------------------|
| **Seguridad** (CC6) | Controles de acceso lógico, cifrado | Cifrado LUKS2 AES-256 en reposo. Credenciales almacenadas solo en la configuración local del operador (`~/.config/rediacc/`), nunca en el servidor. Acceso basado en clave SSH. Docker daemons aislados por repositorio. |
| **Disponibilidad** (A1) | Recuperación y resiliencia del sistema | `rdc repo push/pull` con copias cifradas fuera del sitio a SSH, S3, B2, Azure o GDrive. Snapshots CoW para rollback instantáneo. Actualizaciones basadas en fork para cambios sin tiempo de inactividad. |
| **Integridad del procesamiento** (PI1) | Procesamiento preciso y completo | Los hooks de ciclo de vida determinísticos del Rediaccfile (`up`/`down`) aseguran despliegues consistentes. `rdc repo validate` verifica la integridad del repositorio y la salud del respaldo después de apagados inesperados u operaciones de respaldo. |
| **Confidencialidad** (C1) | Protección de datos contra acceso no autorizado | Cifrado por repositorio con credenciales LUKS únicas. Aislamiento de red vía iptables, Docker daemons separados y subredes de IP loopback. Los contenedores de diferentes repositorios no pueden verse entre sí. El almacén de configuración de conocimiento cero cifra las configuraciones del lado del cliente antes de subirlas. El servidor solo almacena blobs opacos que no puede descifrar. |
| **Privacidad** (P1-P8) | Manejo de datos personales | Autoalojado: sin egreso de datos durante operaciones. Rastro de auditoría para todo acceso a datos. Gestión de claves de cifrado bajo control del cliente. El almacén de configuración usa derivación de clave dividida (passkey PRF + secreto del servidor) para que ninguna parte pueda acceder a los datos por sí sola. |

## Rastro de auditoría

Así que Rediacc registra más de 70 tipos de eventos diferentes. Acciones de usuario, cambios del sistema, actualizaciones de configuración, modificaciones de control de acceso, eventos de seguridad, operaciones de fork, rastros de auditoría. Sé que suena como mucho, pero a los auditores realmente les importa ver esto.

- **Autenticación**: inicio de sesión, cierre de sesión, cambios de contraseña, habilitación/deshabilitación de 2FA, revocación de sesiones
- **Autorización**: creación/revocación de tokens API, cambios de roles, membresía de equipos
- **Configuración**: push/pull del almacén de configuración, gestión de miembros, fallos de acceso (discrepancia de IP, denegación de SDK)
- **Licencias**: emisión de licencias de repositorio, seguimiento de ranuras de máquina, cambios de suscripción
- **Operaciones de máquina**: crear/iniciar/detener/eliminar repositorio, fork, push/pull de respaldo, sincronización de archivos, sesiones de terminal

Tres formas de obtener estos registros. Panel de administración con filtrado por usuario, equipo y fecha. Página de actividad del portal para administradores de organizaciones, filtrado por tipo y fecha. O la CLI `rdc audit` para exportación programática. Canalízalos a tus propias herramientas, intégralos donde quieras. Las operaciones de máquina también se registran en tus registros del sistema, así que tienes defensa en profundidad.

## Gestión de cambios

Los forks hacen que la gestión de cambios sea auditable: cada fork es una copia del estado en vivo contra la que puedes probar, revisar, y luego promover o descartar, con cada paso con marca de tiempo asignada a un actor.

1. Hacer fork de un repositorio de producción (`rdc repo fork`)
2. Aplicar y probar cambios en el fork
3. Validar el fork de forma independiente
4. Promover el fork a producción (`rdc repo takeover`)

Cada paso: registrado. Con marca de tiempo. Vinculado a una persona. Sin 'no sé quién cambió eso'.

## Control de acceso

- **Acceso a máquinas**: Solo autenticación con clave SSH. Sin SSH basado en contraseña.
- **Tokens API**: Permisos con alcance definido, vinculación IP opcional, revocación automática al remover del equipo.
- **Aislamiento de repositorios**: Cada repositorio tiene su propio socket de Docker daemon. El acceso a un repositorio no otorga acceso a otro en la misma máquina.
- **Tokens del almacén de configuración**: Tokens rotativos de un solo uso con vinculación IP en el primer uso, expiración automática de 24 horas y ventana de gracia de 3 solicitudes para concurrencia. Acceso de miembros gestionado vía intercambio de claves X25519 con revocación inmediata.
