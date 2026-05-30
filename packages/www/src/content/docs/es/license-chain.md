---
title: "Cadena de Licencias y Delegación"
description: "Emisión de licencias con evidencia de manipulación, firma delegada para on-premise y detección de bifurcaciones."
category: "Guides"
order: 8
language: es
sourceHash: "9b062d6866c1ccb4"
sourceCommit: "4e60a12e0664cdee5ad9079a7b75e2d05980d0f5"
---

# Cadena de Licencias y Delegación

Rediacc usa una cadena de hashes con evidencia de manipulación para la emisión de licencias y un modelo de certificado de delegación para despliegues on-premise. Esta página explica cómo el sistema protege contra manipulaciones, ataques de repetición y compartir licencias.

## ¿Por qué una Cadena?

Cada licencia emitida por un servidor de cuentas se registra en un libro de contabilidad de solo adición. Cada entrada está vinculada a la anterior mediante un hash SHA-256, formando una cadena. La cadena tiene tres propiedades que hacen detectable la manipulación:

1. Los **números de secuencia** son globales y monotónicos por suscripción. Omitir o reordenar entradas rompe la cadena.
2. Los **hashes de cadena** vinculan cada entrada a todas las entradas anteriores. Modificar cualquier entrada pasada invalida cada entrada que la sigue.
3. **Renet almacena la secuencia más alta que ha visto** por suscripción. Un servidor que revierte su secuencia se detecta de inmediato.

## Cómo se Emite una Licencia

Cuando el CLI solicita una activación de máquina o una licencia de repositorio, el servidor de cuentas:

1. Lee el encabezado de la cadena actual (última secuencia + hash) para la suscripción.
2. Construye el payload de la licencia con el siguiente número de secuencia y el hash de cadena anterior incorporados.
3. Firma el payload con Ed25519.
4. Calcula `chainHash = SHA256(prevChainHash + ":" + signedPayload)`.
5. Agrega la entrada al libro de contabilidad de emisión atómicamente. Si dos solicitudes concurrentes colisionan en la misma secuencia, la perdedora readquiere la siguiente secuencia y re-firma.
6. Devuelve el blob firmado con el hash de cadena al CLI.

El `sequence` y `prevChainHash` están dentro del payload firmado (por lo que no pueden modificarse sin invalidar la firma). El `chainHash` está en el sobre (calculado después de firmar para evitar una dependencia circular).

## Cómo Valida Renet

Cada máquina que ejecuta Renet almacena su último estado de cadena conocido en `{licenseDir}/chain-state.json`. En cada validación de licencia, Renet verifica:

| Verificación | El fallo significa |
|---|---|
| La firma Ed25519 es válida | La licencia fue falsificada o manipulada |
| `sequence > lastKnownSequence` | El servidor retrotrajo la cadena (ataque de repetición) |
| `chainHash == SHA256(prevChainHash + ":" + payload)` | La entrada de la cadena fue modificada |
| `issuedAt >= lastKnownIssuedAt` | Manipulación del reloj (reloj del servidor retrasado) |

Si alguna verificación falla, la licencia se rechaza y se reporta el motivo del fallo.

## Certificados de Delegación (On-Premise)

Para despliegues sin acceso a internet o auto-alojados, el servidor de cuentas upstream emite un **certificado de delegación** que autoriza a un servidor on-premise a firmar licencias con su propia clave Ed25519. El certificado restringe lo que el servidor on-premise puede hacer.

### Estructura del certificado

Un certificado de delegación contiene:

- `subscriptionId` - a qué suscripción aplica este certificado
- `planCode`, `maxMachines`, `maxRepositorySizeGb`, `maxRepoLicenseIssuancesPerMonth` - límites del plan incorporados
- `maxTotalIssuances` - límite superior en el número de secuencia de la cadena
- `delegatedPublicKey` - la clave pública Ed25519 del servidor on-premise (SPKI base64)
- `genesisHash` - el punto de inicio de la cadena (continuación del certificado anterior, o "genesis")
- `genesisSequence` - secuencia de la cadena en el momento de emisión. Usado por `/onprem/cert-upload` para validar que el nuevo certificado enlaza con una entrada conocida en el libro de contabilidad de emisión local cuando la cadena ha avanzado durante el tránsito. Opcional para compatibilidad retroactiva (tratado como 0 si falta).
- `validFrom`, `validUntil` - ventana de validez (regida por la política de validez a continuación)
- Firmado por la clave maestra Ed25519 upstream

### Cómo funciona la delegación

1. El administrador Enterprise genera un par de claves Ed25519 en el servidor on-premise.
2. El administrador solicita un certificado de delegación al upstream:
   ```
   POST /admin/delegation-certs
   { subscriptionId, validDays: 90, delegatedPublicKey: "MCowBQYDK2VwAyEA..." }
   ```
3. El upstream firma el certificado con su clave maestra y lo devuelve.
4. El servidor on-premise almacena el certificado y su clave privada, listo para firmar licencias.
5. Cuando un CLI solicita una licencia al servidor on-premise, el servidor firma con su clave delegada e incluye una referencia al certificado.
6. Renet realiza **validación en dos niveles**:
   - Verifica la firma del certificado contra la clave maestra upstream incorporada.
   - Verifica la firma del blob contra la clave delegada del certificado.
   - Verifica que `blob.sequence <= cert.maxTotalIssuances`.
   - Aplica todas las verificaciones estándar de la cadena.

El servidor on-premise no puede:
- Falsificar una licencia fuera de los límites del plan del certificado de delegación (renet la rechaza).
- Emitir más de `maxTotalIssuances` operaciones en total (renet rechaza el desbordamiento de secuencia).
- Modificar el certificado (la firma upstream se rompe).

## Política de Validez

La ventana de validez de un certificado de delegación la calcula un helper de política compartido (`computeDelegationCertValidity()`) que se ejecuta tanto en el backend upstream como en el frontend del portal del cliente. Las mismas entradas siempre producen el mismo `validUntil`, para que los clientes puedan obtener una vista previa de la validez efectiva en el modal de creación antes de enviar.

### Valores predeterminados y límites por plan

| Plan | Validez predeterminada | Límite del plan |
|---|---|---|
| COMMUNITY | 15 días | 30 días |
| PROFESSIONAL | 60 días | 120 días |
| BUSINESS | 90 días | 180 días |
| ENTERPRISE | 120 días | 365 días |

El valor predeterminado es el que elige el endpoint de creación cuando el caller omite `validDays`. El límite es el máximo que el caller puede solicitar.

### Anulación por suscripción

Los administradores pueden establecer un valor personalizado de `delegationCertDefaultDays` en una suscripción específica a través de la página de Detalle de Suscripción del administrador. **La anulación reemplaza tanto el valor predeterminado como el límite para esa suscripción.** Es una salida de emergencia para clientes especiales (por ejemplo, un contrato enterprise que necesita un certificado de 200 días en un plan COMMUNITY). El esquema Zod todavía aplica un rango absoluto de `1..365`.

### Límite máximo: fin de suscripción + 3 días de gracia

Independientemente del límite del plan y de la anulación, cada certificado tiene un límite máximo en `subscription.expiresAt + 3 días` (el `SUBSCRIPTION_CONFIG.gracePeriodDays` existente). Esto significa:

- Para suscripciones perpetuas (`expiresAt = null`), no se aplica límite de vencimiento - solo el límite del plan.
- Para suscripciones mensuales facturadas por Stripe, el límite es aproximadamente la próxima fecha de facturación + 3 días. Cuando Stripe avanza `expiresAt` cada mes, el límite se mueve con él.
- Para suscripciones de prueba, el límite es el fin de la prueba + 3 días.

### Días efectivos y motivo

Cada respuesta de creación/renovación incluye `effectiveDays` y `reason` para que el caller pueda ver exactamente por qué el certificado obtuvo la validez que obtuvo:

| Motivo | Significado |
|---|---|
| `plan_default` | Sin solicitud, sin anulación - se usó el valor predeterminado por plan |
| `subscription_override` | Sin solicitud - se usó la anulación por suscripción como valor predeterminado |
| `requested` | Solicitud del caller aceptada dentro de todos los límites |
| `plan_max_clamp` | La solicitud del caller excedió el límite del plan - reducida |
| `override_max_clamp` | La solicitud del caller excedió la anulación por suscripción - reducida |
| `subscription_cap_clamp` | El objetivo válido sobreviviría a `expiresAt + 3 días` de la suscripción |

El modal de creación del portal del cliente usa estos motivos para mostrar una vista previa en tiempo real ("Recibirás un certificado de 18 días. Reducido porque el certificado no puede sobrevivir a la fecha de vencimiento de tu suscripción en más de 3 días.") para que los clientes no envíen a ciegas.

### Umbral de renovación adaptativo

El ciclo de renovación automática on-premise usa un umbral adaptativo inspirado en Let's Encrypt:

```
effectiveThresholdDays = min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))
```

Un certificado COMMUNITY de 15 días renueva a los 5 días restantes. Un certificado BUSINESS de 90 días renueva a los 14 días restantes (el límite configurado en el entorno entra en acción). Un certificado ENTERPRISE de 120 días renueva a los 14 días restantes. Esto evita que los certificados de corta duración activen la renovación de inmediato, al tiempo que proporciona un margen cómodo a los de larga duración.

## Aplicación de Activo Único

Una suscripción puede tener **como máximo un certificado de delegación activo a la vez** (`MAX_ACTIVE_DELEGATION_CERTS_PER_SUBSCRIPTION = 1`).

### ¿Por qué uno?

Cada instalación on-premise aplica `maxRepoLicenseIssuancesPerMonth`, `maxActivations` e integridad de la cadena contra su propio libro de contabilidad de emisión local. El on-premise no sincroniza recuentos de uso con el upstream. Ese es el objetivo completo de la delegación con capacidad offline.

Si una suscripción tuviera múltiples certificados activos (uno por instalación), cada instalación aplicaría el límite de forma independiente:

- Una suscripción de 500/mes con 3 certificados activos permite hasta **1.500 emisiones/mes** en la práctica.
- Tres cadenas paralelas, cada una anclada al genesis, sin posible reconciliación de auditoría.

El upstream no puede detectar esta evasión porque los on-prems están diseñados para operar sin conexión. **El activo único es el único modelo aplicable.** Los clientes con múltiples instalaciones (producción + staging + DR) deben comprar una suscripción por instalación.

### Comportamiento de colisión

`POST /admin/delegation-certs` y `POST /portal/delegation-certs` rechazan una segunda creación con:

```json
HTTP/1.1 409 Conflict
{
  "code": "DELEGATION_CERT_ALREADY_ACTIVE",
  "existingCertId": "...",
  "actions": {
    "renew": "POST /portal/delegation-certs/process-renewal-request (preserves chain)",
    "revokeAndCreate": "POST /portal/delegation-certs/{existingCertId}/revoke then retry create"
  }
}
```

El portal del cliente muestra esto con un diálogo dedicado que explica las consecuencias:

- **Renovar (recomendado)** - extiende la cadena existente. Todas las licencias de repositorio emitidas anteriormente siguen funcionando.
- **Revocar y Crear** - descarta la cadena existente y comienza desde el genesis. Las licencias de repositorio emitidas anteriormente se vuelven inverificables una vez que pase el `validUntil` del certificado ANTERIOR. Usar solo cuando has migrado a un nuevo on-prem con una clave de firma diferente, o al recuperarse de una clave comprometida.

`renew()` es el intercambio atómico que preserva el activo único y **no** está sujeto a la verificación de colisión 409 del lado de creación.

### Límite de tasa

Incluso con activo único, un caller malicioso podría hacer un bucle `revocar -> crear -> revocar -> crear` para consumir ciclos de firma de la clave maestra upstream. Ambos endpoints de creación limitan a **10 intentos por 24h continuas** por suscripción a través de la tabla `rateLimits` existente:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 78234
{ "code": "DELEGATION_CERT_RATE_LIMITED", "retryAfterSec": 78234 }
```

El contador se incrementa en cada intento independientemente del resultado (los bucles de spam de colisión también se limitan).

## Detección de Bifurcaciones

Si un cliente comparte su certificado de delegación con otra parte (o ejecuta dos servidores on-premise con el mismo certificado), las cadenas divergen. El upstream lo detecta en el momento de la renovación.

### Flujo de renovación

1. El administrador on-premise llama a `POST /admin/delegation-certs/renew` con el encabezado de la cadena actual:
   ```
   { subscriptionId, currentChainHash, currentSequence, delegatedPublicKey }
   ```
2. El upstream recorre las entradas de la cadena contra su propio registro en el libro de contabilidad.
3. Si `currentChainHash` no coincide con la cadena registrada del upstream en `currentSequence`, se detecta bifurcación:
   ```
   409 { code: 'CHAIN_FORK_DETECTED', divergedAtSequence: N }
   ```
4. El `genesisHash` del nuevo certificado se establece en el hash de cadena actual, para que las máquinas con el estado de cadena anterior puedan continuar desde donde lo dejaron.

Si el certificado se comparte con un no-cliente:
- Pueden usarlo durante el período de validez del certificado.
- En la primera renovación, el upstream ve solo una cadena (la legítima).
- El `genesisHash` del nuevo certificado solo coincide con la cadena legítima.
- Las máquinas en la cadena compartida rechazarán las nuevas licencias de inmediato porque su `chainHash` almacenado no conecta con el `genesisHash` del nuevo certificado.

## Renovación Sin Conexión

Para instalaciones on-premise sin acceso HTTPS saliente al upstream, el flujo de renovación es completamente offline. Hay tres nuevos endpoints que cierran el ciclo:

**En el on-premise (`auth, root, requireElevated()`):**
- `GET /onprem/cert-current` - descargar el certificado firmado actualmente cargado (respaldo, auditoría, re-importación)
- `GET /onprem/renewal-request` - generar un manifiesto firmado que contiene el encabezado de la cadena local + clave pública delegada, firmado por la clave privada on-premise

**En el upstream (root del sistema administrativo o del portal de alcance org):**
- `POST /admin/delegation-certs/process-renewal-request` (root del sistema entre clientes)
- `POST /portal/delegation-certs/process-renewal-request` (propietario/admin de la org)

### Manifiesto de solicitud de renovación

La solicitud de renovación es un pequeño documento JSON:

```json
{
  "manifest": {
    "schemaVersion": 1,
    "generatedAt": "2026-04-15T12:00:00.000Z",
    "subscriptionId": "...",
    "currentChainHash": "...",
    "currentSequence": 42,
    "delegatedPublicKey": "MCowBQYDK2VwAyEA...",
    "currentCertValidUntil": "...",
    "currentCertPublicKeyId": "...",
    "currentCertId": null
  },
  "signature": "<base64 Ed25519>",
  "publicKeyId": "..."
}
```

La firma se calcula sobre la codificación canónica del manifiesto (claves ordenadas alfabéticamente, luego `JSON.stringify`) usando la clave privada on-premise. Esto garantiza que ambos lados calculen bytes idénticos independientemente del orden de construcción del objeto.

### Verificación en el upstream

`processRenewalManifest()` ejecuta cinco verificaciones:

1. **Existe un certificado activo** para la suscripción del manifiesto. Devuelve `404 NO_ACTIVE_CERT` en caso contrario - el cliente debe usar el flujo de creación, no renovar.
2. **La clave pública delegada coincide** con el certificado activo. Devuelve `400 DELEGATED_KEY_MISMATCH` en caso contrario - protege contra repetición desde un on-prem diferente.
3. **La firma del manifiesto verifica** contra el `delegatedPublicKey` del certificado activo. Devuelve `400 MANIFEST_SIGNATURE_INVALID` en caso contrario - prueba que el manifiesto provino de un titular de la clave privada on-premise.
4. **La edad del manifiesto** es de 7 días o menos (`RENEWAL_MANIFEST_MAX_AGE_MS`). Devuelve `400 MANIFEST_EXPIRED` en caso contrario - ancla anti-repetición.
5. **El enlace del hash de cadena** en el `currentSequence` del manifiesto coincide con el libro de contabilidad del upstream. Devuelve `409 CHAIN_FORK_DETECTED` en caso contrario - protege contra cadenas bifurcadas.

Si todas las verificaciones pasan, `processRenewalManifest` llama al flujo `renew()` existente, que expira atómicamente el certificado anterior e inserta uno nuevo. **No está sujeto al 409 de activo único del lado de creación** porque es un intercambio atómico, no un revocar+crear en 2 pasos.

### Avance de secuencia durante el tránsito

Un manifiesto de solicitud de renovación captura el encabezado de la cadena en el momento de generación. Mientras el manifiesto está en tránsito (entrega USB, correo electrónico cifrado), el on-premise puede seguir emitiendo licencias de repositorio, avanzando su cadena local.

Cuando el nuevo certificado se sube de vuelta al on-premise, `/onprem/cert-upload` valida que el `genesisSequence` del nuevo certificado todavía enlaza con una entrada conocida en el libro de contabilidad de emisión local:

- Si `cert.genesisSequence > localHead.sequence` devuelve `409 CHAIN_HEAD_BEHIND` (el upstream está en una cadena bifurcada).
- Si `cert.genesisSequence > 0` y la entrada del libro de contabilidad local en esa secuencia tiene un `chainHash` diferente al `cert.genesisHash` devuelve `409 CHAIN_FORK_ON_UPLOAD` (la cadena local ha divergido).
- En caso contrario, el certificado se acepta. Las emisiones futuras continúan desde `localHead.sequence + 1`.

Esto significa que **no se requiere congelación de escritura durante el tránsito**. La cadena se extiende naturalmente en ambos lados. Es análogo a cómo la renovación de certificados X.509 maneja números de serie en vuelo.

## Auditoría Periódica

El upstream proporciona un endpoint de auditoría para verificar la integridad de la cadena sin renovar el certificado:

```
POST /admin/delegation-certs/audit
{ subscriptionId, chainEntries: [{ sequence, chainHash }, ...] }
```

El upstream recorre las entradas y devuelve `{ valid: true }` o `{ valid: false, divergedAtSequence: N, expected, actual }`.

Los servidores on-premise deben llamar a este endpoint periódicamente (predeterminado: semanalmente via la variable de entorno `UPSTREAM_AUDIT_URL`) para detectar bifurcaciones de forma temprana.

### Pruebas de auditoría del lado de la máquina

Renet puede verificar la continuidad de la cadena localmente usando `VerifyAuditProof`. Cuando una máquina renueva su licencia después de un largo período, el servidor puede devolver las entradas de cadena intermedias como prueba. La máquina recorre la prueba para verificar que cada `chainHash` se deriva del `prevHash + blobHash` anterior via SHA-256, detectando cualquier manipulación sin contactar al upstream.

## Seguridad de Concurrencia

D1 (la base de datos de Cloudflare) no admite transacciones interactivas. La emisión de licencias concurrente para la misma suscripción podría colisionar en el número de secuencia. El servidor de cuentas maneja esto:

1. Leyendo la siguiente secuencia + hash de cadena anterior.
2. Construyendo y firmando el blob con esa secuencia incorporada.
3. Insertando la entrada del libro de contabilidad con `onConflictDoNothing`.
4. Si la inserción devuelve 0 filas modificadas, la secuencia fue reclamada por otra solicitud - readquiere la secuencia, reconstruye, **re-firma** y reintenta.
5. Después de 10 intentos fallidos, falla con un error.

El detalle crítico: el reintento **re-firma** el blob. Un reintento ingenuo que solo actualizara la entrada del libro de contabilidad dejaría el blob firmado con un número de secuencia obsoleto, rompiendo la cadena.

## Transporte de Correo

El servidor de cuentas puede enviar correos electrónicos transaccionales (magic links, restablecimientos de contraseña, notificaciones de seguridad) a través de dos transportes intercambiables:

| Transporte | Configuración |
|---|---|
| `ses` (predeterminado) | `AWS_SES_ACCESS_KEY_ID`, `AWS_SES_SECRET_ACCESS_KEY`, `AWS_SES_REGION`, `AWS_SES_FROM` |
| `smtp` | `EMAIL_TRANSPORT=smtp`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SECURE`, `SMTP_FROM` |

Ambos transportes funcionan para despliegues en la nube y on-premise. Elige el que mejor se adapte a tu infraestructura: AWS SES con tu propia cuenta de AWS, o cualquier servidor SMTP (Microsoft Exchange, Postfix, SendGrid, Mailgun, etc.).

El transporte se selecciona al inicio mediante la variable de entorno `EMAIL_TRANSPORT`. SMTP usa agrupación de conexiones y carga diferida, por lo que la biblioteca del cliente SMTP solo se inicializa si se selecciona SMTP.

Todas las plantillas de correo electrónico y la API de correo pública son idénticas en todos los transportes.

## Documentación Relacionada

- [Instalación On-Premise](/es/docs/on-premise) - cómo desplegar el servidor on-premise
- [Suscripción y Licencias](/es/docs/subscription-licensing) - límites del plan y slots de máquinas
- [Canales de Release](/es/docs/release-channels) - canales edge vs stable
- [Regiones de Datos](/es/docs/data-regions) - residencia de datos regional
