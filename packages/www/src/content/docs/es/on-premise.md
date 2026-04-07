---
title: "Instalación en Infraestructura Propia"
description: "Ejecutar el servidor de cuentas y la distribución del CLI en tu propia infraestructura."
category: "Guides"
order: 5
language: es
sourceHash: "bd53b8bc522532de"
sourceCommit: "a97009927c347f7090e4f4f60f3948997654ae4b"
---

Rediacc puede ejecutarse completamente en tu propia infraestructura. La imagen Docker independiente incluye el servidor de cuentas, el portal web, el sitio de marketing y el endpoint de distribución del CLI. No se requieren dependencias externas de los servicios alojados de Rediacc.

## Imagen Docker

Descarga la imagen independiente:

```bash
docker pull ghcr.io/rediacc/server:stable
```

Ejecuta con la configuración predeterminada:

```bash
docker run -p 80:80 -p 443:443 ghcr.io/rediacc/server:stable
```

La imagen sirve:
- API de cuentas en `/account/api/v1/`
- Portal web en `/account/`
- Sitio de marketing en `/`
- Artefactos del CLI en `/releases/`
- Binarios de Renet en `/bin/`

## Instalación del CLI desde tu Servidor

Los usuarios pueden instalar el CLI directamente desde tu servidor on-premise. El script de instalación detecta automáticamente el canal de actualizaciones y configura el CLI para verificar actualizaciones en tu servidor.

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com bash
```

Este único comando:
1. Descarga el binario del CLI desde el endpoint `/releases/` de tu servidor
2. Consulta `/account/api/v1/.well-known/server-info` para descubrir el canal de actualizaciones
3. Escribe `server.json` con la URL de tu servidor, el canal de actualizaciones y las claves de cifrado
4. Configura `rdc update` para verificar actualizaciones en tu servidor en el futuro

No se necesita la variable `REDIACC_CHANNEL`. El script de instalación lee el canal de la configuración de tu servidor automáticamente.

## Configuración del CLI con Configs con Nombre

Para usuarios que se conectan a múltiples servidores (on-premise, producción, edge), las configs con nombre mantienen cada entorno aislado:

```bash
# Crear una config para tu servidor on-premise
rdc config init --name myserver --server https://account.example.com

# Iniciar sesión usando esa config
rdc --config myserver subscription login

# Todos los comandos con --config usan el servidor on-premise
rdc --config myserver machine query --name prod-1
```

Cada config con nombre almacena su propia URL del servidor de cuentas y token de suscripción. Cambiar de config cambia todo el contexto del servidor.

## Entornos Sin Acceso a Internet

Para entornos sin acceso a internet, configura tanto la URL del servidor como una URL de releases personalizada:

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com \
  REDIACC_RELEASES_URL=https://account.example.com/releases \
  bash
```

El CLI verificará `account.example.com/releases/cli/stable/manifest.json` para actualizaciones en lugar del CDN público de releases.

Si el servidor está completamente sin conexión, instala el CLI via npm desde el tarball incluido:

```bash
npm install -g https://account.example.com/npm/rediacc-cli-latest.tgz
```

## Referencia de Variables de Entorno

| Variable | Usada por | Propósito |
|---|---|---|
| `REDIACC_SERVER_URL` | Script de instalación | URL del servidor de cuentas. Detecta automáticamente el canal y las claves de cifrado. |
| `REDIACC_RELEASES_URL` | Script de instalación, actualizador del CLI | Endpoint de releases personalizado para binarios del CLI. Predeterminado: `https://releases.rediacc.com` |
| `REDIACC_CHANNEL` | Script de instalación | Sobreescribe el canal de actualizaciones. Se detecta automáticamente desde el servidor si no se configura. |
| `REDIACC_ACCOUNT_SERVER` | Tiempo de ejecución del CLI | Sobreescribe la URL del servidor de cuentas para todos los comandos del CLI. |
| `RDC_UPDATE_CHANNEL` | Tiempo de ejecución del CLI | Sobreescribe el canal de actualizaciones para `rdc update`. |

## Configuración del Servidor

La imagen Docker on-premise usa la misma variable `ENVIRONMENT` que el servicio alojado. Configúrala en tu entorno Docker o en la configuración de orquestación:

- `ENVIRONMENT=production` (predeterminado): límites estándar, canal de actualizaciones stable recomendado a los clientes
- `ENVIRONMENT=edge`: 2X de límites Community, canal de actualizaciones edge recomendado a los clientes

Consulta [Canales de Release](/es/docs/release-channels) para más detalles sobre lo que proporciona cada entorno.

## Qué le Comunica el Servidor al CLI

Cuando el CLI se conecta a tu servidor, consulta `/.well-known/server-info` para descubrir:

- **Clave pública de cifrado E2E**: para almacenamiento de configuración de conocimiento cero
- **Versión mínima del CLI**: bloquea CLIs desactualizados de conectarse
- **Canal de actualizaciones**: indica al CLI qué canal de release usar para las actualizaciones
- **Entorno**: si se trata de un despliegue de producción o edge

Esta autoconfiguración significa que los usuarios solo necesitan la URL del servidor. Todo lo demás se descubre automáticamente.

## Licencias para Despliegues Sin Acceso a Internet

Los servidores on-premise sin acceso a internet y los auto-alojados emiten licencias localmente usando un **certificado de delegación** firmado por la clave maestra upstream. El certificado restringe el servidor on-premise a los límites de su plan y crea una cadena con evidencia de manipulación. Consulta [Cadena de Licencias y Delegación](/es/docs/license-chain) para el diseño criptográfico (integridad de la cadena, detección de bifurcaciones, pruebas de auditoría).

Esta sección cubre la configuración operativa: generación de claves, solicitud del certificado, configuración de la renovación automática y el flujo de renovación sin conexión.

### Una suscripción, una instalación on-premise

Una suscripción puede tener **como máximo un certificado de delegación activo a la vez**. Cada instalación on-premise aplica límites mensuales y por máquina contra su propio registro de emisión local, por lo que múltiples certificados activos multiplicarían la cuota efectiva sin posibilidad de reconciliación.

Si necesitas entornos separados (producción, staging, DR, multirregión), compra una suscripción por instalación. La aplicación de activo único codifica este contrato: un intento de crear un segundo certificado activo devuelve `409 DELEGATION_CERT_ALREADY_ACTIVE` con el id del certificado existente e instrucciones para renovar (preferido - preserva la cadena) o revocar-y-crear (reinicia la cadena).

### 1. Generar el par de claves Ed25519 on-premise

El servidor on-premise usa un par de claves Ed25519 separado para firmar licencias. El certificado de delegación del upstream autoriza esta clave pública específica.

```bash
# Generar un nuevo par de claves
openssl genpkey -algorithm Ed25519 -out onprem-private.pem
openssl pkey -in onprem-private.pem -pubout -out onprem-public.pem

# Convertir a base64 (el formato que el on-premise espera en las variables de entorno)
ON_PREMISE_PRIVATE_KEY=$(openssl pkey -in onprem-private.pem -outform DER | base64 -w 0)
ON_PREMISE_PUBLIC_KEY=$(openssl pkey -in onprem-private.pem -pubout -outform DER | base64 -w 0)
```

Almacena la clave privada junto con tus otros secretos (por ejemplo, un Docker secret o Kubernetes Secret). Nunca sale del servidor on-premise.

### 2. Solicitar un certificado de delegación al upstream

Puedes solicitar el certificado al portal de cuentas upstream de tres formas:

**Opción A - Autoservicio del cliente (recomendado).** Inicia sesión en el portal upstream como propietario o administrador de la organización y navega a **/account/delegation-certs**. Haz clic en **Crear Nuevo**, pega la clave pública on-premise (base64 SPKI), elige una validez (o acepta el predeterminado por plan) y descarga el archivo `.json` resultante.

**Opción B - Administrador (entre clientes).** El soporte de Rediacc o el administrador del sistema upstream puede usar `POST /admin/delegation-certs` con los mismos parámetros.

**Opción C - CLI `rdc` (planificado).** Un futuro comando del CLI encapsulará el flujo del portal.

El `.json` devuelto tiene este aspecto:

```json
{
  "payload": "eyJ2ZXJzaW9uIjoxLCJzdWJzY3JpcHRpb25JZCI6...",
  "signature": "...",
  "publicKeyId": "..."
}
```

La validez del certificado está regida por la política de validez (valores predeterminados y límites por plan, anulación por suscripción, con límite en fin de suscripción + 3 días de gracia). La respuesta también incluye `effectiveDays` y `reason` para que puedas ver por qué se eligió ese valor. Consulta [Cadena de Licencias - Política de Validez](/es/docs/license-chain) para las reglas completas.

### 3. Instalar el certificado en el servidor on-premise

Guarda el `.json` descargado en una ruta conocida y apunta el on-premise hacia él:

```bash
DELEGATION_CERT_PATH=/etc/rediacc/delegation-cert.json
```

O, para flujos de trabajo efímeros o con Docker secrets, incrusta el certificado como base64 en una variable de entorno:

```bash
DELEGATION_CERT_BASE64=$(base64 -w 0 < delegation-cert.json)
```

### 4. Configurar verificación upstream y renovación automática (opcional pero recomendado)

Si tu on-premise tiene acceso HTTPS saliente al upstream, configura la renovación automática para que el certificado se actualice antes de expirar sin intervención manual:

```bash
# Requerido para que /onprem/cert-upload verifique los certificados subidos contra la clave maestra upstream.
# Falla rápidamente al arrancar si se configura UPSTREAM_API_KEY sin esto.
UPSTREAM_PUBLIC_KEY="<clave publica SPKI Ed25519 maestra upstream, base64>"

# Requerido para el ciclo de renovación automática. Obtener via el portal:
#   Propietario/admin de org → /account/delegation-certs → "Obtener token de renovación automática"
# Esta es la ÚNICA forma de obtener un token de api con alcance delegation:renew.
UPSTREAM_URL="https://www.rediacc.com"
UPSTREAM_API_KEY="rdt_..."

# Ajuste opcional (se muestran los predeterminados).
AUTO_RENEW_INTERVAL_HOURS=24
RENEW_THRESHOLD_DAYS=14
```

El ciclo de renovación automática on-premise se ejecuta una vez al arrancar y luego en el intervalo configurado. Usa un **umbral adaptativo** (`min(env.RENEW_THRESHOLD_DAYS, ceil(certValidityDays / 3))`) para que un certificado COMMUNITY de 15 días renueve a los 5 días restantes en lugar de activar la renovación en el día 1. Un certificado BUSINESS de 90 días renueva a los 14 días restantes (el límite configurado en el entorno).

Si la renovación falla, el certificado permanece en uso hasta su vencimiento natural. El fallo retrocede durante 1 hora y se registra en `${DELEGATION_CERT_PATH}.status.json` además de exponerse via `GET /onprem/cert-status`.

### 5. Renovación sin conexión (sin HTTPS saliente)

Si tu on-premise no puede llegar al upstream, usa el flujo de transferencia manual:

1. **Descarga una solicitud de renovación desde el portal de administración on-premise.** Como root del sistema on-premise, accede a `GET /onprem/renewal-request`. Esto devuelve un manifiesto JSON que contiene el encabezado de la cadena local, la clave pública delegada y una firma Ed25519 con evidencia de manipulación de tu clave privada on-premise.
2. **Transfiere el manifiesto al upstream** via USB, correo electrónico cifrado o cualquier canal fuera de banda. El manifiesto es pequeño (unos pocos KB) y no contiene secretos.
3. **Procesa el manifiesto en el upstream.** El propietario/admin de la organización abre **/account/delegation-certs** → **Subir solicitud de renovación** → selecciona el archivo de manifiesto. El upstream verifica la firma del manifiesto contra el `delegatedPublicKey` del certificado activo (demuestra que provino de un titular de la clave privada on-premise), verifica la anti-reproducción (los manifiestos de más de 7 días son rechazados) y luego emite un certificado nuevo.
4. **Descarga el nuevo certificado** desde el portal upstream como un archivo `.json`.
5. **Transfiere el certificado de vuelta** al on-premise.
6. **Sube al on-premise** via el portal de administración local (`POST /onprem/cert-upload`). El on-premise verifica el nuevo certificado contra `UPSTREAM_PUBLIC_KEY` y valida que el `genesisSequence` del certificado todavía enlaza con una entrada de la cadena en el registro de emisión local (el avance de la cadena durante el tránsito es compatible - la cadena se extiende naturalmente).

Todo este ciclo nunca requiere salida de red desde el on-premise.

#### Modos de fallo del manifiesto

| Código | Causa | Solución |
|---|---|---|
| `NO_ACTIVE_CERT` | El upstream no tiene un certificado activo para esta suscripción | Emite un nuevo certificado a través del flujo de creación en lugar de renovar |
| `DELEGATED_KEY_MISMATCH` | El `delegatedPublicKey` del manifiesto difiere del certificado activo | El manifiesto puede ser una repetición de una instalación on-prem diferente |
| `MANIFEST_SIGNATURE_INVALID` | La firma no verifica contra la clave pública delegada | El manifiesto fue manipulado en tránsito, o lo generaste en un on-prem diferente |
| `MANIFEST_EXPIRED` | El manifiesto tiene más de 7 días | Genera una nueva solicitud de renovación desde el on-premise |

#### Modos de fallo de subida del certificado

| Código | Causa | Solución |
|---|---|---|
| `CHAIN_HEAD_BEHIND` | El `genesisSequence` del nuevo certificado está por delante del encabezado de la cadena local | El upstream está en una cadena bifurcada - investiga |
| `CHAIN_FORK_ON_UPLOAD` | El hash de la cadena en el `genesisSequence` del certificado no coincide con el registro local | La cadena local ha divergido del upstream - investiga |
| `Signature verification failed` | El certificado no está firmado por el `UPSTREAM_PUBLIC_KEY` configurado | Verifica que `UPSTREAM_PUBLIC_KEY` coincida con la clave pública maestra upstream |

### 6. Estado y monitoreo

Consulta el estado del certificado local on-premise en cualquier momento:

```bash
curl https://onprem.example.com/account/api/v1/onprem/cert-status \
  -H "Cookie: <sesión de administrador>"
```

Devuelve el `subscriptionId`, `planCode`, `validUntil`, `daysUntilExpiry` del certificado cargado, además del bloque `autoRenew` (`enabled`, `lastSuccessAt`, `lastErrorAt`, `lastError`). Integra esto en tu stack de monitoreo para alertar sobre `lastSuccessAt` desactualizado o `lastError` no nulo.

Para respaldo y auditoría, el administrador on-premise también puede descargar el certificado firmado actualmente cargado via `GET /onprem/cert-current` (requiere sesión elevada).

### Referencia de variables de entorno del certificado de delegación

| Variable | ¿Requerida? | Propósito |
|---|---|---|
| `ON_PREMISE_MODE` | Sí | Establecer en `true` para habilitar el subconjunto de rutas on-premise |
| `ON_PREMISE_PRIVATE_KEY` | Sí | Clave privada Ed25519 PKCS8 en base64 para firma delegada |
| `ON_PREMISE_PUBLIC_KEY` | Sí | Clave pública Ed25519 SPKI en base64 (debe coincidir con el `delegatedPublicKey` del certificado) |
| `DELEGATION_CERT_PATH` | Una de estas | Ruta del sistema de archivos al JSON del certificado firmado |
| `DELEGATION_CERT_BASE64` | Una de estas | JSON del certificado codificado en base64 (alternativa a la ruta de archivo) |
| `UPSTREAM_PUBLIC_KEY` | Requerido si `UPSTREAM_API_KEY` está configurado, o para que `/onprem/cert-upload` funcione | SPKI base64 de la clave pública maestra upstream. Falla rápidamente al arrancar si falta. |
| `UPSTREAM_URL` | Para renovación automática | URL base del servidor de cuentas upstream, ej. `https://www.rediacc.com` |
| `UPSTREAM_API_KEY` | Para renovación automática | Un token de api con alcance `delegation:renew`. Obtener via el portal - ver Paso 4. |
| `AUTO_RENEW_INTERVAL_HOURS` | Opcional | Predeterminado 24. Con qué frecuencia verificar si el certificado necesita renovación. |
| `RENEW_THRESHOLD_DAYS` | Opcional | Predeterminado 14. Actúa como límite superior en el umbral adaptativo de 1/3 de la validez. |

### Resumen del modelo de amenazas

El modelo de certificado de delegación defiende contra:

- **Licencias falsificadas**: el on-premise solo puede firmar dentro de los límites de su plan; renet rechaza todo lo que esté fuera de los límites del certificado.
- **Compartir certificados entre despliegues**: la divergencia de cadena se detecta en la renovación (devuelve `CHAIN_FORK_DETECTED`).
- **Evasión de cuota mediante multi-instalación**: aplicado en el upstream mediante activo único (un certificado por suscripción).
- **Reversión de la cadena**: renet almacena la secuencia más alta vista por suscripción y rechaza cualquier blob con una secuencia inferior.
- **Credenciales upstream comprometidas**: el token `delegation:renew` de bootstrap solo se puede obtener a través del endpoint dedicado del portal y está restringido a administradores. El token solo concede renovación - no puede leer ni modificar ningún otro recurso.
- **Ataques de repetición en manifiestos**: los manifiestos de más de 7 días son rechazados.

Lo que **no** defiende contra:

- **Clave privada on-premise comprometida**: una clave privada filtrada permite a un atacante firmar licencias hasta el `validUntil` del certificado. Mitigación: rota el par de claves (revoca el certificado antiguo + crea uno nuevo con la nueva clave) y trata todas las licencias firmadas con la clave antigua como sospechosas.
- **Clave maestra upstream comprometida**: esta es la raíz de confianza. Los procedimientos de rotación están fuera del alcance de este documento.
