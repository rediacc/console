---
title: "Suscripción y licencias"
description: "Gestionar suscripciones y licencias de máquina para implementaciones locales."
category: "Guides"
order: 7
language: es
sourceHash: "84215f54750ac4a4"
---

# Suscripción y licencias

Las máquinas que funcionan en implementaciones locales necesitan una licencia de suscripción para aplicar los límites de recursos según el plan. El CLI entrega automáticamente blobs de licencia firmados a las máquinas remotas vía SSH — sin necesidad de activación manual ni conexión a la nube desde el lado del servidor.

## Descripción general

1. Inicia sesión con `rdc subscription login` (abre el navegador para autenticación)
2. Usa cualquier comando de máquina — las licencias se gestionan automáticamente

Cuando ejecutas un comando dirigido a una máquina (`rdc machine info`, `rdc repo up`, etc.), el CLI verifica automáticamente si la máquina tiene una licencia válida. Si no la tiene, obtiene una del servidor de cuentas y la entrega vía SSH.

## Inicio de sesión

```bash
rdc subscription login
```

Abre un navegador para autenticación mediante el flujo de código de dispositivo. Tras la aprobación, el CLI almacena un token de API localmente en `~/.config/rediacc/api-token.json`.

| Opción | Requerido | Predeterminado | Descripción |
|--------|----------|---------|-------------|
| `-t, --token <token>` | No | - | Token de API (omite el flujo del navegador) |
| `--server <url>` | No | `https://account.rediacc.com` | URL del servidor de cuentas |

## Verificar el estado

```bash
# Estado a nivel de cuenta (plan, máquinas)
rdc subscription status

# Incluir detalles de licencia de una máquina específica
rdc subscription status -m hostinger
```

Muestra los detalles de la suscripción desde el servidor de cuentas. Con `-m`, también se conecta a la máquina vía SSH y muestra su información de licencia actual.

## Actualización forzada de licencia

```bash
rdc subscription refresh -m <machine>
```

Reemite y entrega forzosamente una licencia nueva a la máquina especificada. Esto normalmente no es necesario — las licencias se actualizan automáticamente cada 50 minutos durante el uso normal del CLI.

## Cómo funciona

1. **El inicio de sesión** almacena un token de API en tu estación de trabajo
2. **Cualquier comando de máquina** activa una verificación automática de licencia vía SSH
3. Si la licencia remota falta o tiene más de 50 minutos de antigüedad, el CLI:
   - Lee el ID de hardware de la máquina remota vía SSH
   - Llama a la API de cuentas para emitir una nueva licencia
   - Entrega tanto la licencia de máquina como el blob de suscripción al equipo remoto vía SSH
4. Una caché en memoria de 50 minutos previene viajes SSH redundantes dentro de la misma sesión

Cada activación de máquina consume una plaza en tu suscripción. Para liberar una plaza, desactiva una máquina desde el portal de cuentas.

## Período de gracia y degradación

Si una licencia expira y no puede actualizarse dentro del período de gracia de 3 días, los límites de recursos de la máquina se degradan a los valores predeterminados del plan Community. Una vez que se actualiza la licencia (restaurando la conectividad y ejecutando cualquier comando `rdc`), los límites del plan original se restauran inmediatamente.

## Límites de plan

### Límites de licencias flotantes

| Plan | Licencias flotantes |
|------|-------------|
| Community | 2 |
| Professional | 5 |
| Business | 20 |
| Enterprise | 50 |

### Límites de recursos

| Recurso | Community | Professional | Business | Enterprise |
|----------|-----------|--------------|----------|------------|
| Bridges | 0 | 1 | 2 | 10 |
| Max reserved jobs | 1 | 2 | 3 | 5 |
| Job timeout (hours) | 2 | 24 | 72 | 96 |
| Repository size (GB) | 10 | 100 | 500 | 2,048 |
| Jobs per month | 500 | 5,000 | 20,000 | 100,000 |
| Pending per user | 5 | 10 | 20 | 50 |
| Tasks per machine | 1 | 2 | 3 | 5 |

### Disponibilidad de funcionalidades

| Funcionalidad | Community | Professional | Business | Enterprise |
|---------|-----------|--------------|----------|------------|
| Permission groups | - | Yes | Yes | Yes |
| Queue priority | - | - | Yes | Yes |
| Advanced analytics | - | - | Yes | Yes |
| Priority support | - | Yes | Yes | Yes |
| Audit log | - | Yes | Yes | Yes |
| Advanced queue | - | - | Yes | Yes |
| Custom branding | - | Yes | Yes | Yes |
| Dedicated account | - | - | - | Yes |
