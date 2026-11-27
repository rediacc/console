---
title: Guía de configuración de Claude Code
description: >-
  Guía paso a paso para configurar Claude Code para la gestión autónoma de
  infraestructura Rediacc.
category: Guides
tags:
  - ai-agents
  - cli
subcategory: ai-agents
order: 31
language: es
sourceHash: "81cd5da23b9747e0"
sourceCommit: "29bdc2aca2ed2b968e47005622ff9cfbbb66e56a"
---

Claude Code funciona de forma nativa con Rediacc a través del CLI `rdc`. Esta guía cubre la configuración, los permisos y los flujos de trabajo habituales.

> **La seguridad primero**: Antes de conectar un agente a cualquier cosa que toque secretos, lea [Seguridad y medidas de protección para agentes de IA](/es/docs/ai-agents-safety). Claude Code ejecutándose bajo `rdc` se detecta como agente. Las mutaciones sensibles requieren `--current <previous-value>` (precondición estilo passwd) tanto para humanos como para agentes; `--rotate-secret` (rotación reconocida y auditada) solo cuenta para un humano en un terminal. `rdc config edit` (interactivo, `--apply`, `--reveal`) se rechaza sin ninguna anulación, y los repositorios grand y el SSH directo a la máquina siguen cerrados salvo que un humano los acepte explícitamente dentro de lo que permita la política. Cuando una precondición falla, el campo `errors[].next.options[].run` del envelope JSON indica al agente el comando exacto de la CLI que debe sugerir al usuario. Transmítalo literalmente.

## Configuración rápida

1. Instale el CLI: `curl -fsSL https://www.rediacc.com/install.sh | bash`
2. Copie la [plantilla AGENTS.md](/es/docs/agents-md-template) en la raíz de su proyecto como `CLAUDE.md`
3. Inicie Claude Code en el directorio del proyecto

Claude Code lee `CLAUDE.md` al iniciarse y lo utiliza como contexto persistente para todas las interacciones.

## Configuración de CLAUDE.md

Coloque esto en la raíz de su proyecto. Consulte la [plantilla AGENTS.md](/es/docs/agents-md-template) completa para una versión íntegra. Secciones clave:

```markdown
# Rediacc Infrastructure

## CLI Tool: rdc

### Common Operations
- Status: rdc machine status <machine> -o json
- Deploy: rdc repo up <repo>@<machine> --yes
- Containers: rdc machine status <machine> --containers -o json
- Health: rdc machine health <machine> -o json
- SSH: rdc term connect <machine|repo-ref>

### Rules
- Always use --output json when parsing output
- Always use --yes for automated confirmations
- Use --dry-run before destructive operations
```

## Permisos de herramientas

Claude Code solicitará permiso para ejecutar comandos `rdc`. Puede preautorizar las operaciones habituales añadiendo a la configuración de Claude Code:

- Permitir `rdc machine status *`, verificaciones de estado de solo lectura
- Permitir `rdc machine status * --containers`, listado de contenedores
- Permitir `rdc machine health *`, verificaciones de salud
- Permitir `rdc repo list`, listado de repositorios

Para operaciones destructivas (`rdc repo up`, `rdc repo delete`), Claude Code siempre pedirá confirmación a menos que las autorice explícitamente.

## Ejemplos de flujos de trabajo

### Verificar el estado de la infraestructura

```
You: "What's the status of prod-1?"

Claude Code runs: rdc machine status prod-1 -o json
→ Shows machine status, repositories, containers, services
```

### Desplegar un repositorio

```
You: "Deploy the mail repo to prod-1"

Claude Code runs: rdc repo up mail@prod-1 --dry-run -o json
→ Shows what would happen
Claude Code runs: rdc repo up mail@prod-1 --yes
→ Deploys the repository
```

### Diagnosticar problemas de contenedores

```
You: "Why is the nextcloud container unhealthy?"

Claude Code runs: rdc machine status prod-1 --containers -o json --fields name,status,repository
→ Lists container states
Claude Code runs: rdc repo logs nextcloud@prod-1 -c nextcloud-app --lines 50
→ Checks recent logs
```

### Sincronización de archivos

```
You: "Upload the local config to the mail repo"

Claude Code runs: rdc repo sync upload mail@prod-1 --local ./config --dry-run
→ Shows files that would be synced
Claude Code runs: rdc repo sync upload mail@prod-1 --local ./config
→ Syncs the files
```

## Consejos

- Claude Code detecta automáticamente non-TTY y cambia a salida JSON, no es necesario especificar `-o json` en la mayoría de los casos
- Ejecute `rdc --help-all` para que Claude Code descubra todos los comandos disponibles
- La opción `--fields` ayuda a mantener bajo el uso de la ventana de contexto cuando solo necesita datos específicos
