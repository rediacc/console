---
title: "Regiones de Datos"
description: "Dónde se almacenan tus datos y cómo funciona la residencia de datos regional."
category: "Concepts"
order: 3
language: es
sourceHash: "107d8ef496686b0e"
sourceCommit: "a97009927c347f7090e4f4f60f3948997654ae4b"
---

Al crear una cuenta en Rediacc, eliges una región de datos. Todos tus datos permanecen en esa región. Esta elección es permanente y no puede cambiarse después del registro.

## Regiones Disponibles

| Región | Ubicación | Dominio |
|---|---|---|
| **Europa (EU)** | Frankfurt, Alemania | `eu.rediacc.com` |
| **Estados Unidos (US)** | Virginia, EE.UU. | `us.rediacc.com` |
| **Asia Pacífico** | Tokio, Japón | `asia.rediacc.com` |

Tu región se detecta automáticamente por tu zona horaria durante el registro. Puedes anular la sugerencia en el selector de región.

## Qué Permanece en tu Región

Estos tipos de datos se almacenan y procesan exclusivamente en tu región elegida:

- **Datos de cuenta**: correo electrónico, nombre, organización, membresías de equipo
- **Registros de facturación y suscripción**: plan, activaciones, emisiones de licencias
- **Blobs de configuración cifrados**: cifrados del lado del cliente con conocimiento cero. El servidor no puede descifrarlos.
- **Correos electrónicos transaccionales**: restablecimientos de contraseña, magic links, notificaciones. Enviados desde un endpoint de correo regional.

## Qué Es Global

Estos elementos no son específicos de una región:

- **Artefactos de release del CLI**: binarios públicos alojados en una CDN global
- **Sitio web de marketing**: servido globalmente desde ubicaciones edge
- **Procesamiento de pagos con Stripe**: gestionado por la propia infraestructura de Stripe bajo su acuerdo de procesamiento de datos

## Infraestructura Regional

| Componente | EU | US | Asia |
|---|---|---|---|
| Base de datos (D1) | Europa del Este (EEUR) | América del Norte Oriental (ENAM) | Asia Pacífico (APAC) |
| Almacenamiento de config (R2) | Jurisdicción EU | US | Asia Pacífico |
| Correo (SES) | Frankfurt (eu-central-1) | Virginia (us-east-1) | Tokio (ap-northeast-1) |

Cada región ejecuta infraestructura independiente. No hay consultas entre regiones ni flujos de datos entre ellas.

## Garantías de Datos en la EU

La región EU proporciona garantías adicionales para organizaciones con requisitos de residencia de datos europeos:

- **Base de datos D1**: funciona en Europa del Este (pista de ubicación EEUR)
- **Almacenamiento de config R2**: usa aplicación jurisdiccional de la EU (garantía contractual, no solo una pista de ubicación)
- **Correo electrónico**: enviado desde Frankfurt (eu-central-1)
- **Decisión de adecuación mutua EU-Japón (2019)**: permite flujos de datos conformes para la infraestructura de la región Asia

Para un mapeo detallado del RGPD, consulta [Cumplimiento del RGPD](/es/docs/legal-gdpr).

## Cifrado de Conocimiento Cero

Los blobs de configuración almacenados en R2 se cifran del lado del cliente antes de subirse usando intercambio de claves X25519 y AES-256-GCM. El servidor solo almacena texto cifrado. Ni Rediacc ni ningún proveedor de infraestructura puede leer tus datos de configuración.

Las claves se derivan de una passkey con extensión PRF. El servidor almacena un secreto del lado del servidor que participa en la derivación de claves, pero ni la passkey sola ni el secreto del servidor solo pueden descifrar los datos.

Para detalles sobre la arquitectura de cifrado, consulta [Almacenamiento de Config](/es/docs/config-storage).

## Cómo Elegir

- **Elige la región más cercana a ti** para la menor latencia.
- **Elige la región que requiere tu organización** por cumplimiento normativo. Si tu empresa exige residencia de datos en la EU, elige EU.
- **La elección es permanente.** No puedes mover tu cuenta a una región diferente después del registro.

## Para Responsables de Cumplimiento

Propiedades técnicas de la arquitectura regional:

- **Bases de datos separadas por región**: cada región tiene su propia base de datos Cloudflare D1. Sin consultas entre regiones.
- **Almacenamiento separado por región**: cada región tiene su propio bucket R2. La EU usa aplicación jurisdiccional.
- **Endpoints de correo separados por región**: los correos electrónicos transaccionales se envían desde endpoints AWS SES regionales.
- **Un usuario, una región**: una cuenta de usuario existe en exactamente una región. No puede abarcar múltiples regiones.
- **Aislamiento de webhooks**: los eventos de webhook de Stripe son recibidos por todos los workers regionales, pero solo procesados por la región propietaria del registro del cliente.
- **Cifrado de config de conocimiento cero**: el servidor no puede leer los datos de configuración. Las claves de cifrado nunca abandonan el dispositivo del cliente.

Para una visión más amplia del cumplimiento de soberanía de datos, consulta [Soberanía de Datos](/es/docs/legal-data-sovereignty).
