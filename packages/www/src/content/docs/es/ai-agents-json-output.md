---
title: Referencia de salida JSON
description: Referencia completa del formato de salida JSON del CLI rdc, esquema de la información envolvente, gestión de errores y comandos de descubrimiento para agentes.
category: Reference
order: 51
language: es
sourceHash: "49cfcc5e2e4621a9"
---

Todos los comandos `rdc` admiten salida JSON estructurada para consumo programático por agentes de IA y scripts.

## Activar la salida JSON

### Opción explícita

```bash
rdc machine query prod-1 --output json
rdc machine query prod-1 -o json
```

### Detección automática

Cuando `rdc` se ejecuta en un entorno non-TTY (tubería, subshell o invocado por un agente de IA), la salida cambia automáticamente a JSON. No se necesita ninguna opción.

```bash
# These all produce JSON automatically
result=$(rdc machine query prod-1)
echo '{}' | rdc agent exec "machine query"
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
      "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
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
| `code` | `string` | Código de error legible por máquina |
| `message` | `string` | Descripción legible por humanos |
| `retryable` | `boolean` | Si reintentar el mismo comando puede tener éxito |
| `guidance` | `string` | Acción sugerida para resolver el error |

### Errores reintentables

Estos tipos de error se marcan como `retryable: true`:

- **NETWORK_ERROR** — Fallo de conexión SSH o de red
- **RATE_LIMITED** — Demasiadas solicitudes, espere y reintente
- **API_ERROR** — Fallo transitorio del backend

Los errores no reintentables (autenticación, no encontrado, argumentos inválidos) requieren acción correctiva antes de reintentar.

## Filtrar la salida

Use `--fields` para limitar la salida a claves específicas. Esto reduce el uso de tokens cuando solo se necesitan datos específicos:

```bash
rdc machine containers prod-1 -o json --fields name,status,repository
```

## Salida de simulación

Los comandos destructivos admiten `--dry-run` para previsualizar lo que ocurriría:

```bash
rdc repo delete mail -m prod-1 --dry-run -o json
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

## Comandos de descubrimiento para agentes

El subcomando `rdc agent` proporciona introspección estructurada para que los agentes de IA descubran las operaciones disponibles en tiempo de ejecución.

### Listar todos los comandos

```bash
rdc agent capabilities
```

Devuelve el árbol completo de comandos con argumentos, opciones y descripciones:

```json
{
  "success": true,
  "command": "agent capabilities",
  "data": {
    "version": "1.0.0",
    "commands": [
      {
        "name": "machine query",
        "description": "Show machine status",
        "arguments": [
          { "name": "machine", "description": "Machine name", "required": true }
        ],
        "options": [
          { "flags": "-o, --output <format>", "description": "Output format" }
        ]
      }
    ]
  }
}
```

### Obtener esquema de un comando

```bash
rdc agent schema "machine query"
```

Devuelve el esquema detallado de un solo comando, incluyendo todos los argumentos y opciones con sus tipos y valores predeterminados.

### Ejecutar mediante JSON

```bash
echo '{"machine": "prod-1"}' | rdc agent exec "machine query"
```

Acepta JSON en stdin, mapea las claves a los argumentos y opciones del comando, y ejecuta con salida JSON forzada. Útil para la comunicación estructurada agente-CLI sin construir cadenas de comandos de shell.

## Ejemplos de análisis

### Shell (jq)

```bash
status=$(rdc machine query prod-1 -o json | jq -r '.data.status')
```

### Python

```python
import subprocess, json

result = subprocess.run(
    ["rdc", "machine", "query", "prod-1", "-o", "json"],
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

const raw = execFileSync('rdc', ['machine', 'query', 'prod-1', '-o', 'json'], { encoding: 'utf-8' });
const { success, data, errors } = JSON.parse(raw);

if (!success) {
  const { message, retryable, guidance } = errors[0];
  throw new Error(`${message} (retryable: ${retryable}, fix: ${guidance})`);
}
```
