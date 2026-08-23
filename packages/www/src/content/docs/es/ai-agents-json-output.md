---
title: Referencia de salida JSON
description: >-
  Referencia completa del formato de salida JSON del CLI rdc, esquema de la
  información envolvente, gestión de errores y comandos de descubrimiento para
  agentes.
category: Reference
tags:
  - ai-agents
  - cli
subcategory: ai-agents
order: 51
language: es
sourceHash: "36ba86893c3817ac"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
---

Todos los comandos `rdc` producen JSON estructurado. Páselo a un script o aliméntelo directamente a un agente.

## Activar la salida JSON

### Opción explícita

```bash
rdc machine status prod-1 --output json
rdc machine status prod-1 -o json
```

### Detección automática

Cuando `rdc` se ejecuta en un entorno non-TTY (tubería, subshell o invocado por un agente de IA), la salida cambia automáticamente a JSON. No se necesita ninguna opción.

```bash
# Produces JSON automatically
result=$(rdc machine status prod-1)
```

## Sobre JSON

Cada respuesta JSON utiliza un sobre consistente:

```json
{
  "success": true,
  "command": "machine query",
  "data": {
    "name": "prod-1",
    "status": "running",
    "repositories": []
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 142
  }
}
```

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `success` | `boolean` | Si el comando se completó correctamente |
| `command` | `string` | La ruta completa del comando (p. ej., `"machine query"`, `"repo up"`) |
| `data` | `object \| array \| null` | Datos específicos del comando en caso de éxito, `null` en caso de error |
| `errors` | `array \| null` | Objetos de error en caso de fallo, `null` en caso de éxito |
| `warnings` | `string[]` | Advertencias no fatales recopiladas durante la ejecución |
| `metrics` | `object` | Metadatos de ejecución |

## Respuestas de error

Los comandos fallidos devuelven errores estructurados con sugerencias de recuperación:

```json
{
  "success": false,
  "command": "machine query",
  "data": null,
  "errors": [
    {
      "code": "NOT_FOUND",
      "message": "Machine \"prod-2\" not found",
      "retryable": false,
      "guidance": "Verify the resource name with \"rdc machine status\" or \"rdc repo list\""
    }
  ],
  "warnings": [],
  "metrics": {
    "duration_ms": 12
  }
}
```

### Campos de error

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `code` | `string` | Código de error legible por máquina (consulte las constantes `ERROR_CODES` para la lista canónica) |
| `message` | `string` | Descripción legible por humanos |
| `retryable` | `boolean` | Si reintentar el mismo comando puede tener éxito |
| `guidance` | `string` | Sugerencia en texto libre (heredado. Prefiera `next` para datos de acción estructurados) |
| `next` | `object?` | Sugerencia de próxima acción estructurada (cuando está presente). Véase más abajo |

### Sugerencias de acción estructuradas con `next`

Para códigos de error de alto valor como `PRECONDITION_MISMATCH`, el error incluye un campo `next` con los comandos exactos que ofrecer al usuario. No todos los códigos de error incluyen este campo, solo aquellos con una ruta de recuperación definida. **Los agentes deben transmitir `next.options[].run` literalmente al usuario en lugar de sintetizar su propio comando.** Esto elimina el fallo donde el agente inventa un comando que no existe. Ocurre con más frecuencia de lo que se podría pensar.

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "--current digest mismatch (expected 3264f8ee…, got 611dfd8a…)",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        {
          "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get mail --key STRIPE_KEY"
        },
        {
          "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set mail --key STRIPE_KEY --value <new> --mode file --rotate-secret"
        }
      ]
    }
  }]
}
```

Esquema:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `next.summary` | `string` | Descripción en una línea de lo que el usuario debe decidir |
| `next.options[]` | `array` | Acciones concretas; cada una es una alternativa que el usuario puede elegir |
| `next.options[].description` | `string` | Explicación legible por humanos de esta opción |
| `next.options[].run` | `string` | Comando CLI exacto. Transmítalo literalmente al usuario |

### Errores reintentables

Estos tipos de error se marcan como `retryable: true`:

- **NETWORK_ERROR**, Fallo de conexión SSH o de red
- **RATE_LIMITED**, Demasiadas solicitudes, espere y reintente
- **API_ERROR**, Fallo transitorio del backend

Los errores no reintentables (autenticación, no encontrado, argumentos inválidos) requieren acción correctiva antes de reintentar.

## Filtrar la salida

Use `--fields` para limitar la salida a claves específicas y reducir el uso de tokens:

```bash
rdc machine status prod-1 --containers -o json --fields name,status,repository
```

## Salida de simulación

Los comandos destructivos admiten `--dry-run` para previsualizar lo que ocurriría:

```bash
rdc repo delete mail@prod-1 --dry-run -o json
```

```json
{
  "success": true,
  "command": "repo delete",
  "data": {
    "dryRun": true,
    "repository": "mail",
    "machine": "prod-1",
    "guid": "a1b2c3d4-..."
  },
  "errors": null,
  "warnings": [],
  "metrics": {
    "duration_ms": 8
  }
}
```

Comandos con soporte de `--dry-run`: `repo up`, `repo down`, `repo delete`, `snapshot delete`, `sync upload`, `sync download`.

## Ejemplos de análisis

### Shell (jq)

```bash
status=$(rdc machine status prod-1 -o json | jq -r '.data.status')
```

### Python

```python
import subprocess, json

result = subprocess.run(
    ["rdc", "machine", "query", "--name", "prod-1", "-o", "json"],
    capture_output=True, text=True
)
envelope = json.loads(result.stdout)

if envelope["success"]:
    print(envelope["data"]["status"])
else:
    error = envelope["errors"][0]
    if error["retryable"]:
        # retry logic
        pass
    else:
        print(f"Error: {error['message']}")
        print(f"Fix: {error['guidance']}")
```

### Node.js

```javascript
import { execFileSync } from 'child_process';

const raw = execFileSync('rdc', ['machine', 'query', '--name', 'prod-1', '-o', 'json'], { encoding: 'utf-8' });
const { success, data, errors } = JSON.parse(raw);

if (!success) {
  const { message, retryable, guidance } = errors[0];
  throw new Error(`${message} (retryable: ${retryable}, fix: ${guidance})`);
}
```
