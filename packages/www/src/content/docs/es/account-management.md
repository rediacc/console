---
title: Gestion de cuentas
description: Organizaciones, equipos, miembros y suscripciones en Rediacc.
category: Guides
order: 12
language: es
---

### Organizaciones

Al registrarte, Rediacc crea automaticamente una organizacion para ti. Tu organizacion es el contenedor principal de todos los recursos -- maquinas, repositorios, suscripciones y miembros del equipo.

![Registration Flow](/img/account-registration-flow.svg)

Cada organizacion tiene:
- Un nombre unico (por defecto tu correo electronico)
- Un plan de suscripcion (comienza con COMMUNITY)
- Un equipo predeterminado (todos los miembros se unen automaticamente)

### Miembros y Roles

Las organizaciones admiten tres roles:

![Role Hierarchy](/img/account-role-hierarchy.svg)

| Rol | Capacidades |
|-----|-------------|
| **Owner** | Control total: facturacion, transferencia de propiedad, gestion de todos los miembros y equipos |
| **Admin** | Invitar y eliminar miembros, crear y gestionar equipos, revocar tokens de API |
| **Member** | Ver datos de la organizacion, crear tokens de API, acceder a equipos asignados |

Invitar miembros:
```bash
# From the portal: Organization > Members > Invite
# Or via API
```

Cuando se elimina un miembro, sus tokens de API y tokens de config storage se revocan automaticamente.

### Equipos

Los equipos permiten acotar recursos dentro de una organizacion. Cada organizacion comienza con un equipo predeterminado.

![Team Structure](/img/account-team-structure.svg)

Roles de equipo:
- **Team Admin**: Puede agregar/eliminar miembros dentro del equipo
- **Member**: Puede acceder a recursos del ambito del equipo

Los propietarios y administradores de la organizacion tienen acceso automatico a todos los equipos sin necesidad de membresia explicita.

### Suscripciones y Planes

Rediacc ofrece cuatro planes:

| Plan | Maquinas | Licencias de repo/mes | Caracteristicas |
|------|----------|------------------------|-----------------|
| COMMUNITY | 2 | 500 | Basico |
| PROFESSIONAL | 10 | 2.000 | Grupos de permisos, prioridad en cola |
| BUSINESS | 25 | 5.000 | Ceph, analiticas avanzadas, registro de auditoria |
| ENTERPRISE | Ilimitado | Ilimitado | Marca personalizada, cuenta dedicada |

![Subscription Flow](/img/account-subscription-flow.svg)

Todos los planes comienzan con un periodo de gracia de 3 dias. Las activaciones de maquinas se registran por equipo y se liberan automaticamente tras inactividad.

### Facturacion

Solo el **owner** de la organizacion puede gestionar la facturacion:
- Crear una sesion de pago en Stripe para mejoras de plan
- Acceder al portal de facturacion de Stripe para cambiar el metodo de pago
- Solicitar reembolsos de autoservicio (dentro de 14 dias, con un periodo de espera de 30 dias)
