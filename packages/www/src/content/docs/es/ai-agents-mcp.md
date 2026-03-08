---
title: Configuración del Servidor MCP
description: Conecta agentes de IA a la infraestructura de Rediacc mediante el servidor de Model Context Protocol (MCP).
category: Guides
order: 33
language: es
sourceHash: "1b6cd5ba5d8d0ffe"
---

## Descripción general

El comando `rdc mcp serve` inicia un servidor MCP (Model Context Protocol) local que los agentes de IA pueden usar para gestionar tu infraestructura. El servidor utiliza transporte stdio — el agente de IA lo ejecuta como un subproceso y se comunica mediante JSON-RPC.

**Requisitos previos:** `rdc` instalado y configurado con al menos una máquina.

## Claude Code

Añade a tu archivo `.mcp.json` del proyecto:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve"]
    }
  }
}
```

O con una configuración con nombre:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--config", "production"]
    }
  }
}
```

## Cursor

Abre Configuración → MCP Servers → Añadir servidor:

- **Nombre**: `rdc`
- **Comando**: `rdc mcp serve`
- **Transporte**: stdio

## Herramientas disponibles

### Herramientas de lectura (seguras, sin efectos secundarios)

| Herramienta | Descripción |
|------|-------------|
| `machine_info` | Obtener información del sistema, contenedores, servicios y uso de recursos |
| `machine_containers` | Listar contenedores Docker en ejecución en una máquina |
| `machine_services` | Listar servicios systemd en una máquina |
| `machine_repos` | Listar repositorios desplegados en una máquina |
| `machine_health` | Ejecutar verificación de salud (sistema, contenedores, servicios, almacenamiento) |
| `config_repositories` | Listar repositorios configurados con mapeos de nombre a GUID |
| `agent_capabilities` | Listar todos los comandos disponibles de rdc CLI |

### Herramientas de escritura (destructivas)

| Herramienta | Descripción |
|------|-------------|
| `repo_up` | Desplegar/actualizar un repositorio en una máquina |
| `repo_down` | Detener un repositorio en una máquina |
| `term_exec` | Ejecutar un comando en una máquina remota vía SSH |

## Flujos de trabajo de ejemplo

**Verificar el estado de la máquina:**
> "¿Cuál es el estado de mi máquina de producción?"

El agente llama a `machine_info` → devuelve información del sistema, contenedores en ejecución, servicios y uso de recursos.

**Desplegar una aplicación:**
> "Despliega gitlab en mi máquina de staging"

El agente llama a `repo_up` con `name: "gitlab"` y `machine: "staging"` → despliega el repositorio, devuelve éxito/error.

**Depurar un servicio con fallos:**
> "Mi nextcloud va lento, averigua qué pasa"

El agente llama a `machine_health` → `machine_containers` → `term_exec` para leer logs → identifica el problema y sugiere una solución.

## Opciones de configuración

| Opción | Predeterminado | Descripción |
|--------|---------|-------------|
| `--config <name>` | (configuración predeterminada) | Configuración con nombre a usar para todos los comandos |
| `--timeout <ms>` | `120000` | Tiempo de espera predeterminado para comandos en milisegundos |

## Arquitectura

El servidor MCP no tiene estado. Cada llamada a una herramienta ejecuta `rdc` como un proceso hijo aislado con las flags `--output json --yes --quiet`. Esto significa:

- No hay fugas de estado entre llamadas a herramientas
- Utiliza tu configuración de `rdc` y claves SSH existentes
- Funciona tanto con el adaptador local como con el de nube
- Los errores en un comando no afectan a otros
