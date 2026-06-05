---
title: Almacenamiento de configuración
description: >-
  Sincronización cifrada de configuración de conocimiento cero con cifrado
  basado en passkeys
category: Guides
order: 8
language: es
sourceHash: "daf79946b8925246"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

# Almacenamiento de configuración

El almacenamiento de configuración proporciona sincronización cifrada de conocimiento cero de su configuración CLI entre dispositivos. Sus configuraciones se cifran con claves derivadas de su passkey, el servidor nunca ve datos en texto plano.

## Requisitos previos

- **Autenticación de dos factores** habilitada en su cuenta
- **Proveedor de passkey con soporte PRF**: clave de seguridad FIDO2 (p. ej. YubiKey), iCloud Keychain, Google Password Manager, 1Password o Dashlane
- **Navegador**: Chrome 133+, Edge 133+, Firefox 130+ o Safari 17+

## Configuración

1. Navegue a **Almacenamiento de configuración** en la barra lateral, luego haga clic en **Configurar almacenamiento de configuración**
2. La lista de verificación de requisitos verifica su navegador, 2FA y el estado de la sesión
3. Haga clic en **Iniciar configuración**, necesitará tocar su clave de seguridad dos veces:
   - Primer toque: registra el passkey
   - Segundo toque: deriva las claves de cifrado vía PRF
4. Configuración completa, su secreto de passkey se almacena en el llavero de su sistema operativo

Después de la configuración, las operaciones diarias del CLI (push/pull) funcionan sin el passkey. Advertencia: la configuración requiere un passkey con soporte de extensión PRF. No todos los tokens de hardware o autenticadores de plataforma lo tienen.

## Compatibilidad de proveedores PRF

| Proveedor | Soporte PRF | Plataformas |
|----------|:-----------:|-----------|
| YubiKey / claves de seguridad FIDO2 | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Multiplataforma |
| Extensión Bitwarden | ❌ | En desarrollo |
| Windows Hello | ❌ | No soportado |

## Gestión de miembros

El almacenamiento de configuración está delimitado por organización. Los miembros se gestionan a través del portal web:

- **Ver miembros**: Almacenamiento de configuración → Miembros
- **Añadir miembro**: Actualmente solo vía CLI (interfaz web planificada)
- **Eliminar miembro**: Haga clic en el botón de eliminar en la página de Miembros (requiere 2FA + re-autenticación)

Las protecciones de seguridad impiden eliminar al último miembro activo o eliminarse a sí mismo.

## Seguridad

- **Conocimiento cero**: El servidor almacena datos triplemente cifrados que no puede descifrar
- **Clave dividida**: El descifrado requiere tanto su secreto de passkey (cliente) como el secreto del servidor (servidor)
- **Tokens rotativos**: Cada llamada API usa un token nuevo; los tokens antiguos se autodestruyen
- **Vinculación IP**: Los tokens se vinculan a su IP en el primer uso
- **Revocación instantánea**: Los miembros eliminados pierden el acceso en 30 segundos

## Solución de problemas

| Error | Causa | Solución |
|-------|-------|-----|
| PRF not supported | El autenticador carece de extensión PRF | Use YubiKey, iCloud Keychain, 1Password o Dashlane |
| X25519 not supported | Versión del navegador demasiado antigua | Actualice a Chrome 133+, Edge 133+, Firefox 130+ o Safari 17+ |
| Already configured | Ya existe un almacén para su organización | Visite /account/config-storage para gestionar |
| Config storage not configured | El servidor carece de almacenamiento blob | Contacte a su administrador para configurar R2/RustFS |
| Token expired | Sin actividad durante 24 horas | Ejecute cualquier comando de almacenamiento de configuración para actualizar |
| Cannot remove last member | Bloquearía el almacén permanentemente | Añada otro miembro primero |
