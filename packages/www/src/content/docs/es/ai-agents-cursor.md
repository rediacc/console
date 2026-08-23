---
title: Guía de configuración de Cursor
description: Configure el IDE Cursor para trabajar con la infraestructura Rediacc usando .cursorrules y la integración del terminal.
category: Guides
tags:
  - ai-agents
  - cli
subcategory: ai-agents
order: 32
language: es
sourceHash: "e0fb319a9e477324"
sourceCommit: "23543669cd22bce3f14d69a0886bac8a12061412"
---

Versión resumida: `.cursorrules` carga el contexto de Rediacc en la IA de Cursor; el terminal le permite ejecutar comandos `rdc` contra sus máquinas reales.

## Configuración rápida

1. Instale el CLI: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. Copie la [plantilla AGENTS.md](/es/docs/agents-md-template) en la raíz de su proyecto como `.cursorrules`
3. Abra el proyecto en Cursor

Cursor lee `.cursorrules` al iniciarse. Tenga en cuenta que se aplican límites de ventana de contexto, así que mantenga el archivo centrado en sus máquinas y repositorios reales en lugar de texto genérico.

## Configuración de .cursorrules

Cree `.cursorrules` en la raíz de su proyecto con el contexto de infraestructura Rediacc. Consulte la [plantilla AGENTS.md](/es/docs/agents-md-template) completa para una versión íntegra.

Las secciones clave a incluir:

- Nombre de la herramienta CLI (`rdc`) e instalación
- Comandos habituales con la opción `--output json`
- Descripción general de la arquitectura (aislamiento de repositorios, daemons Docker)
- Reglas de terminología (adaptadores, no modos)

## Integración con el terminal

Cursor puede ejecutar comandos `rdc` a través de su terminal integrado. Patrones habituales:

### Verificar el estado

Pregunte a Cursor: *"Verifica el estado de mi servidor de producción"*

Cursor ejecuta en el terminal:
```bash
rdc machine status prod-1 -o json
```

### Desplegar cambios

Pregunte a Cursor: *"Despliega la configuración actualizada de nextcloud"*

Cursor ejecuta en el terminal:
```bash
rdc repo up nextcloud@prod-1 --yes
```

### Ver registros

Pregunte a Cursor: *"Muéstrame los registros recientes del contenedor de correo"*

Cursor ejecuta en el terminal:
```bash
rdc repo logs mail@prod-1 -c mail-postfix --lines 100
```

## Configuración del espacio de trabajo

Para proyectos en equipo, añada la configuración específica de Rediacc para Cursor en `.cursor/settings.json`:

```json
{
  "terminal.defaultProfile": "bash",
  "ai.customInstructions": "Use rdc CLI for all infrastructure operations. Always use --output json when parsing results."
}
```

## Consejos

- El modo Composer de Cursor funciona bien para tareas de infraestructura con múltiples pasos
- Use `@terminal` en el chat de Cursor para hacer referencia a la salida reciente del terminal
- El comando `rdc --help-all` proporciona a Cursor una referencia completa de comandos
- Combine `.cursorrules` con un archivo `CLAUDE.md` para máxima compatibilidad entre herramientas de IA
