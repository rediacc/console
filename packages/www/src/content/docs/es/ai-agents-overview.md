---
title: Integración de agentes de IA - Descripción general
description: Cómo los asistentes de programación con IA como Claude Code, Cursor y Cline se integran con la infraestructura Rediacc para el despliegue y la gestión autónomos.
category: Guides
order: 30
language: es
sourceHash: "2d8ab92216666d0e"
---

Los asistentes de programación con IA pueden gestionar la infraestructura Rediacc de forma autónoma a través del CLI `rdc`. Esta guía cubre los enfoques de integración y cómo empezar.

## Por qué autoalojamiento + agentes de IA

La arquitectura de Rediacc es naturalmente compatible con agentes:

- **CLI primero**: Cada operación es un comando `rdc` — no se requiere GUI
- **Basado en SSH**: El protocolo que los agentes mejor conocen de los datos de entrenamiento
- **Salida JSON**: Todos los comandos admiten `--output json` con un sobre consistente
- **Aislamiento Docker**: Cada repositorio tiene su propio daemon y espacio de nombres de red
- **Automatizable**: `--yes` omite confirmaciones, `--dry-run` previsualiza operaciones destructivas

## Enfoques de integración

### 1. Plantilla AGENTS.md / CLAUDE.md

La forma más rápida de empezar. Copie nuestra [plantilla AGENTS.md](/es/docs/agents-md-template) en la raíz de su proyecto:

- `CLAUDE.md` para Claude Code
- `.cursorrules` para Cursor
- `.windsurfrules` para Windsurf

Esto da al agente contexto completo sobre los comandos disponibles, la arquitectura y las convenciones.

### 2. Pipeline de salida JSON

Cuando los agentes llaman a `rdc` en un subshell, la salida cambia automáticamente a JSON (detección non-TTY). Cada respuesta JSON utiliza un sobre consistente:

```json
{
  "success": true,
  "command": "machine query",
  "data": { ... },
  "errors": null,
  "warnings": [],
  "metrics": { "duration_ms": 42 }
}
```

Las respuestas de error incluyen los campos `retryable` y `guidance`:

```json
{
  "success": false,
  "errors": [{
    "code": "NOT_FOUND",
    "message": "Machine \"prod-2\" not found",
    "retryable": false,
    "guidance": "Verify the resource name with \"rdc machine query\" or \"rdc config repository list\""
  }]
}
```

### 3. Descubrimiento de capacidades del agente

El subcomando `rdc agent` proporciona introspección estructurada:

```bash
# List all commands with arguments and options
rdc agent capabilities

# Show detailed schema for a specific command
rdc agent schema "machine query"

# Execute a command with JSON stdin
echo '{"name": "prod-1"}' | rdc agent exec "machine query"
```

## Opciones clave para agentes

| Opción | Propósito |
|--------|-----------|
| `--output json` / `-o json` | Salida JSON legible por máquina |
| `--yes` / `-y` | Omitir confirmaciones interactivas |
| `--quiet` / `-q` | Suprimir la salida informativa en stderr |
| `--fields name,status` | Limitar la salida a campos específicos |
| `--dry-run` | Previsualizar operaciones destructivas sin ejecutar |

## Próximos pasos

- [Guía de configuración de Claude Code](/es/docs/ai-agents-claude-code) — Configuración paso a paso de Claude Code
- [Guía de configuración de Cursor](/es/docs/ai-agents-cursor) — Integración con el IDE Cursor
- [Referencia de salida JSON](/es/docs/ai-agents-json-output) — Documentación completa de la salida JSON
- [Plantilla AGENTS.md](/es/docs/agents-md-template) — Plantilla de configuración de agentes lista para copiar y pegar
