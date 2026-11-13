---
title: "Instalación en Infraestructura Propia"
description: "Ejecutar el servidor de cuentas y la distribución del CLI en tu propia infraestructura."
category: "Guides"
tags:
  - account
  - operations
subcategory: setup
order: 5
language: es
sourceHash: "7216d032580dd4e1"
sourceCommit: "48fd8400c9f2754ab1653f0247fb0d77a1835c5b"
---

Rediacc puede ejecutarse completamente en tu propia infraestructura. La imagen Docker independiente incluye el servidor de cuentas, el portal web, el sitio de marketing y el endpoint de distribución del CLI. No se requieren dependencias externas de los servicios alojados de Rediacc.

## Instalar con rdc

`rdc server install` instala el servidor de cuentas como repositorio en una máquina a la que la CLI llega por SSH. Un solo comando cubre la comprobación de la máquina, la configuración de renet, el DNS, el TLS, la generación de claves, la licencia, el arranque y la cuenta de propietario. Cada valor tiene su opción. En un terminal se pregunta por el valor que falte; con `--yes` no se pregunta nada y se rechaza el valor ausente. Cada paso queda registrado, así que una nueva ejecución omite lo que ya está hecho.

Los pasos, en orden: `preflight` (sudo sin contraseña, arquitectura, puertos 80 y 443, espacio en disco, desfase del reloj), `setup` (`rdc machine setup`, solo si falta renet), `dns`, `tls`, `repo`, `keys`, `licence`, `image`, `up` y `owner`.

### Primero, máquinas existentes

La instalación apunta a una máquina que ya existe: un servidor en un centro de datos o un dispositivo de la red local. Una máquina configurada se indica como argumento. Una máquina aún sin registrar se añade con su dirección:

```bash
rdc server install --ip 203.0.113.10 --user admin --domain accounts.example.com
rdc server install server-1 --domain accounts.example.com --owner owner@example.com --yes
```

`--port` y `--name` fijan el puerto SSH y el nombre con el que se registra la máquina. Una VM en la nube se crea antes con `rdc machine provision`; la instalación nunca crea una.

### DNS

La instalación imprime los registros A y AAAA del dominio del servidor y del dominio de su almacén de copias (`--store-domain`, por defecto `<nombre>-store.<resto del dominio>`) y espera a que ambos resuelvan a la máquina. Nunca se escribe un registro en una zona. `--no-dns-wait` imprime los registros y continúa, algo útil para un nombre de red local servido por un resolvedor local.

### TLS

`--tls` elige uno de tres métodos:

| Método | Requisitos | Notas |
|---|---|---|
| `letsencrypt` | Puertos 80 y 443 accesibles desde internet | Desafío HTTP-01. `--cert-email` recibe los avisos de caducidad; por defecto, el propietario. |
| `cloudflare` | `--cf-token` | Desafío DNS-01 mediante un token de API de Cloudflare. |
| `byo` | `--tls-cert` y `--tls-key` | Un certificado PEM existente que cubra ambos dominios. `--tls-ca` indica la CA en la que confía la comprobación de estado. |

```bash
rdc server install lab --domain lab.example.internal --tls byo \
  --tls-cert host.crt --tls-key host.key --tls-ca ca.crt \
  --licence free --no-dns-wait --yes
```

### Imagen

El paso de imagen descarga `ghcr.io/rediacc/server:latest` en la máquina por defecto. `--image` elige otra referencia. `--image-file` envía un tar generado con `docker save`, y `--local-image` guarda la `--image` del Docker local y la envía. Ambas evitan cualquier acceso a un registro desde la máquina.

### Licencia y plan gratuito

`--licence auto` (el valor por defecto) toma un certificado de delegación de la cuenta con sesión iniciada, o arranca en el plan gratuito si no hay ninguno. `--licence free` arranca siempre en el plan gratuito. Una cuenta que inició sesión antes de que existiera el comando de instalación necesita volver a ejecutar `rdc subscription login` para tener el scope adecuado.

Para una máquina sin ruta al servidor de cuentas, `--cert <file>` toma un certificado de delegación obtenido en otro sitio. El certificado debe nombrar la clave generada en la máquina, por lo que el orden habitual es primero una instalación en el plan gratuito y después el certificado:

```bash
rdc server install server-1 --domain accounts.example.com --licence free --yes
rdc server licence accounts.example.com --cert delegation-cert.json
```

`rdc server licence` pasa un servidor del plan gratuito a un certificado de la cuenta con sesión iniciada o de `--cert`. El paso 3 de la sección de licencias, más abajo, describe lo que comprueba el servidor.

### Paquete de recuperación

Todas las claves se generan en la máquina y se escriben solo en el `secrets.env` del repositorio. En un terminal, la instalación termina imprimiendo una única vez un paquete de recuperación: el par de claves delegado, la clave del servidor de configuración de la cuenta y las credenciales del almacén de objetos. El paquete nunca se registra ni forma parte de `--output json`. Sin terminal no se imprime, y la línea final menciona `rdc server backup`.

```bash
rdc server backup accounts.example.com --out elite-recovery.env
```

`--out` escribe el archivo con modo 0600; sin él, el paquete va a stdout. `--bws-project <id>` en la instalación copia además las claves a un proyecto de Bitwarden Secrets Manager, y `--rotate` sustituye un valor almacenado que difiera. Sin `--bws-project`, ninguna clave sale de la máquina.

### Estado

```bash
rdc server status accounts.example.com
```

El estado muestra la salud, el plan, el certificado y la imagen del servidor. `--machine` y `--repo` indican el destino cuando el dispositivo no tiene registro de instalación para el dominio.

### Actualizaciones

| Componente | Comando |
|---|---|
| CLI | `rdc update` |
| renet en la máquina | `rdc machine setup <machine>` |
| Imagen y plantilla del servidor | `rdc server upgrade <domain>` |

`rdc server upgrade` hace un fork del repositorio como punto de retorno, coloca la nueva imagen, vuelve a aplicar la plantilla cuando la integrada es más reciente y reinicia. Acepta `--image`, `--image-file` y `--local-image` igual que la instalación, de modo que una máquina aislada se actualiza desde un tar de imagen guardado.

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

Instala el CLI directamente desde tu servidor on-premise. El script de instalación detecta automáticamente el canal de actualizaciones y configura el CLI para verificar actualizaciones en tu servidor.

```bash
curl -fsSL https://account.example.com/install.sh | \
  REDIACC_SERVER_URL=https://account.example.com bash
```

Este único comando:
1. Descarga el binario del CLI desde el endpoint `/releases/` de tu servidor
2. Consulta `/account/api/v1/.well-known/server-info` para descubrir el canal de actualizaciones
3. Escribe la configuración predeterminada (`rediacc.json`) con la URL de tu servidor, el canal de actualizaciones y las claves de cifrado bajo sus campos `account.*`
4. Configura `rdc update` para verificar actualizaciones en tu servidor en el futuro

No se necesita la variable `REDIACC_CHANNEL`. El script de instalación lee el canal de la configuración de tu servidor automáticamente.

## Configuración del CLI con Configs con Nombre

Si te conectas a múltiples servidores (on-premise, producción, edge), las configs con nombre mantienen cada entorno aislado:

```bash
# Crear una config para tu servidor on-premise
rdc config init myserver --server https://account.example.com

# Iniciar sesión usando esa config
rdc --config myserver subscription login

# Todos los comandos con --config usan el servidor on-premise
rdc --config myserver machine status prod-1
```

Cada config con nombre almacena su propia URL del servidor de cuentas (bajo `account.*`) y su propio token de API de cuenta, guardado junto a la config en `api-token-<name>.json`. Cambiar de config cambia todo el contexto del servidor.

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
| `REDIACC_UPDATE_CHANNEL` | Tiempo de ejecución del CLI | Sobreescribe el canal de actualizaciones para `rdc update`. |

## Configuración del Servidor

La imagen Docker on-premise usa la misma variable `ENVIRONMENT` que el servicio alojado. Configúrala en tu entorno Docker o en la configuración de orquestación:

- `ENVIRONMENT=production` (predeterminado): límites de recursos estándar; los CLIs que se conectan a este servidor utilizan el canal de actualizaciones **stable** por defecto. El nombre de valor `production` es un identificador de despliegue heredado. Ambos modos `production` y `edge` son de calidad de producción.
- `ENVIRONMENT=edge`: 2X de límites Community; los CLIs usan por defecto el canal de actualizaciones **edge**

Consulta [Canales de Release](/es/docs/release-channels) para más detalles sobre lo que proporciona cada entorno.

## Qué le Comunica el Servidor al CLI

Cuando el CLI se conecta a tu servidor, consulta `/.well-known/server-info` para descubrir:

- **Clave pública de cifrado E2E**: para almacenamiento de configuración de conocimiento cero
- **Versión mínima del CLI**: bloquea CLIs desactualizados de conectarse
- **Canal de actualizaciones**: indica al CLI qué canal de release usar para las actualizaciones
- **Entorno**: qué perfil de despliegue ejecuta el servidor (límites estándar vs. edge-con-2X-límites)

Esta autoconfiguración significa que solo necesitas la URL del servidor. Todo lo demás se descubre automáticamente.

## Licencias para Despliegues Sin Acceso a Internet

Los servidores on-premise sin acceso a internet y los auto-alojados emiten licencias localmente usando un **certificado de delegación** firmado por la clave maestra upstream. El certificado restringe el servidor on-premise a los límites de su plan y crea una cadena con evidencia de manipulación. Consulta [Cadena de Licencias y Delegación](/es/docs/license-chain) para el diseño criptográfico (integridad de la cadena, detección de bifurcaciones, pruebas de auditoría).

Esta sección cubre la configuración operativa: generación de claves, solicitud del certificado, configuración de la renovación automática y el flujo de renovación sin conexión.

### Una suscripción, una instalación on-premise

Una suscripción puede tener **como máximo un certificado de delegación activo a la vez**. Cada instalación on-premise aplica límites mensuales y por máquina contra su propio registro de emisión local, por lo que múltiples certificados activos multiplicarían la cuota efectiva sin posibilidad de reconciliación.

Si necesitas entornos separados (producción, staging, DR, multirregión), adquiere una suscripción por instalación. La aplicación de activo único codifica este contrato: un intento de crear un segundo certificado activo devuelve `409 DELEGATION_CERT_ALREADY_ACTIVE` con el id del certificado existente e instrucciones para renovar (preferido, preserva la cadena) o revocar-y-crear (reinicia la cadena).

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

**Opción A: Autoservicio del cliente (recomendado).** Inicia sesión en el portal upstream como propietario o administrador de la organización y ve a **/account/delegation-certs**. Haz clic en **Crear Nuevo**, pega la clave pública on-premise (base64 SPKI), elige una validez (o acepta el predeterminado por plan) y descarga el archivo `.json` resultante.

**Opción B: Administrador (entre clientes).** El soporte de Rediacc o el administrador del sistema upstream puede llamar a `POST /admin/delegation-certs` con los mismos parámetros.

**Opción C: CLI `rdc` (planificado).** Un futuro comando del CLI encapsulará el flujo del portal.

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

El servidor lee su certificado de delegación de un único archivo en su volumen de datos, `/data/delegation-cert.json` (`DELEGATION_CERT_PATH`). Nada más lleva un certificado: no existe una variable de entorno para ello. `rdc server install` deja ahí el certificado descargado, y `rdc server licence` lo reemplaza después:

```bash
rdc server install <domain> --cert delegation-cert.json
rdc server licence <domain> --cert delegation-cert.json
rdc server status <domain>
```

Ambos comandos entregan el certificado al servidor en marcha a través de su buzón de certificados (`data/web/cert-inbox/new.json`). El servidor lo verifica y responde con `applied.json` o `rejected.json`, y el comando confirma el id del nuevo certificado con `rdc server status` (los mismos datos de `cert-status` del paso 6). `rdc server upgrade` usa el mismo buzón. Un paso de la actualización mueve un `DELEGATION_CERT_BASE64` sobrante de `secrets.env` al buzón, de modo que una caja instalada antes de que existiera el buzón conserva su certificado.

El servidor carga el certificado al arrancar y lo compara con la clave con la que firma licencias: la huella de la clave de firma debe coincidir con la huella del `delegatedPublicKey` del certificado, porque las licencias firmadas con una clave que el certificado no autoriza no se podrían validar en ninguna máquina. Mantén sincronizados el par de claves de firma y el `delegatedPublicKey` del certificado.

Un certificado que el servidor rechaza al arrancar (firma incorrecta, clave equivocada, falta de `UPSTREAM_PUBLIC_KEY` o archivo malformado) no lo detiene. El servidor arranca en el nivel gratuito y mueve el archivo defectuoso a `delegation-cert.rejected.json`, junto al original. La firma de licencias de repos responde `503 DELEGATION_CERT_REFUSED` hasta que haya un certificado válido, y `rdc server status` muestra `cert REFUSED (reason)`. Ejecuta `rdc server licence` con un certificado válido para repararlo. Un certificado caducado se sigue cargando: se degrada de forma suave en lugar de rechazarse.

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

`POST /onprem/cert-upload` responde `{uploaded: true, bootstrap, certId}` si todo va bien. Un certificado rechazado devuelve `{error, code}`: `error` lleva el detalle y `code` es uno de los motivos de la tabla. Cada certificado aplicado o rechazado se registra en el log y se envía por correo al propietario de la caja.

`rdc server licence` deposita el certificado por SSH en la bandeja de entrada de la caja (`data/web/cert-inbox`) y lee de vuelta `applied.json` o `rejected.json`. Después confirma el nuevo id del certificado con `cert-status`. Un rechazo trae los mismos motivos, más `not-a-regular-file` y `too-large`, que genera la propia bandeja.

| Código | HTTP | Causa |
|---|---|---|
| `malformed` | 400 | La subida no es un certificado válido |
| `bad-signature` | 400 | El certificado no está firmado con la `UPSTREAM_PUBLIC_KEY` configurada |
| `wrong-key` | 400 | El certificado se emitió para una clave distinta de la de esta instalación on-premise |
| `expired` | 400 | El certificado ya superó su `validUntil` |
| `not-newer` | 409 | El certificado no es más reciente que el que está en vigor |
| `other-subscription` | 409 | El certificado pertenece a otra suscripción |
| `chain-ahead` | 409 | El `genesisSequence` del certificado está por delante del encabezado de la cadena local |
| `chain-fork` | 409 | El hash de la cadena en el `genesisSequence` del certificado no coincide con el registro local |
| `no-upstream-key` | 500 | `UPSTREAM_PUBLIC_KEY` no está configurada |
| `write-failed` | 500 | No se pudo escribir el certificado en disco |
| `adoption-failed` | 500 | El servidor no pudo cargar el certificado escrito |

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
| `DELEGATION_CERT_PATH` | Opcional | Ruta del sistema de archivos al JSON del certificado firmado. Por defecto `/data/delegation-cert.json` en el volumen de datos. Reemplaza el certificado con `rdc server licence`, no a mano. |
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
