---
title: Seguridad de cuenta y API
description: Autenticación, tokens de API, gestión de sesiones y el modelo de permisos.
category: Guides
order: 13
language: es
sourceHash: "c4e24e7a3494b6f6"
sourceCommit: "407174f41c12c0a2ee252a7812290c1ef9ecc9ca"
---

### Autenticación

Rediacc admite múltiples métodos de autenticación:

![Auth Flow](/img/account-auth-flow.svg)

- **Contraseña**: Inicio de sesión tradicional con correo electrónico y contraseña
- **Magic Link**: Inicio de sesión sin contraseña mediante enlace por correo (expira en 15 minutos)
- **Autenticación de dos factores (2FA)**: Basada en TOTP con códigos de respaldo

Cuando 2FA está habilitado, el inicio de sesión requiere tanto la contraseña (o magic link) como un código TOTP de 6 dígitos.

### Tokens de API

Los tokens de API autentican operaciones de máquina a máquina (activación de licencias CLI, verificaciones de estado).

![API Token Lifecycle](/img/account-api-token-lifecycle.svg)

**Alcances:**
- `license:read` -- Consultar el estado de suscripción y licencia
- `license:activate` -- Activar máquinas y emitir licencias de repositorio
- `subscription:read` -- Leer detalles de la suscripción

**Funciones de seguridad:**
- Vinculación de IP: la primera solicitud bloquea el token a esa dirección IP
- Alcance por equipo: los tokens pueden restringirse a un equipo específico
- Revocación automática: los tokens se revocan cuando el creador es eliminado de la organización

Crear un token:
```bash
# A través del portal: API Tokens > Create
# El valor del token se muestra una vez -- guárdelo de forma segura
```

### Flujo de código de dispositivo

La CLI puede autenticarse en máquinas sin pantalla utilizando el flujo de código de dispositivo:

![Device Code Flow](/img/account-device-code-flow.svg)

```bash
rdc config remote enable --headless
# Muestra: Ingrese el código XXXX-XXXX-XX en https://www.rediacc.com/account/authorize
# Después de la aprobación, la CLI recibe credenciales automáticamente
```

### Config Storage

Para configuración cifrada y sincronizada con el servidor, consulta [Config Storage](/es/docs/config-storage) para la guía completa. Config storage utiliza:
- Cifrado de conocimiento cero (el servidor nunca ve texto plano)
- Derivación de claves basada en passkey (WebAuthn + PRF)
- Tokens rotativos con rotación por solicitud

### Seguridad de sesión

| Tipo de token | Duración | Almacenamiento | Actualización |
|---------------|----------|----------------|---------------|
| Access Token (JWT) | 15 minutos | Cookie HttpOnly | Automático vía refresh token |
| Refresh Token | 7 días | Cookie HttpOnly | Rotado en cada uso |
| Sesión elevada | 10 minutos | Lado del servidor | Activado por reautenticación |

Las sesiones elevadas son necesarias para operaciones sensibles: cambios de contraseña, cambios de correo electrónico, configuración de 2FA, transferencias de propiedad y acciones administrativas destructivas.

### Modelo de permisos

Rediacc utiliza tres capas de permisos independientes:

![Permission Flow](/img/account-permission-flow.svg)

**Capa 1: Rol del sistema** -- Determina el acceso a los endpoints de administración del sistema.

**Capa 2: Rol de organización** -- Controla lo que un usuario puede hacer dentro de su organización (owner, admin, member).

**Capa 3: Rol de equipo** -- Limita el acceso a recursos específicos del equipo (team_admin, member). Los propietarios y administradores de la organización omiten las verificaciones de rol de equipo.

Cada solicitud de API pasa por todas las capas aplicables en secuencia. Una solicitud a un endpoint de ámbito de equipo debe cumplir con la autenticación de sesión, la membresía de organización y el acceso al equipo.

### Canales de actualización

La CLI admite dos canales de lanzamiento:
- **stable** (predeterminado): Promovido desde edge tras un período de prueba de 7 días; elige este canal para una cadencia de actualización conservadora
- **edge**: Últimas funciones, actualizado en cada lanzamiento

```bash
rdc update --channel edge      # Cambiar a edge
rdc update --channel stable    # Volver a stable
rdc update --status            # Mostrar canal actual
```
