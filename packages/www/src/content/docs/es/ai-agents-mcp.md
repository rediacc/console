---
title: Configuración del Servidor MCP
description: Conecta agentes de IA a la infraestructura de Rediacc mediante el servidor de Model Context Protocol (MCP).
category: Guides
order: 33
language: es
sourceHash: "ce5f1392ebaa380b"
sourceCommit: "080291626bc44ee7bc452f029b614dfd5c6ca319"
---

## Descripción general

El comando `rdc mcp serve` inicia un servidor MCP (Model Context Protocol) local que los agentes de IA pueden usar para gestionar tu infraestructura. El servidor utiliza transporte stdio, el agente de IA lo ejecuta como un subproceso y se comunica mediante JSON-RPC.

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
| `machine_query` | Obtiene información del sistema, contenedores, servicios y uso de recursos de una máquina |
| `machine_containers` | Lista contenedores Docker con estado, salud, uso de recursos, etiquetas y dominio de ruta automática |
| `machine_services` | Lista servicios systemd gestionados por Rediacc (nombre, estado, subestado, reintentos, memoria, repositorio propietario) |
| `machine_repos` | Lista repositorios desplegados (nombre, GUID, tamaño, estado de montaje, estado Docker, número de contenedores, uso de disco, fecha de modificación, presencia de Rediaccfile) |
| `machine_health` | Ejecuta una comprobación de salud en una máquina (sistema, contenedores, servicios, almacenamiento) |
| `machine_list` | Lista todas las máquinas configuradas |
| `config_repositories` | Lista repositorios configurados con sus asignaciones nombre-GUID |
| `config_show_infra` | Muestra la configuración de infraestructura de una máquina (dominio base, IPs públicas, TLS, zona de Cloudflare) |
| `config_providers` | Lista proveedores de nube configurados para el aprovisionamiento de máquinas |
| `agent_capabilities` | Lista todos los comandos rdc CLI disponibles con sus argumentos y opciones |
| `repo_secret_list` | Lista nombres de secretos y modos de entrega de un repositorio (nunca los valores, nunca los hashes). Seguro para lectura. |
| `repo_secret_get` | Obtiene el hash SHA-256 y el modo de entrega de un secreto. El valor en texto plano no se devuelve por diseño. Úsalo para verificar que un secreto existe o ha sido rotado. |

### Herramientas de escritura (destructivas)

| Herramienta | Descripción |
|------|-------------|
| `repo_create` | Crea un nuevo repositorio cifrado en una máquina |
| `repo_up` | Despliega/actualiza un repositorio (ejecuta Rediaccfile up, inicia contenedores). Usa `mount` para el primer despliegue o tras un pull |
| `repo_down` | Detiene los contenedores del repositorio. NO desmonta por defecto. Usa `unmount` para también cerrar el contenedor LUKS |
| `repo_delete` | Elimina un repositorio (destruye contenedores, volúmenes e imagen cifrada). La credencial se archiva para recuperación |
| `repo_fork` | Crea un fork CoW con nuevo GUID y networkId (copia totalmente independiente, forking en línea disponible) |
| `backup_push` | Envía una copia de seguridad del repositorio a almacenamiento u otra máquina (mismo GUID -- copia de seguridad/migración, no fork) |
| `backup_pull` | Descarga una copia de seguridad del repositorio desde almacenamiento o una máquina. Tras el pull, despliega con `repo_up` (mount=true) |
| `machine_provision` | Aprovisiona una nueva máquina en un proveedor de nube usando OpenTofu |
| `machine_deprovision` | Destruye una máquina aprovisionada en la nube y la elimina de la configuración |
| `config_add_provider` | Añade una configuración de proveedor de nube para el aprovisionamiento de máquinas |
| `config_remove_provider` | Elimina una configuración de proveedor de nube |
| `term_exec` | Ejecuta un comando en una máquina remota mediante SSH |

## Flujos de trabajo de ejemplo

**Verificar el estado de la máquina:**
> "¿Cuál es el estado de mi máquina de producción?"

El agente llama a `machine_query` → devuelve información del sistema, contenedores en ejecución, servicios y uso de recursos.

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
| `--allow-grand` | off | Permite operaciones destructivas en repositorios grand (no fork) |

## Seguridad

El servidor MCP aplica dos capas de protección:

### Modo solo-fork (predeterminado)

Por defecto, el servidor opera en **modo solo-fork**: las herramientas de escritura (`repo_up`, `repo_down`, `repo_delete`, `backup_push`, `backup_pull`, `term_exec`) solo pueden operar sobre repositorios fork. Los agentes no pueden tocar repositorios grand (originales). Es así por diseño.

> **Los secretos por repositorio son exclusivos de la CLI por diseño.** `repo_secret_set` y `repo_secret_unset` no se exponen como herramientas MCP de manera intencional. Las escrituras requieren una precondición `--current <valor-anterior>` (o `--rotate-secret` para confirmar una rotación no verificada), y esa ceremonia necesita supervisión humana. Los agentes que necesiten sugerir una rotación de secreto deben llamar a `repo_secret_get` para confirmar el hash, y luego transmitir al usuario el comando CLI correspondiente mediante el campo `next.options[].run` del envelope de error JSON. Consulta [Seguridad de agentes IA](/en/docs/ai-agents-safety#structured-next-action-hints) para ver el patrón completo, y [Repositorios § Secretos](/en/docs/repositories#secrets) para la guía dirigida al operador.

Para permitir que un agente modifique repositorios grand, inícialo con `--allow-grand`:

```json
{
  "mcpServers": {
    "rdc": {
      "command": "rdc",
      "args": ["mcp", "serve", "--allow-grand"]
    }
  }
}
```

También puedes establecer la variable de entorno `REDIACC_ALLOW_GRAND_REPO` con un único nombre de repositorio, una lista de nombres separados por comas (por ejemplo `repo1,repo2,repo3`) o `*` para todos los repositorios. Los espacios alrededor de cada entrada se ignoran, por lo que `repo1, repo2` también funciona. El acceso a nivel de máquina (por ejemplo `term connect -m <machine>` sin repositorio) sigue requiriendo `*`; una lista de nombres de repositorios no lo desbloquea.

### Claves SSH por repositorio y sandbox en el servidor

Cada repositorio tiene su propio par de claves SSH. La clave pública se despliega en `authorized_keys` con un prefijo `command=` que obliga a todas las sesiones SSH a pasar por `renet sandbox-gateway <repo-name>`, un ForceCommand en el servidor que ningún cliente puede eludir, incluido VS Code.

**Funcionamiento:**
1. `rdc repo create` o `rdc repo fork` genera un par de claves ed25519 únicas por repositorio
2. La clave pública se despliega en el remoto con `command="renet sandbox-gateway <name>"`
3. Cada conexión SSH que usa esa clave pasa por el gateway, que aplica:
   - **Landlock LSM**, restricciones de sistema de archivos a nivel de kernel sobre la ruta de montaje del repositorio
   - **OverlayFS home overlay**, las escrituras en `$HOME` se capturan por repositorio, las lecturas se pasan al home real
   - **TMPDIR por repositorio** en `<datastore>/.interim/sandbox/<name>/tmp/`
   - **Acceso a Docker** a través del socket Docker aislado del repositorio
   - **Reducción de privilegios** al usuario universal (`rediacc`)
4. El `.envrc` del repositorio se carga automáticamente para Docker y la configuración del entorno

**Lectura/escritura permitida**: ruta de montaje del repositorio, espacio de trabajo sandbox por repositorio, directorio home (mediante overlay), socket Docker
**Solo lectura permitida**: rutas del sistema (`/usr`, `/bin`, `/etc`, `/proc`, `/sys`)
**Bloqueado**: rutas de montaje de otros repositorios, archivos del sistema fuera de la lista permitida

**Integración con VS Code**: cada repositorio tiene su propia instalación del servidor VS Code en `<datastore>/.interim/sandbox/<name>/.vscode-server/`. Varios repositorios pueden estar abiertos simultáneamente con entornos sandbox independientes, sin compartir servidor entre repositorios.

Esto evita el movimiento lateral. Aunque un agente obtenga acceso shell a un fork, no puede leer ni modificar otros repositorios en la misma máquina. El SSH a nivel de máquina (sin repositorio) usa la clave de equipo y no tiene sandbox.

## Arquitectura

El servidor MCP no tiene estado. Cada llamada a una herramienta ejecuta `rdc` como un proceso hijo aislado con las flags `--output json --yes --quiet`. Esto significa:

- No hay fugas de estado entre llamadas a herramientas
- Utiliza tu configuración de `rdc` y claves SSH existentes
- Funciona tanto con el adaptador local como con el de nube
- Los errores en un comando no afectan a otros
