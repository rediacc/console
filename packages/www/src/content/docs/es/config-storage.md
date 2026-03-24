---
title: "Config Storage (Rediacc Provider)"
description: "Sincronice de forma segura la configuración CLI entre dispositivos y equipos con cifrado de conocimiento cero."
category: "Guides"
order: 9
language: es
sourceHash: "459f12eb33547c13"
sourceCommit: "12bf0959ad816cdab93fb6410a22e4694d1a7635"
---

# Config Storage

El proveedor de almacenamiento de configuración Rediacc sincroniza su configuración CLI entre dispositivos y equipos con cifrado de conocimiento cero. Sus claves SSH, IPs de máquinas y credenciales se cifran en el lado del cliente antes de salir de su máquina -- ni siquiera los operadores de Rediacc pueden leer sus datos.

## Requisitos previos

- **Proveedor de passkey con soporte PRF**: una llave de seguridad FIDO2 (ej. YubiKey), iCloud Keychain, Google Password Manager, 1Password o Dashlane
- **2FA habilitado** para propietarios/administradores de organización (requerido para la configuración del store y gestión de miembros)
- **Suscripción de cuenta** con config storage habilitado

## Inicio rápido

```bash
# Set up config storage (opens browser for passkey registration)
rdc store add my-config --type rediacc

# Push your current config to the server
rdc store push --store my-config

# Pull config on another device (after setup)
rdc store pull --store my-config

# Sync (pull newer, then push)
rdc store sync --store my-config
```

## Configuración

### Escritorio (con navegador)

```bash
rdc store add my-config --type rediacc
```

1. Se abre una ventana del navegador en el portal de cuenta Rediacc
2. Registre un passkey (ventana emergente de YubiKey/iCloud Keychain/1Password)
3. La extensión PRF del passkey deriva sus claves de cifrado
4. Las claves se almacenan en el almacenamiento seguro nativo de su SO (Keychain/keyctl/DPAPI)
5. Listo -- no hay contraseña que recordar

### Servidores headless (sin navegador)

```bash
rdc store add my-config --type rediacc --headless
```

1. La CLI muestra una URL con un código de dispositivo
2. Abra la URL en su teléfono o portátil
3. Complete el registro del passkey en el navegador
4. La CLI recibe automáticamente sus claves cifradas a través de un relay seguro
5. Conocimiento cero preservado -- el servidor solo retransmite un blob cifrado opaco

### URL de servidor personalizada

```bash
rdc store add my-config --type rediacc --server-url https://account.yourcompany.com
```

## Push & Pull

Después de la configuración, push y pull funcionan sin contraseñas ni solicitudes:

```bash
# Push current config
rdc store push --store my-config

# Pull from server
rdc store pull --store my-config

# Sync all configured stores
rdc store sync --all

# List configured stores
rdc store list
```

Cada operación utiliza un token rotativo que se autodestruye después de un solo uso. Sin credenciales estáticas.

## Gestión de equipos

Los miembros del equipo se gestionan a través del portal web en `/account/config-storage/members`.

### Agregar miembros

1. El administrador abre la página de miembros de config storage
2. Hace clic en "Add Member" (requiere 2FA)
3. El navegador del administrador cifra la clave de cifrado del equipo para el nuevo miembro
4. El nuevo miembro inicia sesión y acepta la invitación
5. Ambos pueden ahora hacer push/pull de las mismas configuraciones

### Eliminar miembros

1. El administrador hace clic en "Remove" junto al miembro (requiere 2FA)
2. Las claves de cifrado del miembro se eliminan inmediatamente
3. En 30 segundos, el miembro pierde todo acceso a las configuraciones cifradas

No se necesita rotación de claves -- el servidor simplemente deja de servir claves de descifrado al miembro eliminado.

## Propiedades de seguridad

| Propiedad | Cómo |
|-----------|------|
| **Conocimiento cero** | El cliente cifra antes de enviar; el servidor solo ve blobs opacos |
| **Sin contraseña maestra** | La biometría del passkey reemplaza las contraseñas por completo |
| **Derivación de clave dividida** | CEK requiere tanto passkey_secret (cliente) + server_secret (servidor) |
| **Tokens rotativos** | Cada llamada API genera un nuevo token; los antiguos expiran |
| **Vinculación IP** | Los tokens se vinculan a la IP del cliente en el primer uso |
| **Triple cifrado** | SDK (ventana temporal) + CEK (cliente) + frase de organización (servidor) |
| **Revocación instantánea** | Dejar de servir SDK a miembros eliminados; retraso máximo de 30 segundos |
| **Detección de manipulación** | HMAC sobre blobs cifrados; verificado en cada pull |

Para la arquitectura de seguridad completa, consulte el [Security Guide](/docs/SECURITY-CONFIG-STORAGE.md).

## Solución de problemas

### "Passkey must support PRF extension"

Su proveedor de passkey no soporta la extensión PRF. Use:
- Una llave de seguridad FIDO2 (ej. YubiKey)
- iCloud Keychain (Safari en macOS/iOS)
- Google Password Manager (Chrome en Android/ChromeOS)
- 1Password
- Dashlane

### "Two-factor authentication required"

Los propietarios y administradores de la organización deben habilitar 2FA antes de configurar config storage. Vaya a Account Settings -> Security -> Enable 2FA.

### "Version conflict"

Otro miembro del equipo envió una versión más reciente. Descargue primero:
```bash
rdc store pull --store my-config
# Resolve any conflicts
rdc store push --store my-config
```

### "Config token expired"

Los tokens expiran después de 24 horas de inactividad. Ejecute cualquier comando para actualizar:
```bash
rdc store sync --store my-config
```

### "passkey_secret not found in secure storage"

La clave de cifrado se perdió del almacenamiento seguro de su SO (reinicio en Linux, restablecimiento de keychain). Ejecute la configuración de nuevo:
```bash
rdc store add my-config --type rediacc
```
