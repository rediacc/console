---
title: Suscripciones y Licencias
description: >-
  Comprenda cómo account, rdc y renet administran ranuras de máquina, licencias
  de repositorio y límites de plan.
category: Guides
order: 7
language: es
sourceHash: 10e9f781881854be
sourceCommit: 2e3862505c06f97f846b7d879375434011954f95
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
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

También puedes inyectar el token directamente a través del entorno para que la CLI pueda emitir y actualizar licencias de repositorio sin ningún paso de inicio de sesión interactivo:

```bash
export REDIACC_SUBSCRIPTION_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## Ranuras de máquina y licencias de repositorio

### Ranuras de máquina (lado del servidor)

El seguimiento de ranura de máquina se aplica del lado del servidor. Cuando la CLI emite una licencia de repositorio, el servidor de cuenta verifica la cuota de ranura de máquina de la suscripción (por ejemplo, 2 máquinas para Community, 3 para Professional). Se mantiene una ranura durante 5 horas desde la última emisión de licencia de repositorio en esa máquina y se libera automáticamente después de la inactividad. Un plan Business de 10 ranuras puede cubrir docenas de máquinas a lo largo del tiempo, ya que las ranuras solo se mantienen mientras aprovisionas activamente.

No se almacena ningún archivo de licencia de máquina en la máquina. La aplicación de ranura ocurre en el momento de la issuance en el servidor.

### Licencia de repositorio

Una licencia de repositorio es una licencia firmada para un repositorio en una máquina. Es el único archivo de licencia almacenado en la máquina (`/var/lib/rediacc/license/repos/{guid}.json`).

Se utiliza para:

- `rdc repo create` y `rdc repo fork`, validadas antes del aprovisionamiento (pre-emitidas sin pruebas de identidad, luego re-emitidas con pruebas de identidad después de la creación)
- `rdc repo resize` y `rdc repo expand`, validación completa incluyendo expiración
- `rdc repo up`, `rdc repo down`, `rdc repo delete`, validadas con **expiración omitida**
- `rdc repo push`, `rdc repo pull`, `rdc repo sync`, validadas con **expiración omitida**
- autostart de repositorio en reinicio de máquina, validadas con **expiración omitida**

Las licencias de repositorio están vinculadas a la máquina y al repositorio de destino. Cada licencia contiene el ID de máquina, GUID del repositorio, ID de suscripción, límites de plan y expiración. Para repositorios encriptados, Rediacc también verifica la identidad LUKS del volumen subyacente.

Múltiples suscripciones pueden coexistir en la misma máquina. Cada repositorio tiene su propia licencia con su propio contexto de suscripción.

## Límites predeterminados

El tamaño del repositorio depende del nivel de derecho:

- Community: hasta `10 GB`
- planes pagados: límite de plan o contrato

Los límites predeterminados de planes pagados son:

| Plan | Licencias Flotantes | Tamaño de Repositorio | Issuances de licencia de repositorio mensuales | Delegación cert predeterminado / máximo |
|------|-------------------|-----------------|-------------------------------|---|
| Community | 2 | 10 GB | 100 | 15d / 30d |
| Professional | 3 | 50 GB | 2,000+ | 60d / 120d |
| Business | 10 | 200 GB | 5,000+ | 90d / 180d |
| Enterprise | 25+ | 1 TB+ | 15,000+ | 120d / 365d |

Los límites específicos del contrato pueden aumentar o disminuir estos valores para un cliente específico. La validez del certificado de delegación también tiene un límite máximo de `subscription.expiresAt + 3 day grace`, por lo que las suscripciones facturadas mensualmente obtienen naturalmente certificados alineados con su ciclo de facturación. Consulta [Cadena de Licencias y Delegación - Política de Validez](/es/docs/license-chain) para conocer todas las reglas.

## Período de Gracia de Migración de VM

Cuando un proveedor de alojamiento migra una VM a un hardware físico diferente, el ID de máquina cambia (se deriva de identificadores de hardware como UUID de DMI, `/etc/machine-id` y direcciones MAC de NIC). Las licencias de repositorio están vinculadas al ID de máquina, por lo que una migración normalmente invalidaría todas las licencias.

Para manejar esto de manera transparente, las licencias de repositorio incluyen un **período de gracia de ID de máquina de 40 días**. Si el ID de máquina no coincide pero la licencia se emitió hace menos de 40 días, la licencia aún se acepta. Como las licencias se actualizan cada 30 días, la siguiente actualización vincula automáticamente al nuevo ID de máquina.

En la práctica:
- VM migrada, ID de máquina cambia: los repositorios siguen ejecutándose (dentro de la ventana de 40 días)
- La siguiente operación `rdc` actualiza la licencia con el nuevo ID de máquina
- No se requiere intervención manual
- Verifica el ID de máquina y el estado de la licencia con `rdc machine query --system --licenses --name <machine>`

**Usuarios del canal Edge** reciben 2X los límites de Community sin costo alguno (repositorios de 20 GB, 200 issuances/mes, 4 máquinas). Los planes pagados solo están disponibles en el canal Stable. Consulta [Canales de Release](/es/docs/release-channels) para más detalles.

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
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

Para entornos no interactivos, establecer `REDIACC_SUBSCRIPTION_TOKEN` es la opción más simple. El token debe tener alcance solo para las operaciones de suscripción y licencia de repositorio que necesita el agente.

Mostrar el estado de suscripción respaldado por account:

```bash
rdc subscription status
```

Mostrar detalles de activación de máquina para una máquina:

```bash
rdc subscription activation status -m hostinger
```

Mostrar detalles de licencia de repositorio instalada en una máquina:

```bash
rdc subscription repo status -m hostinger
```

Actualizar en lote licencias de repositorio en una máquina:

```bash
rdc subscription refresh repos -m hostinger
```

Los repositorios descubiertos en la máquina pero faltantes en la configuración local de `rdc` se rechazan durante la actualización en lote. Se informan como fallos y no se clasifican automáticamente.

Forzar una actualización de licencia de repositorio para un repositorio existente:

```bash
rdc subscription refresh repo --name my-app -m hostinger
```

En el primer uso, una operación de repositorio licenciado o copia de seguridad que no encuentra ninguna licencia de repositorio utilizable puede activar un cambio de autorización de account automáticamente. La CLI imprime una URL de autorización, intenta abrir el navegador en terminales interactivas y reintenta la operación una vez después de que la autorización e issuance tengan éxito.

En entornos no interactivos, la CLI no espera la aprobación del navegador. En su lugar, te dice que suministres un token con alcance limitado con `rdc subscription login --token ...` o `REDIACC_SUBSCRIPTION_TOKEN`.

Para configuración de máquina por primera vez, consulta [Configuración de Máquina](/es/docs/setup).

## Comportamiento sin conexión y expiración

La validación de licencia ocurre localmente en la máquina. No necesitas contactar al servidor de cuenta para operar tus repositorios.

Eso significa:

- un entorno en ejecución no necesita conectividad en vivo de account en cada comando
- todos los repositorios siempre pueden iniciarse, detenerse y eliminarse incluso con licencias expiradas, los usuarios nunca quedan bloqueados de operar sus propios repositorios
- las operaciones de aprovisionamiento (`create`, `fork`) requieren una licencia de repositorio pre-emitida, y las operaciones de crecimiento (`resize`, `expand`) requieren una licencia de repositorio válida
- las licencias de repositorio verdaderamente expiradas deben actualizarse a través de `rdc` antes de resize/expand
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

Estos casos de falla rápida no consumen automáticamente llamadas de actualización o issuance respaldadas por account.

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

Si necesitas una vista con datos del cliente de uso e historial de issuance de licencia de repositorio reciente, usa el portal de account. Si necesitas inspección del lado de la máquina, usa `rdc subscription activation status -m` y `rdc subscription repo status -m`.
