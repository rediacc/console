---
title: Suscripciones y Licencias
description: >-
  Comprenda cómo account, rdc y renet administran ranuras de máquina, licencias
  de repositorio y límites de plan.
category: Guides
order: 7
language: es
sourceHash: "4e7aa81c81aef1e9"
sourceCommit: "fd9d3476b1fdf0ac6ffaa14f486f20f9642fe2d5"
---

# Suscripciones y Licencias

El sistema de licencias de Rediacc se divide en tres componentes principales:

- `account` firma asignaciones de derechos y registra el uso
- `rdc` autentica, solicita licencias, las entrega a máquinas y las aplica en tiempo de ejecución
- `renet` (el tiempo de ejecución en máquina) valida las licencias instaladas localmente sin llamar al servidor de cuenta

Esta página explica cómo encajan estas piezas en implementaciones locales.

## Qué hace el sistema de licencias

El sistema de licencias controla dos cosas diferentes:

- **Contabilidad de acceso a máquinas** mediante **Licencias Flotantes**
- **Autorización de tiempo de ejecución de repositorio** mediante **licencias de repositorio**

Están relacionadas, pero no son el mismo artefacto.

## Cómo funciona el sistema de licencias

`account` es la fuente de verdad para planes, anulaciones de contrato, estado de ranura de máquina e issuances de licencias de repositorio mensuales.

`rdc` se ejecuta en tu estación de trabajo. Te inicia sesión en el servidor de cuenta, solicita las licencias que necesita e las instala en máquinas remotas a través de SSH. Cuando ejecutas un comando de repositorio, `rdc` garantiza que las licencias requeridas estén en su lugar y las valida en la máquina en tiempo de ejecución.

El flujo normal se ve así:

1. Te autenticas con `rdc subscription login`
2. Ejecutas un comando de repositorio como `rdc repo create`, `rdc repo up` o `rdc repo down`
3. Si la licencia requerida falta o ha expirado, `rdc` la solicita desde `account`
4. `rdc` escribe la licencia firmada en la máquina
5. La licencia se valida localmente en la máquina y la operación continúa

Consulta [rdc vs renet](/es/docs/rdc-vs-renet) para conocer la división estación de trabajo frente a servidor, y [Repositorios](/es/docs/repositories) para el ciclo de vida del repositorio en sí.

Para automatización y agentes de IA, utiliza un token de suscripción con alcance limitado en lugar de inicio de sesión en navegador:

```bash
rdc subscription login --token "$REDIACC_TOKEN"
```

También puedes inyectar el token directamente a través del entorno para que la CLI pueda emitir y actualizar licencias de repositorio sin ningún paso de inicio de sesión interactivo:

```bash
export REDIACC_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## Ranuras de máquina y licencias de repositorio

### Ranuras de máquina (lado del servidor)

El seguimiento de ranura de máquina se aplica del lado del servidor. Cuando la CLI emite una licencia de repositorio, el servidor de cuenta verifica la cuota de ranura de máquina de la suscripción. Todos los planes de autoservicio (Community, Professional, Business) incluyen una ranura de máquina; las implementaciones multi-máquina son una configuración Enterprise dimensionada junto con nuestros partners. Se mantiene una ranura durante 5 horas desde la última emisión de licencia de repositorio en esa máquina y se libera automáticamente después de la inactividad. Como una ranura solo se mantiene mientras aprovisionas activamente, una sola ranura puede seguir cubriendo varias máquinas a lo largo de un mes.

El tope se lee del registro de tu suscripción, no de una constante de plan fija en el código, así que un número de activaciones negociado se respeta en cuanto queda anotado en la suscripción. El nivel del plan solo decide el valor inicial.

La emisión y la renovación se aplican de forma distinta, y esa diferencia importa:

- **Emitir una licencia nueva se bloquea en el tope.** Si todas las ranuras están ocupadas, la petición falla con `MAX_MACHINES_REACHED` y no se aprovisiona nada.
- **Renovar una licencia existente nunca se bloquea.** Una máquina que renueva mientras todas las ranuras están ocupadas sigue funcionando y su ranura queda registrada como por encima del límite. Puedes verlo en el portal, en la página Máquinas, en `rdc subscription status` y en el campo `overLimitCount` de la API de estado de licencias. La marca desaparece sola en cuanto la máquina vuelve a estar dentro del límite.

La renovación es deliberadamente el camino más flexible. Una máquina que renueva una licencia que ya tiene no es capacidad nueva, y rechazarla detendría copias de seguridad sobre infraestructura que ya está pagada. Lo que sigue bloqueado es añadir capacidad.

No se almacena ningún archivo de licencia de máquina en la máquina. La aplicación de ranura ocurre en el momento de la issuance en el servidor.

### Licencia de repositorio

Una licencia de repositorio es una licencia firmada para un repositorio en una máquina. Es el único archivo de licencia almacenado en la máquina, organizado por datastore y por clave de firma:

```
/var/lib/rediacc/license/repos/{guid}/{keyId}.json
/var/lib/rediacc/license/datastores/{datastoreId}/repos/{guid}/{keyId}.json
```

Los repositorios que están en el almacenamiento predeterminado de una máquina usan la primera ruta. Los repositorios que están en un datastore con nombre usan la segunda, donde `{datastoreId}` es la identidad que recibió ese datastore al crearse. Ese alcance es lo que hace que un fork de datastore se mida con honestidad: un datastore forkeado obtiene una identidad completamente nueva, así que sus repositorios arrancan sin ninguna licencia, informan `missing` en su primera operación con licencia y reciben sus propias licencias. Un repositorio cuya licencia nombra un datastore distinto de aquel en el que está falla de inmediato con `identity_mismatch` en lugar de reemitirse solo, y eso es lo que impide copiar de lado un archivo de licencia.

`{keyId}` es una huella de 16 dígitos hexadecimales (los primeros 8 bytes de `SHA-256` de la clave pública Ed25519 del servidor firmante). Un repositorio gestionado por más de un universo de cuenta (por ejemplo, producción y bench desplegando en la misma máquina) mantiene un archivo por clave de firma bajo su directorio `{guid}`. La compilación de renet de la máquina solo valida el archivo que su clave incorporada, o un certificado de delegación encadenado a ella, pueda verificar; los archivos de otros universos quedan inertes. Cambiar de universo nunca invalida las licencias: la primera operación en un universo nuevo emite la licencia de ese universo una vez (un resultado `missing` la emite automáticamente), y ambos coexisten después.

Se utiliza para:

- `rdc repo create`, `rdc repo fork` y `rdc repo commit`, validadas antes del aprovisionamiento (pre-emitidas sin pruebas de identidad, luego re-emitidas con pruebas de identidad después de la creación, porque el repositorio todavía no existe en el momento de la comprobación)
- `rdc repo resize`, `rdc repo expand`, `rdc repo merge` y `rdc repo promote`, **validación completa incluyendo expiración**
- transferencia de copias de seguridad, **validación completa incluyendo expiración**: `rdc repo push`, `rdc repo pull`, `rdc repo migrate` y las copias de seguridad programadas
- `rdc repo up`, `rdc repo up --all`, `rdc repo exec` y el autostart de repositorio en el reinicio de la máquina, validadas **omitiendo tanto la expiración como la ventana del certificado de delegación**
- `rdc repo down`, `rdc repo delete` y los comandos de solo lectura, como listar repositorios, no necesitan licencia alguna

Las firmas, la vinculación de clave, la vinculación de máquina, la vinculación de repositorio y todas las restricciones del certificado de delegación se aplican en todas ellas. Lo único que relaja el último grupo son las dos ventanas de tiempo, para que una licencia expirada o un certificado vencido nunca puedan impedirte arrancar o apagar tus propios datos.

Las licencias de repositorio están vinculadas a la máquina y al repositorio de destino. Cada licencia contiene el ID de máquina, GUID del repositorio, ID de suscripción, límites de plan y expiración. Para repositorios encriptados, Rediacc también verifica la identidad LUKS del volumen subyacente.

Múltiples suscripciones pueden coexistir en la misma máquina. Cada repositorio tiene su propia licencia con su propio contexto de suscripción.

## Clústeres

El clustering se vende a través de nuestros partners como parte de un acuerdo Enterprise. No es una opción de plan de autoservicio, y las secciones siguientes describen cómo se mide, no cómo se compra.

**Un nodo es una máquina.** Un clúster no tiene identidad de licencia propia. Cada nodo que lo forma es una máquina corriente con el Renet Agent instalado, y se cuenta exactamente igual que una máquina independiente.

**No hay agrupación.** Un clúster de cinco nodos no consume una única ranura de clúster compartida. Cada nodo reclama su propia ranura la primera vez que se coloca un repositorio en él, y esa ranura sigue la misma regla flotante de 5 horas que cualquier otra: se mantiene 5 horas desde la última emisión de licencia de repositorio en ese nodo y se libera sola después.

**Construir el clúster es gratis. Lo que se mide es colocar repositorios.** Crear el clúster, unir nodos, instalar la capa de almacenamiento distribuido y levantar el plano de control de Kubernetes no cuesta ninguna ranura. La medición empieza cuando un repositorio aterriza en un nodo.

**Un fork de clúster vuelve a medir repositorio por repositorio.** Al forkear un clúster entero, el datastore forkeado recibe una identidad nueva, así que cada repositorio del fork obtiene su propia licencia la primera vez que se toca, en el nodo en el que esté corriendo. La migración normal es el caso opuesto: mover un repositorio entre máquinas se lleva consigo su licencia y esta sigue validando, porque nada de su identidad de almacenamiento ha cambiado.

**La renovación en un clúster sigue la regla flexible de arriba.** Los nodos renuevan sus propias licencias sin supervisión, así que un clúster que ha crecido por encima de su número de activaciones sigue funcionando e informa de los nodos que exceden el límite, en lugar de hacer fallar las copias de seguridad en mitad de la noche. Añadir un nodo nuevo sí se sigue bloqueando en el tope.

Dimensionar un clúster es una conversación, no una casilla. El número de activaciones de un clúster se acuerda en el pedido, y tu partner lo fija directamente en la suscripción. Consulta [Contacto](/es/contact) para iniciar esa conversación.

## Límites predeterminados

El tamaño del repositorio depende del nivel de derecho:

- Community: hasta `10 GB`
- planes pagados: límite de plan o contrato

Los límites predeterminados de planes pagados son:

| Plan | Licencias Flotantes | Tamaño de Repositorio | Issuances de licencia de repositorio mensuales | Delegación cert predeterminado / máximo |
|------|-------------------|-----------------|-------------------------------|---|
| Community | 1 | 10 GB | 100 | 15d / 30d |
| Professional | 1 | 100 GB | 2,000+ | 60d / 120d |
| Business | 1 | 500 GB | 5,000+ | 90d / 180d |
| Enterprise | Personalizado | 1 TB+ | 15,000+ | 120d / 365d |

Los límites específicos del contrato pueden aumentar o disminuir estos valores para un cliente específico. La validez del certificado de delegación también tiene un límite máximo de `subscription.expiresAt + 3 day grace`, por lo que las suscripciones facturadas mensualmente obtienen naturalmente certificados alineados con su ciclo de facturación. Consulta [Cadena de Licencias y Delegación - Política de Validez](/es/docs/license-chain) para conocer todas las reglas.

## Prueba Gratuita y el Plan de Respaldo Community

Los nuevos registros comienzan una prueba gratuita de 14 días en Professional o Business. Se solicita una tarjeta de crédito al registrarte, y el primer cobro se realiza solo cuando termina la prueba, así que cancelar antes no tiene ningún costo. Hay una prueba disponible por cliente.

Community es el nivel gratuito permanente. Ya no es una opción de registro directo para cuentas nuevas; en su lugar, una cuenta pasa a Community cuando termina una suscripción: al cancelar durante la prueba, al cancelar más tarde un plan pagado, o por un pago fallido. En el respaldo de Community conservas una máquina con 10 GB por repositorio y 100 setups al mes. Las cuentas creadas antes del lanzamiento del modelo basado en prueba conservan su acceso Community existente.

La aplicación de límites se mantiene flexible donde más importa: los repositorios en ejecución siguen funcionando incluso después de que termina una suscripción (`up`, `down`, `delete`, autostart). Más allá de eso rigen dos reglas distintas, y confundirlas es lo que hace que el margen de 60 días parezca incoherente:

- **Las operaciones que necesitan el servidor de cuenta** no pueden ocurrir sin una suscripción activa, porque el servidor se niega a firmar. Son `create`, `fork` y cualquier actualización o renovación de licencia. Una vez que la suscripción caduca, no se aprovisiona nada nuevo.
- **Las operaciones que solo necesitan una licencia instalada válida** siguen funcionando hasta que esa licencia expira de forma dura, sin servidor de por medio. Son `resize` y `expand` sobre repositorios que ya tienes, y la transferencia de copias de seguridad (`push`, `pull`, copias programadas). La licencia principal de un repositorio expira de forma dura 60 días después de la fecha de fin de la suscripción, y de ahí sale el margen de 60 días. La licencia de un fork vive mucho menos, con un tope de 7 días, y por eso las máquinas con muchos forks dependen de la autorrenovación que se describe más abajo.

Así que una suscripción caducada te impide de inmediato hacer crecer tu flota, y 60 días después te impide hacer crecer los repositorios que hay en ella.

## Período de Gracia de Migración de VM

Cuando un proveedor de alojamiento migra una VM a un hardware físico diferente, el ID de máquina cambia (se deriva de identificadores de hardware como UUID de DMI, `/etc/machine-id` y direcciones MAC de NIC). Las licencias de repositorio están vinculadas al ID de máquina, por lo que una migración normalmente invalidaría todas las licencias.

Para manejar esto de manera transparente, las licencias de repositorio incluyen un **período de gracia de ID de máquina de 40 días**. Si el ID de máquina no coincide pero la licencia se emitió hace menos de 40 días, la licencia aún se acepta. Como las licencias se actualizan cada 30 días, la siguiente actualización vincula automáticamente al nuevo ID de máquina.

En la práctica:
- VM migrada, ID de máquina cambia: los repositorios siguen ejecutándose (dentro de la ventana de 40 días)
- La siguiente operación `rdc` actualiza la licencia con el nuevo ID de máquina
- No se requiere intervención manual
- Verifica el ID de máquina y el estado de la licencia con `rdc machine status <machine> --system --licenses`

**Las cuentas del canal Edge** se ejecutan en el plan Community con el doble de los límites (repositorios de 20 GB, 200 setups/mes, 2 máquinas). Los planes pagados solo están disponibles en el canal Stable. Consulta [Canales de Release](/es/docs/release-channels) para más detalles.

## Qué sucede durante Repo Create, Up, Down y Restart

### Repo create y fork

Cuando creas o haces fork de un repositorio:

1. `rdc` garantiza que tu token de suscripción esté disponible (activa la autenticación de código de dispositivo si es necesario)
2. `rdc` pre-emite una licencia de repositorio desde el servidor de cuenta (el servidor verifica la cuota de ranura de máquina y los límites de issuance mensual en este punto)
3. La licencia de repositorio pre-emitida se escribe en la máquina y se valida localmente (firma, ID de máquina, GUID del repositorio, expiración y límite de tamaño)
4. Después de la creación exitosa, `rdc` re-emite la licencia de repositorio con pruebas de identidad del repositorio (UUID de LUKS o huella digital de almacenamiento)

Esa issuance respaldada por account cuenta para tu uso mensual de **issuances de licencia de repositorio**. Cada licencia contiene el correo electrónico del titular de la cuenta y el nombre de la empresa, que se registra cuando renet valida la licencia.

### Repo up, down y delete

`rdc` valida la licencia de repositorio instalada en la máquina pero **omite la verificación de expiración**. La firma, el ID de máquina, el GUID del repositorio y la identidad siguen siendo verificados. Los usuarios nunca quedan bloqueados de operar sus repositorios, incluso con una suscripción expirada.

### Repo resize y expand

`rdc` realiza validación completa de licencia de repositorio incluyendo expiración y límites de tamaño.

### Reinicio de máquina y autostart

Autostart utiliza las mismas reglas que `rdc repo up`: la expiración se omite, por lo que los repositorios siempre se reinician libremente.

Las licencias de repositorio utilizan un modelo de validez de larga duración:

- `refreshRecommendedAt` es el punto de actualización suave
- `hardExpiresAt` es el punto de bloqueo

Si la licencia de repositorio está desactualizada pero aún antes de la expiración dura, el tiempo de ejecución puede continuar. Una vez que alcanza la expiración dura, `rdc` debe actualizarla para operaciones de resize/expand.

### Otras operaciones de repositorio

Las operaciones como listar repositorios, inspeccionar información del repositorio y montar no requieren validación de licencia alguna.

## Verificando el estado y actualizando licencias

Inicio de sesión humano:

```bash
rdc subscription login
```

Inicio de sesión de automatización o agente de IA:

```bash
rdc subscription login --token "$REDIACC_TOKEN"
```

Para entornos no interactivos, establecer `REDIACC_TOKEN` es la opción más simple. El token debe tener alcance solo para las operaciones de suscripción y licencia de repositorio que necesita el agente.

Mostrar el estado de suscripción respaldado por account:

```bash
rdc subscription status
```

Mostrar detalles de activación de máquina para una máquina:

```bash
rdc subscription status -m hostinger
```

Mostrar detalles de licencia de repositorio instalada en una máquina:

```bash
rdc subscription status -m hostinger
```

Actualizar la licencia de un repositorio en una máquina:

```bash
rdc subscription refresh -m hostinger --repo my-app
```

El ref de `--repo` debe resolverse en tu configuración local de `rdc`. Un repositorio descubierto en la máquina pero ausente de la configuración local se rechaza: se informa como fallo y no se clasifica automáticamente.

En el primer uso, una operación de repositorio licenciado o copia de seguridad que no encuentra ninguna licencia de repositorio utilizable puede activar un cambio de autorización de account automáticamente. La CLI imprime una URL de autorización, intenta abrir el navegador en terminales interactivas y reintenta la operación una vez después de que la autorización e issuance tengan éxito.

En entornos no interactivos, la CLI no espera la aprobación del navegador. En su lugar, te dice que suministres un token con alcance limitado con `rdc subscription login --token ...` o `REDIACC_TOKEN`.

Para configuración de máquina por primera vez, consulta [Configuración de Máquina](/es/docs/setup).

## Autorrenovación de licencias

Todo lo anterior da por hecho que estás delante del teclado. Las copias de seguridad programadas no lo están, y ese es justo el caso para el que existe la autorrenovación.

Una copia de seguridad programada se valida en el nivel estricto, así que necesita una licencia que no haya expirado. La licencia de un fork tiene un tope de 7 días. Tus máquinas no guardan credenciales de cuenta por diseño, así que antes de la autorrenovación la copia de seguridad de un fork simplemente se paraba una semana después de crearlo, en silencio, a las tres de la madrugada.

### Cómo renueva una máquina sin tener ningún token

Cada licencia que Rediacc emite o renueva lleva una `renewalUrl`, la dirección completa del endpoint de renovación en el servidor de cuenta que la firmó. La máquina lee esa dirección de su propia licencia instalada, así que nunca hay que decirle dónde está su servidor de cuenta.

Después, la máquina presenta la licencia instalada a ese mismo endpoint. La licencia es su propia credencial: está firmada, el servidor verifica esa firma y en ningún momento interviene un token de API. El servidor devuelve una licencia nueva con ventanas de validez nuevas, y la máquina la instala y la vuelve a validar antes de dar la renovación por hecha.

La renovación es una operación de toda la máquina:

```bash
sudo renet license renew
```

Los repositorios se agrupan por el servidor que los firmó, así que una máquina que sirve a dos universos de cuenta contacta con cada uno una sola vez. Un archivo de bloqueo evita que dos renovaciones corran a la vez, y `--jitter` reparte una flota de máquinas que si no despertarían todas en punto.

El servidor rechaza una renovación en tres casos, y cada uno significa algo distinto:

| Rechazo | Qué significa |
|---|---|
| La suscripción ha caducado, está suspendida o ha pasado su período de gracia | Facturación. La renovación se reanuda sola en cuanto la suscripción vuelve a estar activa |
| El certificado de delegación está vencido o revocado | Configuración on-premise. Renueva el certificado en tu servidor on-premise y las máquinas volverán a renovar con normalidad |
| La identidad de la máquina ya no coincide y el margen de 40 días ha pasado | La licencia pertenece a una máquina que esta no es. Reemítela desde el contexto de la máquina actual |

Un rechazo nunca detiene toda la ejecución. Un repositorio caducado no bloquea la renovación de los demás de la misma máquina.

### Las copias de seguridad programadas se renuevan solas

Cada unidad de copia de seguridad que escribe Rediacc ejecuta antes una renovación:

```
ExecStartPre=-<renet> license renew --jitter 45s
```

El `-` inicial la marca como best effort a propósito. Una renovación rechazada, un corte de red o un Renet Agent antiguo que todavía no conoce el comando no deben tumbar nunca la copia de seguridad en sí. La copia se ejecuta, y la licencia se renueva de paso siempre que se pueda.

### Cuando una copia de seguridad queda bloqueada

Si las licencias sí rechazan una copia de seguridad, la máquina lo deja anotado. Esa marca es la única señal de que las copias sin supervisión han dejado de copiar datos, así que se muestra bien alto:

```bash
rdc machine status <machine> --licenses
```

La columna `backups` muestra `BLOCKED` con el motivo, y esa misma información se imprime debajo de la tabla como error para que no se pierda entre treinta repositorios. La columna `renewed` muestra cómo fue la última renovación sin supervisión, incluido el código de rechazo del servidor si lo hubo, que es lo que te dice si la solución es una cuestión de facturación o de certificado on-premise.

Una renovación correcta borra la marca, y una copia de seguridad que pasa su comprobación de licencia también. No hay nada que confirmar ni reiniciar a mano.

## Comportamiento sin conexión y expiración

La validación de licencia ocurre localmente en la máquina. No necesitas contactar al servidor de cuenta para operar tus repositorios.

Eso significa:

- un entorno en ejecución no necesita conectividad en vivo de account en cada comando
- todos los repositorios siempre pueden iniciarse, detenerse y eliminarse incluso con licencias expiradas, los usuarios nunca quedan bloqueados de operar sus propios repositorios
- las operaciones de aprovisionamiento (`create`, `fork`) requieren una licencia de repositorio pre-emitida, y las operaciones de crecimiento (`resize`, `expand`) requieren una licencia de repositorio válida
- las licencias de repositorio verdaderamente expiradas deben reemplazarse antes de resize/expand, ya sea a través de `rdc` desde tu estación de trabajo o renovándose la propia máquina
- las firmas de licencia se verifican contra una clave pública integrada, la verificación de firma no se puede desactivar

## Comportamiento de recuperación

La recuperación automática es intencionalmente estrecha:

- `missing`: `rdc` puede autorizar acceso a account si es necesario, actualizar licencias de repositorio en lote y reintentar una vez
- `expired`: `rdc` puede actualizar licencias de repositorio en lote e reintentar una vez
- `machine_mismatch`: falla rápidamente y te dice que re-emitas desde el contexto de máquina actual
- `repository_mismatch`: falla rápidamente y te dice que actualices licencias de repositorio explícitamente
- `sequence_regression`: falla rápidamente como problema de integridad/estado de licencia de repositorio
- `invalid_signature`: falla rápidamente como problema de integridad/estado de licencia de repositorio
- `identity_mismatch`: falla rápidamente, la identidad del repositorio no coincide con la licencia instalada
- `cert_expired`: falla rápido en las operaciones de crecimiento (`create`, `fork`, `resize`) y en la transferencia de copias de seguridad (`push`, `pull`); `repo up` y el autoarranque siguen funcionando, en línea con el modelo de vencimiento de licencia flexible. Renueva el certificado de delegación
- `cert_invalid`: falla rápido, el certificado de delegación incumplió una restricción (firma de clave maestra inválida, discrepancia de suscripción/plan, límite de tamaño o secuencia superior a `maxTotalIssuances`). Reemite el certificado tras corregir el límite subyacente

Estos casos de falla rápida no consumen automáticamente llamadas de actualización o issuance respaldadas por account.

Dos apuntes para leer esta lista:

- `missing` no siempre es un problema. También es el resultado normal la primera vez que se toca un repositorio dentro de un datastore recién forkeado, y es justo lo que hace que ese fork se mida: se emite la licencia, se reclama una ranura y la operación continúa. `identity_mismatch` es el opuesto deliberado, para que un archivo de licencia copiado desde otro datastore falle de inmediato en vez de reemitirse sin más.
- Esta lista describe la recuperación desde tu estación de trabajo. Una máquina que se renueva sola tiene sus propios resultados, que se informan mediante `rdc machine status <machine> --licenses` en lugar de lanzarse como fallo del comando, porque una copia de seguridad programada no tiene a nadie a quien avisar.

## Certificados de delegación para On-Premise

Para implementaciones on-premise y aisladas del aire, esto se vuelve complejo. El servidor de account ascendente emite un **certificado de delegación** que autoriza tu instalación on-premise a firmar licencias con su propia clave Ed25519. Esto te limita a tus límites de plan y crea una cadena evidente de manipulación.

Puntos clave para propietarios de suscripción:

- **Un certificado activo por suscripción.** Cada instalación on-premise aplica cuotas mensuales y por máquina contra su propio libro mayor local, por lo que multi-instalación multiplicaría la cuota efectiva sin posible reconciliación. Los clientes que necesitan producción, staging y DR deben comprar una suscripción por instalación.
- **Validez basada en nivel** (15d / 60d / 90d / 120d) y límites máximos (30d / 120d / 180d / 365d) - consulta la tabla de límites anterior.
- **Auto-servicio desde el portal de cliente.** Los propietarios de org y administradores pueden crear, renovar y revocar certificados de delegación en `/account/delegation-certs`. La página es visible para todos los clientes independientemente del nivel de plan - solo los límites difieren.
- **Auto-renovación** es compatible a través de un bootstrap de un clic que acuña un token de API con alcance `delegation:renew` para que on-premise lo use para llamadas de renovación ascendentes.
- **Renovación aislada del aire** es compatible a través de un manifiesto de solicitud de renovación firmado que el administrador on-premise descarga, transfiere sin conexión al ascendente, y el ascendente procesa para emitir un nuevo certificado.

Consulta [Instalación On-Premise - Licencias para Implementaciones Aisladas del Aire](/es/docs/on-premise) para la configuración operativa, y [Cadena de Licencias y Delegación](/es/docs/license-chain) para el diseño criptográfico.

## Issuances de licencia de repositorio mensual

Esta métrica cuenta actividad exitosa de issuance de licencia de repositorio respaldada por account en el mes calendario UTC actual.

Incluye:

- issuance de licencia de repositorio por primera vez
- actualización exitosa de licencia de repositorio que devuelve una licencia recientemente firmada

No incluye:

- entradas de lote sin cambios
- intentos fallidos de issuance
- repositorios no rastreados rechazados antes de la issuance

Si necesitas una vista con datos del cliente de uso e historial de issuance de licencia de repositorio reciente, usa el portal de account. Si necesitas inspección del lado de la máquina, usa `rdc subscription status -m` y `rdc subscription status -m`.
