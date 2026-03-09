---
title: Guía de configuración de Claude Code
description: Guía paso a paso para configurar Claude Code para la gestión autónoma de infraestructura Rediacc.
category: Guides
order: 31
language: es
sourceHash: "faa990e37ee96a23"
---

Claude Code funciona de forma nativa con Rediacc a través del CLI `rdc`. Esta guía cubre la configuración, los permisos y los flujos de trabajo habituales.

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
- Status: rdc machine info <machine> -o json
- Deploy: rdc repo up <repo> -m <machine> --yes
- Containers: rdc machine containers <machine> -o json
- Health: rdc machine health <machine> -o json
- SSH: rdc term <machine> [repo]

### Rules
- Always use --output json when parsing output
- Always use --yes for automated confirmations
- Use --dry-run before destructive operations
```

## Permisos de herramientas

Claude Code solicitará permiso para ejecutar comandos `rdc`. Puede preautorizar las operaciones habituales añadiendo a la configuración de Claude Code:

- Permitir `rdc machine info *` — verificaciones de estado de solo lectura
- Permitir `rdc machine containers *` — listado de contenedores
- Permitir `rdc machine health *` — verificaciones de salud
- Permitir `rdc config repositories` — listado de repositorios

Para operaciones destructivas (`rdc repo up`, `rdc repo delete`), Claude Code siempre pedirá confirmación a menos que las autorice explícitamente.

## Ejemplos de flujos de trabajo

### Verificar el estado de la infraestructura

```
You: "What's the status of prod-1?"

Claude Code runs: rdc machine info prod-1 -o json
→ Shows machine status, repositories, containers, services
```

### Desplegar un repositorio

```
You: "Deploy the mail repo to prod-1"

Claude Code runs: rdc repo up mail -m prod-1 --dry-run -o json
→ Shows what would happen
Claude Code runs: rdc repo up mail -m prod-1 --yes
→ Deploys the repository
```

### Diagnosticar problemas de contenedores

```
You: "Why is the nextcloud container unhealthy?"

Claude Code runs: rdc machine containers prod-1 -o json --fields name,status,repository
→ Lists container states
Claude Code runs: rdc term prod-1 -c "docker logs nextcloud-app --tail 50"
→ Checks recent logs
```

### Sincronización de archivos

```
You: "Upload the local config to the mail repo"

Claude Code runs: rdc repo sync upload -m prod-1 -r mail -l ./config --dry-run
→ Shows files that would be synced
Claude Code runs: rdc repo sync upload -m prod-1 -r mail -l ./config
→ Syncs the files
```

## Consejos

- Claude Code detecta automáticamente non-TTY y cambia a salida JSON — no es necesario especificar `-o json` en la mayoría de los casos
- Use `rdc agent capabilities` para que Claude Code descubra todos los comandos disponibles
- Use `rdc agent schema "command name"` para información detallada de argumentos y opciones
- La opción `--fields` ayuda a mantener bajo el uso de la ventana de contexto cuando solo necesita datos específicos
