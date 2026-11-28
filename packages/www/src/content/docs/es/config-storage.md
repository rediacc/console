---
title: Almacenamiento de configuración
description: >-
  Sincronización cifrada del lado del cliente de la configuración, con
  desbloqueo mediante passkey o kit de recuperación
category: Guides
tags:
  - account
  - security
subcategory: account
order: 8
language: es
sourceHash: "3972742d77ac9e63"
sourceCommit: "45ae253620c97f781ac426d3a84bca6b9a8bc528"
---

# Almacenamiento de configuración

El almacenamiento de configuración sincroniza una configuración CLI entre dispositivos. Las configuraciones se cifran en el dispositivo con una clave de cifrado de contenido (CEK) que el servidor nunca posee. La sección [Seguridad](#security) indica exactamente contra qué protege esto y contra qué no.

## Métodos de desbloqueo (ranuras de clave)

Hay una única CEK por almacén, envuelta de forma independiente para cada método de desbloqueo, de manera similar a las ranuras de clave de LUKS. Cualquier ranura por sí sola abre la misma clave, y las ranuras pueden añadirse o eliminarse sin volver a cifrar sus datos:

| Método | Qué es | Notas |
|--------|-----------|-------|
| **Passkey** | Passkey WebAuthn con la extensión PRF, en este dispositivo o en un teléfono mediante un código QR | La opción más robusta; respaldada por hardware |
| **Kit de recuperación** | Un código generado `RC1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX`, guardado como kit impreso o descargado | Obligatorio para todos los miembros; el código solo se muestra mientras se guarda el kit, así que guárdelo en un lugar seguro |

Un **secreto de máquina** no es una ranura: inscribe una máquina headless (consulte [Inscripción headless del CLI](#headless-cli-enrollment)) y no cuenta como una forma de desbloquear el almacén para una persona.

Todos los métodos alimentan el mismo proceso: la ranura produce un secreto que se combina con un secreto guardado en el servidor para desenvolver la CEK. Ninguna de las dos mitades basta por sí sola, y el secreto de la ranura nunca llega al servidor. Ambos secretos tienen entropía suficiente, así que el servidor, que guarda la clave envuelta y su mitad de la clave de envoltura, no tiene nada que adivinar sin conexión.

Las ranuras se gestionan en el portal, en la página de Almacenamiento de configuración. Las organizaciones que quieran un desbloqueo exclusivo por hardware pueden activar la política **requerir passkey**, que rechaza y revoca las ranuras que no sean passkey en todo el almacén.

El desbloqueo es por dispositivo: se desbloquea una vez en un dispositivo nuevo y, a partir de ahí, las operaciones diarias del CLI (push/pull) funcionan sin tocar un passkey ni escribir un código de recuperación.

## Requisitos previos

- **Autenticación de dos factores** habilitada en su cuenta
- Para el método de **passkey**: un proveedor de passkey con soporte PRF, como una clave de seguridad FIDO2 (p. ej. YubiKey), iCloud Keychain, Google Password Manager, 1Password o Dashlane, en el dispositivo o en un teléfono mediante QR
- **Navegador**: Chrome 133+, Edge 133+, Firefox 130+ o Safari 17+

El requisito de PRF se aplica solo a la ranura de passkey. El kit de recuperación funciona con cualquier navegador compatible.

## Configuración

1. Navegue a **Almacenamiento de configuración** en la barra lateral, luego haga clic en **Configurar almacenamiento de configuración**
2. La lista de verificación de requisitos verifica su navegador, 2FA y el estado de la sesión
3. Registra una passkey y haz clic en **Crear almacén de configuración**. El proveedor debe admitir PRF: tocas tu llave de seguridad dos veces, una para registrarla y otra para derivar las claves de cifrado.
   - Un **código de recuperación** se genera junto con el almacén y se muestra una sola vez, en un kit de recuperación. Guarda el kit antes de crear el almacén; sin él la configuración no se completa.
4. Configuración completada. La CLI guarda el secreto de desbloqueo en el llavero de tu sistema operativo.

Puedes añadir una passkey más adelante desde la página de Config Storage.

### Teléfono mediante QR

Un equipo de escritorio sin autenticador PRF local puede usar un teléfono: el navegador muestra un código QR, el teléfono aprueba la solicitud de passkey mediante WebAuthn híbrido y el resultado PRF desbloquea el almacén igual que lo haría una passkey local. La ranura de passkey recuerda la credencial y el transporte con el que se registró. Si un resultado PRF no desenvuelve la clave, por ejemplo porque un teléfono devolvió una salida PRF distinta a la del dispositivo que registró la passkey, la página pide registrar la passkey de nuevo en lugar de mostrar un error de descifrado. El PRF híbrido requiere iOS 18.4+ o un Android reciente.

### Kit de recuperación

Cada miembro recibe un kit de recuperación al inscribirse, y la configuración no se completa hasta que se guarda. El kit contiene el nombre del almacén, el correo de la cuenta, la fecha de creación, el código en grupos, un QR del código y los pasos de recuperación. Una comprobación de guardado pide los últimos 4 caracteres del código, o el escaneo de su QR, antes de continuar con la inscripción. No hay forma de omitir el kit, y conservar la copia impresa a buen recaudo es responsabilidad del miembro.

- Una **passkey perdida** se recupera con el kit y después se registra una passkey nueva.
- Un **kit perdido** se regenera desde una passkey que funcione; la copia impresa anterior deja de servir.
- **Ambos perdidos**: un propietario o administrador vuelve a añadir al miembro mediante el traspaso de miembros.

### Red de seguridad

El servidor se niega a eliminar una ranura, quitar a un miembro o aceptar que un miembro se marche si con ello el almacén se quedara con menos de dos titulares de clave y sin ranura de recuperación. Un titular de clave es un usuario distinto con una ranura de passkey o de recuperación en la generación de clave actual; los secretos de máquina y las concesiones de agente no cuentan. El servidor no ve una copia impresa perdida, así que la página de Almacenamiento de configuración recomienda un segundo titular de clave mientras el almacén tenga solo uno. Si el último titular de clave pierde tanto la passkey como el kit, el almacén no se puede recuperar.

## Compatibilidad de proveedores PRF

| Proveedor | Soporte PRF | Plataformas |
|----------|:-----------:|-----------|
| YubiKey / claves de seguridad FIDO2 | ✅ | Windows 11, macOS, Linux |
| iCloud Keychain | ✅ | macOS 15+, iOS 18+ |
| Google Password Manager | ✅ | Android |
| 1Password | ✅ | Android, iOS |
| Dashlane | ✅ | Multiplataforma |
| Extensión Bitwarden | ❌ | Utilice una llave de hardware u otro proveedor de passkeys |
| Windows Hello | ❌ | No soportado |

## Inscripción headless del CLI

Una máquina sin navegador (un servidor, un runner de CI, un daemon ejecutor) puede inscribirse en un almacén existente con un secreto de máquina:

```bash
export REDIACC_MACHINE_SECRET=RM1-XXXXXXXX-XXXXXXXX-XXXXXXXX-XXXXXXXX
rdc config remote enable --machine-secret <id>
```

Requisitos:

- Un **secreto de máquina** generado a través del portal (el navegador retiene la clave mientras la envuelve bajo el secreto, así que este paso en sí no puede ser headless). El portal muestra el secreto `RM1-` una sola vez, junto con su id; el secreto se limita a la organización, a un equipo o a una configuración
- Un **token de API con el alcance `config:enroll`** para autenticar la llamada

El secreto se toma de `REDIACC_MACHINE_SECRET`, o bien de la entrada estándar si llega por una tubería, o bien de un aviso oculto; nunca es un argumento de la línea de comandos. La inscripción es una lectura: el CLI obtiene los parámetros públicos de KDF del secreto y la clave envuelta, deriva el secreto de envoltura localmente y desenvuelve la CEK en el dispositivo. Otorga al dispositivo la capacidad de descifrar y sincronizar la configuración; no modifica el almacén. Revocar el secreto en el portal impide nuevas inscripciones con él.

## Cómo llegan las claves a tu CLI

`rdc config remote enable` (y `rdc config rotate-cek`) entregan el secreto de desbloqueo al CLI a través del servidor de cuentas. El CLI y el navegador nunca se comunican directamente, así que funciona igual en un servidor sin navegador, en WSL con el navegador en Windows o desde un teléfono.

1. Inicia sesión primero en el CLI con `rdc subscription login`. El servidor vincula la solicitud a esa cuenta.
2. El CLI crea una solicitud de corta duración e imprime un enlace y un **código de emparejamiento** como `7KQ2-M9XD-P4RT`. El enlace guarda todo lo que lleva después del `#`, una parte que los navegadores nunca envían a un servidor.
3. Abre el enlace en cualquier navegador con la sesión iniciada en la misma cuenta. Una solicitud de otra cuenta se rechaza.
4. Escribe el código de emparejamiento desde tu terminal cuando la página lo pida. El botón de desbloqueo permanece desactivado hasta que coincida.
5. Desbloquea con una passkey (en este dispositivo o en un teléfono mediante QR) o con el kit de recuperación. El navegador sella la clave para el CLI, y el servidor reenvía un bloque de datos que no puede leer.
6. El CLI descifra el bloque, guarda el secreto en el llavero del sistema operativo e informa del éxito.

La solicitud caduca a los 10 minutos. Pulsa **Ctrl+C** en el CLI para cancelarla: el CLI pide al servidor que descarte el enlace, que deja de funcionar al instante, y la página indica que hay que volver a ejecutar el comando. Si esa petición no llega, el enlace sigue siendo válido hasta que caduque la solicitud. Si el enlace se abre después de que caduque, o después de que una redirección de inicio de sesión haya perdido la parte posterior al `#`, vuelve a ejecutar el comando.

El código de emparejamiento se deriva de la clave que va dentro del enlace. Si alguien sustituye el enlace por uno propio, el código de tu terminal no coincidirá con el que espera la página y no se liberará nada.

Esto protege frente a la manipulación del enlace y frente a un relé que cambie o falsifique un bloque de datos. No protege frente a un servidor que entregue código de página modificado: la página que abres la sirve el servidor de cuentas, y las claves son tan seguras como ese código. La misma confianza se aplica a cualquier página del portal que maneje la clave de configuración.

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

- **Los kits de recuperación siempre se invalidan** con la rotación, genere y guarde uno nuevo después
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

Otras salvaguardas:

- **Clave dividida**: el descifrado necesita tanto el secreto de la ranura (en el dispositivo) como el secreto del servidor
- **Eliminar exige conocimiento**: quitar un valor confirmado de una configuración exige demostrar que ese valor era conocido, de modo que alguien con acceso parcial no puede eliminar campos en silencio
- **Tokens rotativos**: cada solicitud rota el token de configuración; un token queda vinculado a la IP de su primer uso y caduca a los 7 días
- **Revocación**: eliminar a un miembro borra a la vez sus ranuras de clave y sus tokens; lo que ya había descargado permanece en su dispositivo, y una rotación de la CEK impide que una clave que conservó abra versiones posteriores

## Solución de problemas

| Error | Causa | Solución |
|-------|-------|-----|
| PRF not supported | El autenticador carece de extensión PRF | Use YubiKey, iCloud Keychain, 1Password, Dashlane o un teléfono mediante QR |
| X25519 not supported | Versión del navegador demasiado antigua | Actualice a Chrome 133+, Edge 133+, Firefox 130+ o Safari 17+ |
| Already configured | Ya existe un almacén para su organización | Visite /account/config-storage para gestionar |
| Config storage not configured | El servidor carece de almacenamiento blob | Contacte a su administrador para configurar R2/RustFS |
| Token expired | Sin actividad durante 7 días, o la máquina cambió de red | Se renueva automáticamente al iniciar sesión; si no hay sesión guardada, ejecute `rdc subscription login` o `rdc config remote enable` |
| Config came back at an older version | El servidor devolvió una copia más antigua que la que este dispositivo ya había visto | No cambió nada localmente; reinténtelo y repórtelo si persiste |
| Cannot remove last member | Bloquearía el almacén permanentemente | Añada otro miembro primero |
| Stale slot | La ranura es anterior a la última rotación de clave | Vuelva a añadir la ranura (el kit de recuperación debe regenerarse después de cada rotación) |

## Relacionado

- [Modelo de seguridad](/es/docs/security-model), quién puede ver qué, alcance de las claves, agentes y qué se puede recuperar
- [Consola web](/es/docs/web-console), desbloquear el almacén en el navegador para ejecutar comandos
- [Proxy y ejecutor](/es/docs/proxy-and-executor), cómo se concede la clave desbloqueada a un ejecutor
