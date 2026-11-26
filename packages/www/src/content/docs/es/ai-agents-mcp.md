---
title: Configuración del Servidor MCP
description: Conecta agentes de IA a la infraestructura de Rediacc mediante el servidor de Model Context Protocol (MCP).
category: Guides
tags:
  - ai-agents
  - cli
subcategory: ai-agents
order: 33
language: es
sourceHash: "ece2cec7cd2f4bc9"
sourceCommit: "948dc510c78b93b73ea5b1b7b379cdb93141486e"
---

## Descripción general

Dos servidores MCP (Model Context Protocol) toman sus herramientas de un único registro, y el servidor remoto ofrece un subconjunto:

| Servidor | Transporte | Se ejecuta | Herramientas |
|---|---|---|---|
| Local | stdio | `rdc mcp serve`, lanzado por el agente | Todas las herramientas |
| Remoto | Streamable HTTP | `https://mcp.<region>.rediacc.cloud/g/<grantId>` | Las herramientas remotas, es decir, todas salvo las de la tabla de solo locales |

**Requisitos previos:** `rdc` instalado y configurado con al menos una máquina para el servidor local. Para el servidor remoto hace falta un grant sobre una configuración.

## Servidor local

`rdc mcp serve` inicia un servidor MCP por stdio. El agente lo lanza como subproceso y se comunica con él mediante JSON-RPC.

### Claude Code

El archivo `.mcp.json` del proyecto lleva la entrada:

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

### Cursor

Abre Settings → MCP Servers → Add Server:

- **Name**: `rdc`
- **Command**: `rdc mcp serve`
- **Transport**: stdio

### Opciones

| Opción | Predeterminado | Descripción |
|--------|----------------|-------------|
| `--config <name>` | (configuración predeterminada) | Configuración con nombre que se usa en todos los comandos |
| `--timeout <ms>` | `120000` | Tiempo de espera predeterminado de los comandos, en milisegundos |

## Servidor remoto

En cada región se ejecuta un Worker MCP en `mcp.<region>.rediacc.cloud`. Cada agente se conecta a la URL de un grant: `https://mcp.<region>.rediacc.cloud/g/<grantId>`. El grant indica una configuración, una fecha de caducidad y un alcance: un indicador de solo lectura, una lista de herramientas permitidas y patrones (globs) de nombres de máquinas y repositorios. Las llamadas a herramientas se ejecutan en el ejecutor de la organización del grant.

### Credenciales

Ambas formas identifican el grant; el id del grant en la URL solo lo nombra.

| Forma | Uso | Se envía como |
|---|---|---|
| Token de acceso OAuth | Clientes interactivos como claude.ai | `Authorization: Bearer <token>` |
| Bearer de agente `rmcp_<grantId>.<secret>` | Agentes sin interfaz | `Authorization: Bearer` o `x-api-key` |

Una credencial en la cadena de consulta se rechaza con 400. Un token OAuth ausente, caducado o de otro grant recibe 401 con una cabecera `WWW-Authenticate: Bearer resource_metadata=...` que apunta al documento de recurso protegido del grant, de modo que el cliente OAuth renueva el token o inicia sesión. Un grant desconocido, un secreto incorrecto y un bearer de agente de otro grant reciben todos el mismo 401 sin más.

### OAuth

El Worker es un servidor de autorización OAuth 2.1 con PKCE (solo S256). Los clientes se registran mediante un Client ID Metadata Document o por registro dinámico de clientes en `/register`.

| Endpoint | Finalidad |
|---|---|
| `/.well-known/oauth-authorization-server` | Metadatos del servidor |
| `/.well-known/oauth-protected-resource/g/<grantId>` | Documento de recurso protegido de un grant |
| `/authorize` | Inicia la autorización y redirige a la página de cuenta `/account/mcp/authorize` |
| `/oauth/token` | Intercambio de código, renovación y revocación |
| `/register` | Registro dinámico de clientes |

El cliente envía `resource=https://mcp.<region>.rediacc.cloud/g/<grantId>`. La autorización solo se completa para el grant que nombra el recurso, y un token solo funciona en la URL de su grant. La redirección de `/authorize` lleva un identificador firmado de un solo uso y ningún secreto.

### Duración de los tokens

Un token nunca dura más que su grant.

| Token | Duración |
|---|---|
| Token de acceso | El menor entre 1 hora y el tiempo que le queda al grant |
| Token de renovación | El menor entre 30 días y el tiempo que le queda al grant |

Cada intercambio de código y cada renovación vuelve a consultar el grant. Un grant caducado, revocado o con la clave rotada responde `invalid_grant` y revoca la concesión OAuth. Los tokens de renovación rotan, y presentar uno dos veces revoca el grant.

### Una configuración por grant

Un grant sirve únicamente la configuración que nombra. Un `tools/call` con un argumento que nombre otra configuración (`config` o alguna variante) se rechaza con `REDIACC_GRANT_SCOPE` antes de que se ejecute nada. Quien tenga varias configuraciones autoriza un grant por cada una. Una herramienta fuera de la lista permitida del grant, o una herramienta de escritura bajo un grant de solo lectura, no aparece en `tools/list` y se rechaza si se llama.

### Regiones

El id de un grant empieza por su región, como `eu_`. Una petición a `/g/<grantId>` en el Worker de otra región recibe un 421 con la URL correcta:

```json
{
  "code": "REDIACC_WRONG_REGION",
  "message": "This grant lives in the us region. Use https://mcp.us.rediacc.cloud/g/us_...",
  "region": "us",
  "mcpUrl": "https://mcp.us.rediacc.cloud/g/us_..."
}
```

Un grant nunca se acepta como recurso OAuth, audiencia de token ni destino de autorización fuera de su región.

### Estados del grant y límites

Un grant caducado, revocado o que ha perdido su clave por una rotación de claves del almacén de configuración sigue respondiendo a `initialize` y `tools/list`. Cada `tools/call` devuelve entonces `REDIACC_GRANT_EXPIRED`, `REDIACC_GRANT_REVOKED` o `REDIACC_KEY_ROTATED` con una `reauthUrl` que el usuario abre para autorizar de nuevo.

Cada grant admite 60 llamadas por minuto y 5 llamadas en curso a la vez. Una llamada que supere cualquiera de los dos límites devuelve `REDIACC_RATE_LIMITED` con `retryAfterSeconds`.

## Herramientas disponibles

<!-- >>> translated-table: mcp-tools -->

| Herramienta | Destructiva | Descripción |
|---|---|---|
| `backup_browse` | no | Lista los archivos que contiene un repositorio. |
| `backup_cancel` | no | Cancela una copia de seguridad en curso en una máquina remota. |
| `backup_check` | no | Comprueba que una instantánea almacenada se abre con la frase de contraseña, restaurando un archivo. |
| `backup_immutability_show` | no | Muestra la ventana de borrado diferido vigente. |
| `backup_list` | no | Lista los artefactos de copia de seguridad de una máquina. |
| `backup_manifests` | no | Lista los manifiestos de instantáneas de copia de seguridad registrados en el servidor. |
| `backup_reconcile` | sí | Restablece el libro de bytes almacenados de un repositorio a lo que el almacén contiene realmente (nunca elimina un fragmento). |
| `backup_repair` | sí | Vuelve a subir, desde el ancla de esta máquina, los fragmentos que el almacén perdió o conserva dañados. |
| `backup_restore` | sí | Convierte un artefacto de copia de seguridad en un repositorio activo. |
| `backup_retention` | no | Muestra la política de retención de instantáneas que aplica el servidor. |
| `backup_retention_preview` | no | Muestra qué instantáneas eliminaría la próxima limpieza y cuánto espacio liberaría. |
| `backup_run` | no | Ejecuta una copia de seguridad ahora. |
| `backup_snapshot` | no | Sube una instantánea del almacén de fragmentos: primero el inventario completo y después las celdas modificadas. |
| `backup_status` | no | Muestra el estado de las copias de seguridad y del temporizador en una máquina remota. |
| `backup_strategy_list` | no | Lista todas las estrategias de copia de seguridad. |
| `backup_strategy_show` | no | Muestra los detalles de una estrategia de copia de seguridad. |
| `backup_toc-key_sync` | no | Instala en su máquina la clave de listado del repositorio, o reemplaza una distinta. |
| `backup_undelete` | no | Cancela el borrado diferido de una instantánea antes de que surta efecto. |
| `backup_usage` | no | Muestra la cuota de almacenamiento de copias de seguridad, los bytes almacenados y el uso por repositorio. |
| `backup_verify` | no | Verifica el ancla de copia de seguridad de un repositorio frente al almacén de fragmentos. |
| `cluster_snapshot_list` | no | Lista las instantáneas de grupo del clúster. |
| `cluster_status` | no | Lista todos los clústeres o, con el nombre de un clúster, muestra su configuración completa. |
| `config_access_list` | no | Lista las claves de acceso de la configuración. |
| `config_prune` | no | Elimina lo que sobra del archivo de configuración local ~/.config/rediacc/<config>.json. |
| `config_reconcile` | no | Reconstruye el depósito de estado local a partir del estado real de las máquinas (renet list all). |
| `config_show` | no | Muestra los detalles de la configuración actual. |
| `credits` | no | Muestra el saldo de créditos restante de esta cuenta. |
| `datastore_list` | no | Lista los datastores con nombre, dónde están conectados y qué contienen. |
| `datastore_snapshot_list` | no | Lista las instantáneas de un datastore. |
| `datastore_status` | no | Muestra un datastore: su backend, conexión, uso, repositorios e instantáneas. |
| `feedback_list` | no | Lista los informes de comentarios visibles para esta máquina: id, huella corta, estado y fechas. |
| `feedback_report` | no | Crea un informe a partir del último comando fallido (--last), de un comando registrado (--command <n>) o solo de un mensaje, muestra exactamente lo que se enviaría y lo envía tras la confirmación. |
| `feedback_show` | no | Muestra un informe de comentarios por su id (o un prefijo único), con su estado, número de apariciones y fechas. |
| `incident_status` | no | Lista los incidentes de la organización o muestra uno con su alcance, ventana, pasos por máquina y los relojes de los plazos de alerta temprana, notificación e informe final. |
| `job_cancel` | sí | Cancela un trabajo desacoplado en ejecución. |
| `job_dismiss` | sí | Abandona tickets de trabajo en local: se descartan sus pasos pendientes y el ticket deja de aparecer. |
| `job_gc` | sí | Elimina los trabajos terminados y sus registros. |
| `job_list` | no | Lista los trabajos desacoplados de una máquina, del más reciente al más antiguo. |
| `job_logs` | no | Reproduce o sigue el registro de eventos de un trabajo desacoplado. |
| `job_status` | no | Muestra el estado de un trabajo desacoplado. |
| `job_wait` | no | Espera hasta 50 s a que termine un trabajo. |
| `legal` | no | Imprime los enlaces a los documentos legales en el idioma de la CLI junto con los enlaces vinculantes en inglés, la versión vigente de los Términos del servicio con su suma de verificación y URL de archivo, la aceptación registrada (del servidor de cuentas con sesión iniciada, de esta configuración en modo anónimo) y la entidad contratante. |
| `machine_access_show` | no | Muestra las claves de acceso vinculadas a una máquina y los rangos que cada una resuelve allí. |
| `machine_add` | no | Registra una máquina existente a la que se pueda llegar por SSH. |
| `machine_containers` | no | Lista los contenedores Docker de una máquina. |
| `machine_converge` | sí | Reinicia, de uno en uno, cada daemon de repositorio que sigue con un diseño de runtime anterior, para que pase al actual. |
| `machine_deprovision` | sí | Destruye una máquina aprovisionada en la nube y la elimina de la configuración. |
| `machine_gpu_list` | no | Lista las GPU detectadas en una máquina, los nombres de dispositivo CDI que definen sus especificaciones y los repositorios a los que se concede cada dispositivo. |
| `machine_health` | no | Comprueba la salud de una máquina para pipelines de CI/CD. |
| `machine_infra_show` | no | Muestra la configuración de infraestructura de una máquina (dominio base, IP públicas, puertos), los ajustes TLS compartidos (correo del certificado, token DNS de CF) y el ID de zona de Cloudflare. |
| `machine_list` | no | Lista las máquinas. |
| `machine_provider_add` | no | Añade un proveedor de nube. |
| `machine_provider_list` | no | Lista los proveedores de nube configurados para el aprovisionamiento de máquinas. |
| `machine_provider_remove` | sí | Elimina la configuración de un proveedor de nube. |
| `machine_provision` | sí | Aprovisiona una máquina nueva en un proveedor de nube con OpenTofu. |
| `machine_prune` | sí | Elimina de una máquina los recursos huérfanos del datastore y las instantáneas obsoletas. |
| `machine_remove` | sí | Elimina una máquina de la configuración. |
| `machine_repos` | no | Lista los repositorios desplegados en una máquina. |
| `machine_restart-services` | sí | Pasa los daemons de renet que aún ejecutan un binario reemplazado al binario instalado, unidad por unidad, y confirma que cada una está activa antes de seguir con la siguiente. |
| `machine_scan-keys` | no | Registra en la configuración local las claves de host SSH de la máquina. |
| `machine_services` | no | Lista los servicios systemd gestionados por Rediacc en una máquina (nombre, estado, subestado, número de reinicios, memoria, repositorio resuelto a su nombre con el original en repository_guid). |
| `machine_setup` | no | Termina la incorporación de una máquina: instala renet y la prepara para alojar repositorios. |
| `machine_status` | no | Obtiene los detalles de conexión (IP, usuario, puerto, datastore), la información del sistema, los contenedores (repositorio resuelto a su nombre, original en repository_guid, dominio, autoRoute), los servicios (repositorio resuelto a su nombre), los repositorios (nombre resuelto desde el GUID, original en guid) y el uso de recursos de una máquina. |
| `repo_admin_fsck` | no | Valida las referencias de la configuración (ramas/HEAD) frente a los objetos presentes en una máquina e informa de referencias colgantes y commits huérfanos. |
| `repo_cat` | no | Lee en stdout una ventana acotada de un archivo de un repositorio (los diagnósticos van a stderr). |
| `repo_checkout` | sí | Clona con reflink un commit inmutable (o la punta de una rama) en un fork de trabajo nuevo y escribible, y apunta HEAD a él. |
| `repo_commit` | sí | Congela un fork de trabajo montado en un nuevo commit inmutable (como en git). |
| `repo_create` | sí | Crea un repositorio nuevo. |
| `repo_delete` | sí | Elimina un repositorio y sus datos. |
| `repo_diff` | no | Diff a nivel de archivo al estilo git entre dos repositorios fork con copy-on-write. |
| `repo_down` | sí | Detiene los contenedores Docker de un repositorio (ejecuta Rediaccfile down). |
| `repo_exec` | sí | Ejecuta un comando dentro de un contenedor de un repositorio. |
| `repo_flows` | no | Lista los flujos de red registrados para un repositorio en una ventana de tiempo: hora, proceso, destino, bytes salientes y entrantes, y el ASN y el país del destino cuando se conocen. |
| `repo_fork` | sí | Crea un fork CoW casi instantáneo de un repositorio con un GUID y un networkId NUEVOS (copia totalmente independiente). |
| `repo_gc` | sí | Recolección de basura por alcanzabilidad: elimina los objetos de commit inmutables de una máquina a los que no llega ninguna rama ni HEAD. |
| `repo_health` | no | Ejecuta las comprobaciones health() del Rediaccfile de un repositorio y termina con 0 (correcto), 1 (aviso) o 2 (error). |
| `repo_list` | no | Lista los repositorios de una máquina. |
| `repo_log` | no | Imprime el historial de commits alcanzable desde el commit actual de un fork de trabajo (o desde una referencia de commit), recorriendo la cadena de padres que registra 'rdc repo commit'. |
| `repo_logs` | no | Muestra los registros de la aplicación de los contenedores de un repositorio. |
| `repo_merge` | sí | Fusiona, de forma segura para el ciclo de vida, un commit o fork de origen en un fork de trabajo de destino. |
| `repo_migrate` | sí | Mueve un repositorio a otra máquina con un tiempo de inactividad mínimo: copia en dos fases (sincronización masiva en marcha y, después, una parada breve, sincronización del delta e inicio en el destino) con cambio de DNS. |
| `repo_opens` | no | Lista las aperturas de archivos registradas para un repositorio en una ventana de tiempo: hora, proceso y ruta, con las rutas sensibles marcadas. |
| `repo_pull` | sí | Descarga un repositorio desde otra máquina. |
| `repo_push` | sí | Envía una copia de seguridad de un repositorio al almacenamiento o directamente a otra máquina. |
| `repo_replicate` | no | Aprovisiona réplicas de lectura de un repositorio. |
| `repo_replicate_remove` | sí | Elimina un conjunto de réplicas: borra sus objetos k8s generados (limitado por etiqueta), descarta sus datastores fork, elimina su instantánea y olvida el estado. |
| `repo_replicate_status` | no | Muestra los conjuntos de réplicas gestionados: réplicas, nodos anfitriones, datastores fork, instantánea y marcas de actualización. |
| `repo_secret_get` | no | Muestra el resumen SHA-256 de un secreto. |
| `repo_secret_list` | no | Lista las claves y los modos de los secretos (nunca valores ni resúmenes). |
| `repo_status` | no | Obtiene el estado de un repositorio (estado de montaje, daemon de Docker en marcha, número de contenedores, uso de disco). |
| `repo_trim` | no | Recupera espacio del pool del datastore a partir de repositorios montados (en línea, sin tiempo de inactividad). |
| `repo_up` | sí | Despliega o actualiza un repositorio (ejecuta Rediaccfile up mediante renet compose y arranca los contenedores). |

<!-- <<< translated-table -->

<!-- >>> translated-table: mcp-tools-local -->

| Herramienta | Destructiva | Descripción |
|---|---|---|
| `cluster_kubeconfig` | no | Obtiene por SSH el kubeconfig del nodo de control del clúster y lo guarda en caché local (0600) para kubectl. |
| `config_audit_log` | no | Lee el registro de auditoría de las modificaciones hechas mediante esta configuración. |
| `config_audit_verify` | no | Verifica que la cadena de hashes del registro de auditoría no haya sido manipulada. |
| `config_current` | no | Muestra la configuración activa: nombre, archivo, servidor y canal resueltos, estado del token. |
| `config_list` | no | Lista todos los archivos de configuración. |
| `forensics_verify` | no | Recalcula la cadena de hashes de los archivos diarios de auditoría y las cadenas de lotes forenses firmados de un directorio de evidencias (un directorio de exportación de rdc incident) y enumera cada hueco y cada edición. |
| `incident_export` | no | Escribe la ventana del incidente en un directorio: el registro del incidente con sus relojes, la línea de tiempo combinada, los agregados de bytes salientes, el manifiesto en bruto de la cadena y los archivos en bruto que lista, bajo las claves del manifiesto. |
| `machine_infra_cert_status` | no | Muestra el inventario de certificados en caché. |
| `server_status` | no | Muestra el estado, el nivel, el certificado y la imagen de un servidor instalado. |
| `version` | no | Imprime la versión de la CLI, la plataforma, el canal de actualización y la licencia activa: el plan con sesión iniciada, "anonymous (FREE per repository)" sin sesión y "unknown (server unreachable)" cuando no se puede contactar con el servidor de cuentas. |

<!-- <<< translated-table -->

## Flujos de trabajo de ejemplo

**Comprobar el estado de una máquina:**
> «¿Cuál es el estado de mi máquina de producción?»

El agente llama a `machine_status` y obtiene los detalles de conexión, la información del sistema, los contenedores, los servicios, los repositorios y el uso de recursos.

**Desplegar una aplicación:**
> «Despliega gitlab en mi máquina de staging»

El agente llama a `repo_up` con `name: "gitlab"` y `machine: "staging"`, lo que despliega el repositorio y devuelve éxito o fallo.

**Seguir un trabajo largo:**
> «Restaura la copia de seguridad de anoche de nextcloud»

El agente llama a `backup_restore`. Un comando que supera su ventana devuelve un identificador de trabajo, y el agente llama a `job_wait` (hasta 50 s por llamada) y a `job_logs` hasta que el trabajo termina.

**Depurar un servicio que falla:**
> «Mi nextcloud va lento, averigua qué pasa»

El agente llama a `machine_health`, después a `machine_containers` y `repo_logs`, y sugiere una solución.

## Seguridad

El servidor MCP local aplica dos capas de protección. Los límites del servidor remoto están en [Servidor remoto](#remote-server).

### Modo solo-fork (predeterminado)

De forma predeterminada, el servidor se ejecuta en **modo solo-fork**: las herramientas de escritura (`repo_up`, `repo_down`, `repo_delete`, `repo_exec`, `repo_push`, `repo_pull`) solo pueden operar sobre repositorios fork. Los agentes no pueden tocar los repositorios grand (originales). Por diseño.

> **Los secretos por repositorio son exclusivos de la CLI por diseño.** `repo_secret_set` y `repo_secret_unset` no se exponen como herramientas MCP de manera intencional. Las escrituras requieren una precondición `--current <valor-anterior>` (o `--rotate-secret` para confirmar una rotación no verificada), y esa ceremonia necesita supervisión humana. Los agentes que necesiten sugerir una rotación de secreto deben llamar a `repo_secret_get` para confirmar el hash, y luego transmitir al usuario el comando CLI correspondiente mediante el campo `next.options[].run` del envelope de error JSON. Consulta [Seguridad de agentes IA](/en/docs/ai-agents-safety#structured-next-action-hints) para ver el patrón completo, y [Repositorios § Secretos](/en/docs/repositories#secrets) para la guía dirigida al operador.

Para permitir que un agente modifique repositorios grand, exporta `REDIACC_ALLOW_GRAND_REPO` en tu terminal **antes de iniciar el agente que aloja el servidor MCP**:

```bash
export REDIACC_ALLOW_GRAND_REPO='gitlab'   # un repositorio
# o 'repo1,repo2,repo3' (los espacios alrededor de las entradas se ignoran), o '*' para todos los repositorios
claude   # o cursor, gemini, etc.
```

La anulación se verifica contra la ascendencia del proceso: solo cuenta cuando ya estaba presente en el entorno del propio proceso del agente, lo que significa que la exportaste antes de que el agente (y el servidor MCP que generó) iniciara. Un agente no puede concederse acceso a sí mismo configurando la variable a mitad de sesión. No hay intencionadamente ninguna flag de servidor para esto: una flag en los argumentos del servidor MCP no lleva prueba de quién la puso ahí, mientras que la verificación de ascendencia sí. El acceso a nivel de máquina (como `term connect <machine>` sin un repositorio) sigue requiriendo `*`; una lista de nombres de repositorios no lo desbloquea.

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

El servidor MCP local no mantiene estado. Cada llamada a una herramienta lanza `rdc` como proceso hijo aislado con las opciones `--output json --yes --quiet`. Esto significa:

- No hay fugas de estado entre llamadas a herramientas
- Utiliza tu configuración de `rdc` y claves SSH existentes
- Los errores en un comando no afectan a otros
