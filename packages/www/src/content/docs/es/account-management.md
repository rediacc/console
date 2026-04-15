---
title: "Gestión de cuentas"
description: "Organizaciones, equipos, miembros y suscripciones en Rediacc."
category: Guides
order: 12
language: es
sourceHash: "e32952a1485133e0"
sourceCommit: "a97009927c347f7090e4f4f60f3948997654ae4b"
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
# Desde el portal: Organización > Miembros > Invitar
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

| Plan | Máquinas | Licencias de repo/mes | Validez cert. delegación pred. / máx. | Características |
|------|----------|------------------------|---------------------------------------|-----------------|
| COMMUNITY | 2 | 500 | 15d / 30d | Básico |
| PROFESSIONAL | 5 | 5.000 | 60d / 120d | Grupos de permisos, registro de auditoría, marca personalizada, soporte prioritario |
| BUSINESS | 20 | 20.000 | 90d / 180d | Ceph, analíticas avanzadas, prioridad de cola, cola avanzada |
| ENTERPRISE | 50 | 100.000 | 120d / 365d | Gestor de cuenta dedicado |

![Subscription Flow](/img/account-subscription-flow.svg)

Todos los planes comienzan con un período de gracia de 3 días. Las activaciones de máquinas se registran por equipo y se liberan automáticamente tras la inactividad. Consulta [Suscripción y licencias](/es/docs/subscription-licensing) para el modelo completo de licencias de máquina frente a licencias de repositorio.

### Facturación

Solo el **Owner** de la organización puede gestionar la facturación:
- Crear una sesión de pago en Stripe para mejoras de plan
- Acceder al portal de facturación de Stripe para cambiar el método de pago
- Solicitar reembolsos de autoservicio (dentro de 14 días, con un período de espera de 30 días)

### Región de datos

Tu cuenta se almacena en la región de datos que seleccionaste al registrarte (EU, US o Asia Pacífico). Esta elección es permanente. El distintivo de región en el portal muestra en qué región residen tus datos. Consulta [Regiones de datos](/es/docs/data-regions) para más detalles.

### Canal Edge

Si tu cuenta está en el canal Edge, verás un distintivo "Edge" en la barra lateral del portal. Las cuentas Edge tienen el doble de los límites de Community pero sin acceso a planes de pago. Consulta [Canales de lanzamiento](/es/docs/release-channels) para conocer las diferencias entre Edge y Stable.

### Certificados de delegación

Para implementaciones on-premise y air-gapped, puedes gestionar tus propios certificados de delegación desde el portal de cliente en **/account/delegation-certs**. La página es visible para todos los clientes independientemente del nivel de plan; solo difieren los valores predeterminados de validez por nivel.

#### Control de acceso por rol

| Acción | Org Owner | Org Admin | Member |
|--------|-----------|-----------|--------|
| Listar / ver / descargar certificados | ✓ | ✓ | ✓ |
| Crear nuevo certificado | ✓ | ✓ | ✗ |
| Revocar certificado | ✓ | ✓ | ✗ |
| Emitir token de auto-renovación | ✓ | ✓ | ✗ |
| Procesar solicitud de renovación air-gapped | ✓ | ✓ | ✗ |

Los Members pueden ver la lista y descargar certificados existentes (útil para distribuir el certificado a un conjunto de máquinas), pero solo los owners y admins pueden emitirlos o revocarlos.

#### Restricción de certificado único activo

Una suscripción solo puede tener **un certificado de delegación activo a la vez**. Cada instalación on-premise aplica cuotas mensuales y por máquina contra su propio libro de contabilidad local; múltiples certificados activos multiplicarían la cuota efectiva sin posibilidad de reconciliación.

Si intentas crear un segundo certificado mientras uno ya está activo, el portal muestra un diálogo con dos opciones:

- **Renovar (recomendado)** - extiende la cadena existente. Todas las licencias de repositorio emitidas anteriormente siguen funcionando bajo el certificado renovado. Úsalo al rotar un certificado que va a expirar en la misma instalación on-premise.
- **Revocar y crear nuevo** - descarta la cadena existente y comienza de nuevo desde el origen. Las licencias de repositorio emitidas previamente dejarán de ser verificables una vez que pase el `validUntil` del certificado ANTIGUO. Úsalo solo cuando hayas migrado a una nueva instalación on-prem con una clave de firma diferente, o cuando te estés recuperando de una clave comprometida.

Si necesitas entornos separados (producción + staging + DR + multirregión), adquiere una suscripción por instalación.

#### Bootstrap de auto-renovación

Para habilitar la auto-renovación on-premise, haz clic en **Get auto-renew token** en la página de Certificados de delegación. Esto emite un token de API con alcance `delegation:renew` (perpetuo, sin expiración) y te muestra los valores que debes pegar en tu `.env` on-premise:

```
UPSTREAM_URL=https://www.rediacc.com
UPSTREAM_API_KEY=rdt_<token>
```

El token otorga **únicamente** la renovación de certificados de delegación; no puede leer ni modificar ningún otro recurso. Este es el único camino para emitir un token `delegation:renew`; el flujo habitual de `/portal/api-tokens` no incluye este alcance.

#### Renovación air-gapped

Si tu instalación on-premise no tiene acceso HTTPS de salida, usa el flujo de manifiesto offline:

1. En la página de administración on-premise, haz clic en **Download renewal request**. La instalación on-premise genera un manifiesto firmado que contiene el encabezado de tu cadena local.
2. Transfiere el manifiesto al upstream (USB, correo cifrado, cualquier canal).
3. En el portal upstream, haz clic en **Upload renewal request** y selecciona el manifiesto. El upstream verifica la firma del manifiesto, emite un nuevo certificado y lo devuelve como un `.json` descargable.
4. Transfiere el nuevo certificado de vuelta a la instalación on-premise y súbelo a través de la página de administración on-premise.

El upstream rechaza manifiestos con más de 7 días de antigüedad. Consulta [Instalación on-premise](/es/docs/on-premise) para la configuración paso a paso completa y [Cadena de licencias y delegación](/es/docs/license-chain) para el diseño criptográfico.

#### Límite de velocidad

La creación de certificados está limitada a **10 intentos por 24 horas continuas** por suscripción, incluidos los intentos fallidos (spam de colisión, entrada inválida). Si alcanzas el límite, el portal muestra un valor `Retry-After` que indica cuándo puedes intentarlo de nuevo.
