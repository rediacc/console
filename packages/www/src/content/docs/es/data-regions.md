---
title: "Regiones de Datos"
description: "Dónde se almacenan tus datos y cómo funciona la residencia de datos regional."
category: "Concepts"
tags:
  - compliance
  - account
subcategory: platform
order: 3
language: es
sourceHash: "9efeb1e2b1f9c8db"
sourceCommit: "c477e296238c19495f4a07ef6c5a62f15e942f90"
---

Al crear una cuenta en Rediacc, eliges una región de datos. Todos tus datos permanecen en esa región. Esta elección es permanente: no puedes cambiarla después del registro. No existe una ruta de migración. Elige según dónde tus datos deben residir legalmente, no según dónde estén tus servidores hoy.

## Regiones Disponibles

| Región | Ubicación | Dominio |
|---|---|---|
| **Europa (EU)** | Unión Europea | `eu.rediacc.cloud` |
| **Estados Unidos (US)** | Este de Norteamérica | `us.rediacc.cloud` |
| **Asia Pacífico** | Asia-Pacífico | `asia.rediacc.cloud` |

La columna de ubicación nombra una región de Cloudflare, no una ciudad con centro de datos. Cloudflare no promete ninguna ciudad.

El producto funciona en estos dominios `rediacc.cloud`. Toda la documentación y el sitio de marketing están en `www.rediacc.com`, que te lleva a la región correcta desde su selector de región.

Al registrarte, el selector sugiere una región según tu ubicación y puedes confirmarla o cambiarla. Al iniciar sesión, te redirige a tu región tras una breve cuenta atrás que puedes cancelar o cambiar. Si tu empresa tiene su propio despliegue, la opción «¿Cliente Enterprise?» te lleva allí a partir de tu correo de trabajo. Solo se envía el dominio para encontrar la región; el correo solo rellena de antemano la página de inicio de sesión.

## Qué Permanece en tu Región

Estos tipos de datos se almacenan y procesan en la región que elijas, salvo que el correo transaccional de Asia-Pacífico se envía a través del endpoint de la UE (consulta más abajo la infraestructura regional para saber qué está garantizado):

- **Datos de cuenta**: correo electrónico, nombre, organización, membresías de equipo
- **Registros de facturación y suscripción**: plan, activaciones, emisiones de licencias
- **Blobs de configuración cifrados**: cifrados del lado del cliente con conocimiento cero. El servidor no puede descifrarlos.
- **Correos electrónicos transaccionales**: restablecimientos de contraseña, magic links, notificaciones. Enviados desde un endpoint de correo regional.

## Qué Es Global

Estos elementos no son específicos de una región:

- **Artefactos de release del CLI**: binarios públicos alojados en una CDN global
- **Sitio web de marketing y documentación**: `www.rediacc.com`, servido globalmente desde ubicaciones edge
- **Procesamiento de pagos con Stripe**: gestionado por la propia infraestructura de Stripe bajo su acuerdo de procesamiento de datos

## Infraestructura Regional

| Componente | EU | US | Asia |
|---|---|---|---|
| Base de datos (D1) | Indicación Europa del Este (EEUR) | Indicación Este de Norteamérica (ENAM) | Indicación Asia-Pacífico (APAC) |
| Almacenamiento de config (R2) | Jurisdicción de la UE (garantizada) | Sin jurisdicción (mejor esfuerzo) | Sin jurisdicción (mejor esfuerzo) |
| Correo (SES) | Frankfurt (eu-central-1) | Virginia (us-east-1) | Frankfurt (eu-central-1) |

Solo el almacenamiento de configuración de la UE queda sujeto a una jurisdicción garantizada: Cloudflare mantiene dentro de la UE los objetos de R2 bajo la jurisdicción de la UE. La ubicación de la base de datos D1 y el almacenamiento de US y Asia-Pacífico usan indicaciones de ubicación, que se aplican con el mejor esfuerzo. Cloudflare no garantiza que se ejecuten en la región indicada.

Cada región ejecuta infraestructura independiente. No hay consultas entre regiones ni flujos de datos entre ellas.

## Garantías de Datos en la EU

Si estás sujeto a requisitos europeos de residencia de datos, la región EU ofrece una garantía firme y una ubicación de mejor esfuerzo:

- **Base de datos D1**: ubicada con la indicación EEUR (Europa del Este), de mejor esfuerzo y sin garantía
- **Almacenamiento de configuración R2**: sujeto a la jurisdicción de la UE, que Cloudflare garantiza (una restricción firme, no solo una indicación de ubicación)
- **Correo electrónico**: enviado desde Frankfurt (eu-central-1)

Para un mapeo detallado del RGPD, consulta [Cumplimiento del RGPD](/es/docs/legal-gdpr).

## Cifrado de Conocimiento Cero

Los blobs de configuración almacenados en R2 se cifran del lado del cliente antes de subirse usando intercambio de claves X25519 y AES-256-GCM. El servidor solo almacena texto cifrado. Ni Rediacc ni ningún proveedor de infraestructura puede leer tus datos de configuración.

Las claves se derivan de una passkey con extensión PRF. El servidor almacena un secreto que participa en la derivación de claves, pero ni la passkey sola ni el secreto del servidor solo pueden descifrar los datos.

Para detalles sobre la arquitectura de cifrado, consulta [Almacenamiento de Config](/es/docs/config-storage).

## Cómo Elegir

- **Elige la región más cercana a ti** para la menor latencia.
- **Elige la región que requiere tu organización** por cumplimiento normativo. Si tu empresa exige residencia de datos en la EU, elige EU.
- **La elección es permanente.** No puedes mover tu cuenta a una región diferente después del registro.

## Para Responsables de Cumplimiento

Propiedades técnicas de la arquitectura regional:

- **Bases de datos separadas por región**: cada región tiene su propia base de datos Cloudflare D1. Sin consultas entre regiones.
- **Almacenamiento separado por región**: cada región tiene su propio bucket R2. Solo el bucket de la EU queda sujeto a una jurisdicción; US y Asia-Pacífico se ubican con el mejor esfuerzo.
- **Entrega de correo mediante AWS SES**: los correos electrónicos transaccionales se envían mediante AWS SES. EU y US utilizan endpoints regionales dedicados; Asia Pacífico se enruta a través del endpoint EU (eu-central-1).
- **Un usuario, una región**: una cuenta de usuario existe en exactamente una región. No puede abarcar múltiples regiones.
- **Aislamiento de webhooks**: los eventos de webhook de Stripe son recibidos por todos los workers regionales, pero solo procesados por la región propietaria del registro del cliente.
- **Cifrado de config de conocimiento cero**: el servidor no puede leer los datos de configuración. Las claves de cifrado nunca abandonan el dispositivo del cliente.

Para una visión más amplia del cumplimiento de soberanía de datos, consulta [Soberanía de Datos](/es/docs/legal-data-sovereignty).
