---
title: Gestión de cuentas
description: Organizaciones, equipos, miembros y suscripciones en Rediacc.
category: Guides
order: 12
language: es
sourceHash: "cc3200205666febe"
sourceCommit: "dabe1a33844b3b7ec8a2c4ab44dc2de6683283c9"
---

### Organizaciones

Al registrarte, Rediacc crea automáticamente una organización para ti. Tu organización es el contenedor principal de todos los recursos -- máquinas, repositorios, suscripciones y miembros del equipo.

![Registration Flow](/img/account-registration-flow.svg)

Cada organización tiene:
- Un nombre único (por defecto tu correo electrónico)
- Un plan de suscripción (comienza con COMMUNITY)
- Un equipo predeterminado (todos los miembros se unen automáticamente)

### Miembros y Roles

Las organizaciones admiten tres roles:

![Role Hierarchy](/img/account-role-hierarchy.svg)

| Rol | Capacidades |
|-----|-------------|
| **Owner** | Control total: facturación, transferencia de propiedad, gestión de todos los miembros y equipos |
| **Admin** | Invitar y eliminar miembros, crear y gestionar equipos, revocar tokens de API |
| **Member** | Ver datos de la organización, crear tokens de API, acceder a equipos asignados |

Invitar miembros:
```bash
# A través del portal: Organización > Miembros > Invitar
# O mediante la API
```

Cuando se elimina un miembro, sus tokens de API y tokens de config storage se revocan automáticamente.

### Equipos

Los equipos permiten acotar recursos dentro de una organización. Cada organización comienza con un equipo predeterminado.

![Team Structure](/img/account-team-structure.svg)

Roles de equipo:
- **Team Admin**: Puede agregar/eliminar miembros dentro del equipo
- **Member**: Puede acceder a recursos del ámbito del equipo

Los propietarios y administradores de la organización tienen acceso automático a todos los equipos sin necesidad de membresía explícita.

### Suscripciones y Planes

Rediacc ofrece cuatro planes:

| Plan | Máquinas | Licencias de repo/mes | Características |
|------|----------|------------------------|-----------------|
| COMMUNITY | 2 | 500 | Básico |
| PROFESSIONAL | 10 | 2.000 | Grupos de permisos, prioridad en cola |
| BUSINESS | 25 | 5.000 | Ceph, analíticas avanzadas, registro de auditoría |
| ENTERPRISE | Ilimitado | Ilimitado | Marca personalizada, cuenta dedicada |

![Subscription Flow](/img/account-subscription-flow.svg)

Todos los planes comienzan con un período de gracia de 3 días. Las activaciones de máquinas se registran por equipo y se liberan automáticamente tras inactividad.

### Facturación

Solo el **owner** de la organización puede gestionar la facturación:
- Crear una sesión de pago en Stripe para mejoras de plan
- Acceder al portal de facturación de Stripe para cambiar el método de pago
- Solicitar reembolsos de autoservicio (dentro de 14 días, con un período de espera de 30 días)
