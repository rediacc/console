---
title: Guía de configuración de Cursor
description: Configure el IDE Cursor para trabajar con la infraestructura Rediacc usando .cursorrules y la integración del terminal.
category: Guides
order: 32
language: es
---

Cursor se integra con Rediacc a través de comandos de terminal y el archivo de configuración `.cursorrules`.

## Configuración rápida

1. Instale el CLI: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. Copie la [plantilla AGENTS.md](/es/docs/agents-md-template) en la raíz de su proyecto como `.cursorrules`
3. Abra el proyecto en Cursor

Cursor lee `.cursorrules` al iniciarse y lo utiliza como contexto para el desarrollo asistido por IA.

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
rdc machine info prod-1 -o json
```

### Desplegar cambios

Pregunte a Cursor: *"Despliega la configuración actualizada de nextcloud"*

Cursor ejecuta en el terminal:
```bash
rdc repo up nextcloud -m prod-1 --yes
```

### Ver registros

Pregunte a Cursor: *"Muéstrame los registros recientes del contenedor de correo"*

Cursor ejecuta en el terminal:
```bash
rdc term prod-1 mail -c "docker logs mail-postfix --tail 100"
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
- El comando `rdc agent capabilities` proporciona a Cursor una referencia completa de comandos
- Combine `.cursorrules` con un archivo `CLAUDE.md` para máxima compatibilidad entre herramientas de IA
