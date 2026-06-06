---
title: Integración de agentes de IA - Descripción general
description: "Cómo Claude Code, Cursor y Cline gestionan la infraestructura Rediacc mediante rdc: salida JSON, introspección del agente y medidas de seguridad."
category: Guides
order: 30
language: es
sourceHash: "0aa0c975030d4856"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

`rdc` está diseñado pensando en los agentes. Claude Code, Cursor, Cline: cualquier asistente de IA que llame a `rdc` desde un subshell obtiene salida JSON estructurada, errores legibles por máquina y las medidas de seguridad necesarias para gestionar infraestructura Rediacc de forma autónoma. Así es como funciona la integración.

## Por qué autoalojamiento + agentes de IA

La arquitectura de Rediacc se adapta bien a los agentes:

- **CLI primero**: Cada operación es un comando `rdc`, no se requiere GUI
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

Añádala al proyecto y el agente dispondrá de la referencia completa de comandos, el contexto de arquitectura y las convenciones que necesita para trabajar sin tener que adivinar.

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
rdc agent schema --command "machine query"

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

## Seguridad y medidas de protección

El CLI no trata a los agentes igual que a un humano en el terminal. Las operaciones sensibles requieren demostrar que ya se conoce el estado actual (mediante el flag `--current`), los flujos con editor interactivo se rechazan por defecto, y cada rechazo queda registrado en el log de auditoría. La referencia [Seguridad y medidas de protección para agentes de IA](/es/docs/ai-agents-safety) incluye la tabla completa de restricciones, el modelo de verificación de conocimiento previo, el permiso `REDIACC_ALLOW_CONFIG_EDIT` y el log de auditoría con cadena de hashes.

## Próximos pasos

- [Seguridad y medidas de protección para agentes de IA](/es/docs/ai-agents-safety), Qué pueden y no pueden hacer los agentes, verificación de conocimiento previo, log de auditoría
- [Guía de configuración de Claude Code](/es/docs/ai-agents-claude-code), Configuración paso a paso de Claude Code
- [Guía de configuración de Cursor](/es/docs/ai-agents-cursor), Integración con el IDE Cursor
- [Referencia de salida JSON](/es/docs/ai-agents-json-output), Documentación completa de la salida JSON
- [Plantilla AGENTS.md](/es/docs/agents-md-template), Plantilla de configuración de agentes lista para copiar y pegar
