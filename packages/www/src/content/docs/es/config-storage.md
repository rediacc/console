---
title: Almacenamiento de configuración
description: >-
  Sincronización cifrada del lado del cliente de la configuración, con
  desbloqueo mediante passkey, contraseña maestra o código de recuperación
category: Guides
tags:
  - account
  - security
subcategory: account
order: 8
language: es
sourceHash: "ccced160d151eeeb"
sourceCommit: "6cfcb0017e6db164abaf81c7e0a10d0d8086370b"
---

# Almacenamiento de configuración

El almacenamiento de configuración sincroniza una configuración CLI entre dispositivos. Las configuraciones se cifran en el dispositivo con una clave de cifrado de contenido (CEK) que el servidor nunca posee. La sección [Seguridad](#security) indica exactamente contra qué protege esto y contra qué no.

## Métodos de desbloqueo (ranuras de clave)

Hay una única CEK por almacén, envuelta de forma independiente para cada método de desbloqueo, de manera similar a las ranuras de clave de LUKS. Cualquier ranura por sí sola abre la misma clave, y las ranuras pueden añadirse o eliminarse sin volver a cifrar sus datos:

| Método | Qué es | Notas |
|--------|-----------|-------|
| **Passkey** | Passkey WebAuthn con la extensión PRF | La opción más robusta; respaldada por hardware |
| **Contraseña maestra** | Una contraseña que usted elige, reforzada con PBKDF2-SHA256 (600.000 iteraciones) | Funciona sin hardware compatible con PRF; también habilita la inscripción headless del CLI |
| **Código de recuperación** | Un código generado `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX` | Se muestra una única vez al crearse; guárdelo en un lugar seguro |

Todos los métodos alimentan el mismo proceso: la ranura produce un secreto que se combina con un secreto guardado en el servidor para desenvolver la CEK. Ninguna de las dos mitades basta por sí sola, y el secreto de la ranura nunca llega al servidor. Una ranura de contraseña maestra es la más débil de las tres: el servidor tiene todo lo necesario para probar contraseñas sin conexión, así que la contraseña debe ser robusta. Las ranuras de passkey y de código de recuperación no tienen esa debilidad.

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
3. Elige el primer método de desbloqueo y haz clic en **Crear almacén de configuración**:
   - **Passkey**, si tu proveedor admite PRF: tocas tu llave de seguridad dos veces, una para registrarla y otra para derivar las claves de cifrado.
   - **Contraseña maestra**, que funciona en cualquier navegador, también con proveedores de passkeys sin PRF como Bitwarden.
   - Opcionalmente, un **código de recuperación**, que se muestra una sola vez y debes guardar antes de crear el almacén.
4. Configuración completada. La CLI guarda el secreto de desbloqueo en el llavero de tu sistema operativo.

Puedes añadir una passkey más adelante desde la página de Config Storage. Mantén al menos dos métodos de desbloqueo para que un autenticador perdido o no compatible no te deje fuera.

## Compatibilidad de proveedores PRF

| Proveedor | Soporte PRF | Plataformas |
|----------|:-----------:|-----------|
| YubiKey / claves de seguridad FIDO2 | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Multiplataforma |
| Extensión Bitwarden | ❌ | Utilice una contraseña maestra en su lugar |
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
- **Las ediciones simultáneas desde dos máquinas** se resuelven mediante pull-replay-repush: el servidor acepta un push solo sobre la versión que reemplaza, y el push perdedor se reproduce sobre la copia actualizada, de modo que una edición simultánea en otro lugar no se sobrescribe.
- **Una configuración local** (sin bloque `remote`) no se ve afectada por nada de esto y funciona completamente sin conexión.

## Qué se sincroniza

Todo en una configuración se sincroniza, incluido el ID de red de cada repositorio, salvo estos campos locales del dispositivo: `schemaVersion`, `version`, `remote`, `encryption`, `renetPath`, `credentials.masterPasswordVerifier`, y los campos de inicio de sesión `account.accountServer` y `account.e2ePublicKey`. Iniciar y cerrar sesión es por dispositivo.

## Versiones y restauración

El servidor conserva las últimas 50 versiones de cada configuración.

```bash
rdc config remote versions
rdc config remote restore <version>
```

Una restauración publica el contenido antiguo como una nueva versión sobre la actual; nunca retrocede el número de versión. Cada dispositivo recibe el contenido restaurado en su siguiente pull, y la restauración queda registrada en el registro de auditoría.

## Rotación de claves

Rotar la CEK del almacén la vuelve a envolver bajo una nueva generación:

- **Los códigos de recuperación siempre se invalidan** con la rotación, genere y guarde uno nuevo después
- Una **ranura de contraseña maestra** solo sobrevive si la contraseña se vuelve a introducir durante el asistente de rotación
- Una ranura que queda rezagada en una generación anterior se reporta como obsoleta en lugar de fallar con un error de descifrado críptico
- Los tokens de configuración de los demás miembros se revocan, y a un dispositivo que aún conserve la clave antigua se le indica que vuelva a activarse con `rdc config remote enable`

## Gestión de miembros

El almacenamiento de configuración está delimitado por organización. Los miembros se gestionan a través del portal web:

- **Ver miembros**: Almacenamiento de configuración → Miembros
- **Añadir miembro**: Actualmente solo vía CLI (interfaz web planificada)
- **Eliminar miembro**: Haga clic en el botón de eliminar en la página de Miembros (requiere 2FA + re-autenticación)

Las protecciones de seguridad impiden eliminar al último miembro activo o eliminarse a sí mismo.

Las configuraciones del almacén también están delimitadas por equipo, pero esa delimitación es **control de acceso del lado del servidor, no aislamiento criptográfico**: una única CEK a nivel de organización cifra las configuraciones de todos los equipos, y es el servidor quien aplica qué equipos puede leer cada miembro.

## Seguridad

**Qué está protegido.** Las configuraciones almacenadas son confidenciales frente a una vulneración del almacenamiento del servidor y frente a un operador pasivo. Cada blob está vinculado a su almacén, configuración, equipo y versión, de modo que el servidor no puede intercambiar el blob de una configuración por el de otra ni alterarlo sin que se detecte.

**Qué no está protegido.** Un operador que sirva código malicioso del portal puede leer la clave en el navegador. Un operador también puede retener la versión más reciente ante un dispositivo que nunca la ha visto.

| El servidor puede | El servidor no puede |
|---|---|
| Ver los ids de configuración, los equipos, los números de versión, las marcas de tiempo, el tamaño de los blobs, cuántos campos confirma una configuración y el tipo de cada campo, y las direcciones IP de los clientes | Ver los nombres de máquinas, repositorios o almacenes (están cegados) ni ningún valor de configuración |
| Rechazar, retrasar o eliminar configuraciones y su historial | Servir el contenido de una configuración como si fuera el de otra, o editarlo, sin que el dispositivo lo detecte |
| Servir una versión antigua a un dispositivo que nunca vio una más reciente | Servir al CLI una versión más antigua que otra que ya vio: el CLI la rechaza |
| Probar contraseñas maestras sin conexión | Abrir una ranura de passkey o de código de recuperación |

Otras salvaguardas:

- **Clave dividida**: el descifrado necesita tanto el secreto de la ranura (en el dispositivo) como el secreto del servidor
- **Eliminar exige conocimiento**: quitar un valor confirmado de una configuración exige demostrar que ese valor era conocido, de modo que alguien con acceso parcial no puede eliminar campos en silencio
- **Tokens rotativos**: cada solicitud rota el token de configuración; un token queda vinculado a la IP de su primer uso y caduca a los 7 días
- **Revocación**: eliminar a un miembro borra a la vez sus ranuras de clave y sus tokens; lo que ya había descargado permanece en su dispositivo, y una rotación de la CEK impide que una clave que conservó abra versiones posteriores

## Solución de problemas

| Error | Causa | Solución |
|-------|-------|-----|
| PRF not supported | El autenticador carece de extensión PRF | Use YubiKey, iCloud Keychain, 1Password o Dashlane, o añada una ranura de contraseña maestra |
| X25519 not supported | Versión del navegador demasiado antigua | Actualice a Chrome 133+, Edge 133+, Firefox 130+ o Safari 17+ |
| Already configured | Ya existe un almacén para su organización | Visite /account/config-storage para gestionar |
| Config storage not configured | El servidor carece de almacenamiento blob | Contacte a su administrador para configurar R2/RustFS |
| Token expired | Sin actividad durante 7 días, o la máquina cambió de red | Se renueva automáticamente al iniciar sesión; si no hay sesión guardada, ejecute `rdc subscription login` o `rdc config remote enable` |
| Config came back at an older version | El servidor devolvió una copia más antigua que la que este dispositivo ya había visto | No cambió nada localmente; reinténtelo y repórtelo si persiste |
| Cannot remove last member | Bloquearía el almacén permanentemente | Añada otro miembro primero |
| Stale slot | La ranura es anterior a la última rotación de clave | Vuelva a añadir la ranura (los códigos de recuperación deben regenerarse después de cada rotación) |

## Relacionado

- [Consola web](/es/docs/web-console), desbloquear el almacén en el navegador para ejecutar comandos
- [Proxy y ejecutor](/es/docs/proxy-and-executor), cómo se concede la clave desbloqueada a un ejecutor
