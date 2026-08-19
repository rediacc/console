---
title: Almacenamiento de configuración
description: >-
  Sincronización cifrada de configuración de conocimiento cero con
  desbloqueo mediante passkey, contraseña maestra o código de recuperación
category: Guides
tags:
  - account
  - security
order: 8
language: es
sourceHash: "e4b2eecb8bdf0015"
sourceCommit: "433347c5ea4754300fe3da80c4bfcee42dd161bc"
---

# Almacenamiento de configuración

El almacenamiento de configuración proporciona sincronización cifrada de conocimiento cero de su configuración CLI entre dispositivos. Sus configuraciones se cifran del lado del cliente con una clave de cifrado de contenido (CEK); el servidor nunca ve datos en texto plano.

## Métodos de desbloqueo (ranuras de clave)

Hay una única CEK por almacén, envuelta de forma independiente para cada método de desbloqueo, de manera similar a las ranuras de clave de LUKS. Cualquier ranura por sí sola abre la misma clave, y las ranuras pueden añadirse o eliminarse sin volver a cifrar sus datos:

| Método | Qué es | Notas |
|--------|-----------|-------|
| **Passkey** | Passkey WebAuthn con la extensión PRF | La opción más robusta; respaldada por hardware |
| **Contraseña maestra** | Una contraseña que usted elige, reforzada con PBKDF2-SHA256 (600.000 iteraciones) | Funciona sin hardware compatible con PRF; también habilita la inscripción headless del CLI |
| **Código de recuperación** | Un código generado `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX` | Se muestra una única vez al crearse; guárdelo en un lugar seguro |

Todos los métodos alimentan el mismo proceso: la ranura produce un secreto que se combina con un secreto guardado en el servidor para desenvolver la CEK. Ninguna de las dos mitades basta por sí sola, así que la propiedad de conocimiento cero se mantiene en los tres métodos: el secreto de la ranura nunca llega al servidor.

Las ranuras se gestionan en el portal, en la página de Almacenamiento de configuración. Las organizaciones que quieran un desbloqueo exclusivo por hardware pueden activar la política **requerir passkey**, que rechaza y revoca las ranuras que no sean passkey en todo el almacén.

El desbloqueo es por dispositivo: se desbloquea una vez en un dispositivo nuevo y, a partir de ahí, las operaciones diarias del CLI (push/pull) funcionan sin tocar un passkey ni escribir una contraseña.

## Requisitos previos

- **Autenticación de dos factores** habilitada en su cuenta
- Para el método de **passkey**: un proveedor de passkey con soporte PRF, como una clave de seguridad FIDO2 (p. ej. YubiKey), iCloud Keychain, Google Password Manager, 1Password o Dashlane
- **Navegador**: Chrome 133+, Edge 133+, Firefox 130+ o Safari 17+

El requisito de PRF se aplica solo a la ranura de passkey. Los métodos de contraseña maestra y código de recuperación funcionan con cualquier navegador compatible.

## Configuración

1. Navegue a **Almacenamiento de configuración** en la barra lateral, luego haga clic en **Configurar almacenamiento de configuración**
2. La lista de verificación de requisitos verifica su navegador, 2FA y el estado de la sesión
3. Haga clic en **Iniciar configuración**. Para una ranura de passkey tocará su clave de seguridad dos veces:
   - Primer toque: registra el passkey
   - Segundo toque: deriva las claves de cifrado vía PRF
4. Configuración completa, su secreto de passkey se almacena en el llavero de su sistema operativo

Tras la configuración, añada una ranura de contraseña maestra o de código de recuperación desde la página de Almacenamiento de configuración, para que un autenticador perdido o no compatible no le deje bloqueado.

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

## Inscripción headless del CLI

Una máquina sin navegador (un servidor, un runner de CI, un daemon ejecutor) puede inscribirse en un almacén existente con el método de contraseña maestra:

```bash
rdc config remote enable --password
```

Requisitos:

- Una **ranura de contraseña maestra** ya aprovisionada a través del portal (el navegador retiene la clave durante el aprovisionamiento, así que este paso en sí no puede ser headless)
- Un **token de API con el alcance `config:enroll`** para autenticar la llamada

La inscripción es una lectura: el CLI obtiene los parámetros públicos de KDF de la ranura y la clave envuelta, deriva el secreto de la contraseña localmente y desenvuelve la CEK en el dispositivo. Otorga al dispositivo la capacidad de descifrar y sincronizar la configuración; no modifica el almacén.

## Activación y lecturas sin conexión

`rdc config remote enable` conecta la configuración activa con el almacén. Cuando el almacén está vacío, activarlo **lo siembra con su configuración local actual**: los recursos locales se envían (push) como la primera versión del almacén y luego se recuperan (pull) para comprobar el ciclo completo. Cuando el almacén ya tiene contenido, la activación concilia con él en lugar de sobrescribirlo (se cancela ante una divergencia real a menos que pase `--force`).

Una vez activado, la configuración mantiene una **caché de lectura** completa, cifrada en reposo con el mismo mecanismo que cualquier configuración local, de modo que el almacén siga siendo utilizable cuando el servidor de cuenta no esté accesible:

- **Las lecturas funcionan sin conexión.** El contenido en caché se sirve con una advertencia de desactualización en stderr, etiquetada con la versión y la marca de tiempo en caché (`cachedVersion` / `cachedAt`).
- **Las escrituras requieren el servidor y fallan de forma segura.** No hay cola de escritura sin conexión: una escritura que no puede alcanzar el servidor falla con un error que nombra al servidor. Si un comando de escritura tuvo éxito, el cambio está en el servidor.
- **Las ediciones simultáneas desde dos máquinas** se resuelven mediante pull-replay-repush a nivel del bucket de recursos, de modo que una edición simultánea en otro lugar no sobrescribe la suya.

## Rotación de claves

Rotar la CEK del almacén la vuelve a envolver bajo una nueva generación:

- **Los códigos de recuperación siempre se invalidan** con la rotación, genere y guarde uno nuevo después
- Una **ranura de contraseña maestra** solo sobrevive si la contraseña se vuelve a introducir durante el asistente de rotación
- Una ranura que queda rezagada en una generación anterior se reporta como obsoleta en lugar de fallar con un error de descifrado críptico

## Gestión de miembros

El almacenamiento de configuración está delimitado por organización. Los miembros se gestionan a través del portal web:

- **Ver miembros**: Almacenamiento de configuración → Miembros
- **Añadir miembro**: Actualmente solo vía CLI (interfaz web planificada)
- **Eliminar miembro**: Haga clic en el botón de eliminar en la página de Miembros (requiere 2FA + re-autenticación)

Las protecciones de seguridad impiden eliminar al último miembro activo o eliminarse a sí mismo.

Las configuraciones del almacén también están delimitadas por equipo, pero esa delimitación es **control de acceso del lado del servidor, no aislamiento criptográfico**: una única CEK a nivel de organización cifra las configuraciones de todos los equipos, y es el servidor quien aplica qué equipos puede leer cada miembro.

## Seguridad

- **Conocimiento cero**: El servidor almacena datos triplemente cifrados que no puede descifrar
- **Clave dividida**: El descifrado requiere tanto el secreto de su ranura (cliente) como el secreto del servidor (servidor)
- **Tokens rotativos**: Cada llamada API usa un token nuevo; los tokens antiguos se autodestruyen
- **Vinculación IP**: Los tokens se vinculan a su IP en el primer uso
- **Revocación instantánea**: Los miembros eliminados pierden el acceso en 30 segundos

## Solución de problemas

| Error | Causa | Solución |
|-------|-------|-----|
| PRF not supported | El autenticador carece de extensión PRF | Use YubiKey, iCloud Keychain, 1Password o Dashlane, o añada una ranura de contraseña maestra |
| X25519 not supported | Versión del navegador demasiado antigua | Actualice a Chrome 133+, Edge 133+, Firefox 130+ o Safari 17+ |
| Already configured | Ya existe un almacén para su organización | Visite /account/config-storage para gestionar |
| Config storage not configured | El servidor carece de almacenamiento blob | Contacte a su administrador para configurar R2/RustFS |
| Token expired | Sin actividad durante 24 horas | Ejecute cualquier comando de almacenamiento de configuración para actualizar |
| Cannot remove last member | Bloquearía el almacén permanentemente | Añada otro miembro primero |
| Stale slot | La ranura es anterior a la última rotación de clave | Vuelva a añadir la ranura (los códigos de recuperación deben regenerarse después de cada rotación) |

## Relacionado

- [Consola web](/es/docs/web-console), desbloquear el almacén en el navegador para ejecutar comandos
- [Proxy y ejecutor](/es/docs/proxy-and-executor), cómo se concede la clave desbloqueada a un ejecutor
