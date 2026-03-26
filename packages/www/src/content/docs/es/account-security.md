---
title: Seguridad de cuenta y API
description: Autenticacion, tokens de API, gestion de sesiones y el modelo de permisos.
category: Guides
order: 13
language: es
---

### Autenticacion

Rediacc admite multiples metodos de autenticacion:

![Auth Flow](/img/account-auth-flow.svg)

- **Contrasena**: Inicio de sesion tradicional con correo electronico y contrasena
- **Magic Link**: Inicio de sesion sin contrasena mediante enlace por correo (expira en 15 minutos)
- **Autenticacion de dos factores (2FA)**: Basada en TOTP con codigos de respaldo

Cuando 2FA esta habilitado, el inicio de sesion requiere tanto la contrasena (o magic link) como un codigo TOTP de 6 digitos.

### Tokens de API

Los tokens de API autentican operaciones de maquina a maquina (activacion de licencias CLI, verificaciones de estado).

![API Token Lifecycle](/img/account-api-token-lifecycle.svg)

**Alcances:**
- `license:read` -- Consultar el estado de suscripcion y licencia
- `license:activate` -- Activar maquinas y emitir licencias de repositorio
- `subscription:read` -- Leer detalles de la suscripcion

**Funciones de seguridad:**
- Vinculacion de IP: la primera solicitud bloquea el token a esa direccion IP
- Alcance por equipo: los tokens pueden restringirse a un equipo especifico
- Revocacion automatica: los tokens se revocan cuando el creador es eliminado de la organizacion

Crear un token:
```bash
# Via the portal: API Tokens > Create
# Token value is shown once -- save it securely
```

### Flujo de codigo de dispositivo

La CLI puede autenticarse en maquinas sin pantalla utilizando el flujo de codigo de dispositivo:

![Device Code Flow](/img/account-device-code-flow.svg)

```bash
rdc config remote enable --headless
# Displays: Enter code XXXX-XXXX-XX at https://www.rediacc.com/account/authorize
# After approval, CLI receives credentials automatically
```

### Config Storage

Para configuracion cifrada y sincronizada con el servidor, consulta [Config Storage](/en/docs/config-storage) para la guia completa. Config storage utiliza:
- Cifrado de conocimiento cero (el servidor nunca ve texto plano)
- Derivacion de claves basada en passkey (WebAuthn + PRF)
- Tokens rotativos con rotacion por solicitud

### Seguridad de sesion

| Tipo de token | Duracion | Almacenamiento | Actualizacion |
|---------------|----------|----------------|---------------|
| Access Token (JWT) | 15 minutos | Cookie HttpOnly | Automatico via refresh token |
| Refresh Token | 7 dias | Cookie HttpOnly | Rotado en cada uso |
| Elevated Session | 10 minutos | Lado del servidor | Activado por reautenticacion |

Las sesiones elevadas son necesarias para operaciones sensibles: cambios de contrasena, cambios de correo electronico, configuracion de 2FA, transferencias de propiedad y acciones administrativas destructivas.

### Modelo de permisos

Rediacc utiliza tres capas de permisos independientes:

![Permission Flow](/img/account-permission-flow.svg)

**Capa 1: Rol del sistema** -- Determina el acceso a los endpoints de administracion del sistema.

**Capa 2: Rol de organizacion** -- Controla lo que un usuario puede hacer dentro de su organizacion (owner, admin, member).

**Capa 3: Rol de equipo** -- Limita el acceso a recursos especificos del equipo (team_admin, member). Los propietarios y administradores de la organizacion omiten las verificaciones de rol de equipo.

Cada solicitud de API pasa por todas las capas aplicables en secuencia. Una solicitud a un endpoint de ambito de equipo debe cumplir con la autenticacion de sesion, la membresia de organizacion y el acceso al equipo.

### Canales de actualizacion

La CLI admite dos canales de lanzamiento:
- **stable** (predeterminado): Probado exhaustivamente, recomendado para produccion
- **edge**: Ultimas funciones, actualizado en cada lanzamiento

```bash
rdc update --channel edge      # Switch to edge
rdc update --channel stable    # Switch back to stable
rdc update --status            # Show current channel
```
