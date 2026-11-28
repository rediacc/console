---
title: Seguridad y salvaguardas para agentes de IA
description: >-
  Cómo Rediacc evita que los asistentes de programación con IA filtren secretos,
  sobrescriban credenciales o escalen privilegios. Una sola decisión para cada
  superficie, aceptación explícita Y techo de política, compuertas de
  conocimiento, redacción y un registro de auditoría encadenado por hash por organización y día en el servidor, y en un archivo local para la CLI.
category: Concepts
tags:
  - ai-agents
  - security
subcategory: ai-agents
order: 35
language: es
sourceHash: "43350a2e682cebcc"
sourceCommit: "cc655e698ed2c42faef5311e268425c04997f243"
---

Así que estás apuntando un asistente de codificación con IA a tu infraestructura. Cuando Claude Code, Cursor, Gemini CLI, Copilot CLI o cualquier otro asistente similar maneja `rdc`, la CLI lo detecta y aplica un conjunto de reglas diferente al de un humano en el teclado. Esta página explica qué puede hacer el agente, qué no puede hacer y cómo las salvaguardas se mantienen incluso cuando el agente intenta sortearlas.

## Referencia rápida: qué pueden y no pueden hacer los agentes

| Operación | Comportamiento predeterminado del agente | Cómo desbloquear para un caso de uso específico |
|---|---|---|
| `rdc config show` (redactado) | ✅ allowed |  |
| `rdc config field get --pointer <pointer>` (stub redactado o digest) | ✅ allowed |  |
| `rdc config field get --pointer <pointer> --digest` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (campo público) | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (campo sensible, **con `--current` correcto**) | ✅ allowed |  |
| `rdc config edit --dump --redacted` (JSONC redactado) | ✅ allowed |  |
| `rdc config audit {log, tail, verify}` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (campo sensible, sin `--current`) | 🔴 refused | Proporcionar `--current "<valor anterior>"` |
| `rdc repo secret set <repo> --rotate-secret` (rotación sin `--current`) | 🔴 refused | Proporcionar `--current`, o que un humano haga la rotación en un terminal |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 refused | Usar `--digest` en su lugar |
| `rdc config show --reveal` | 🔴 refused | Usar `rdc config show` sin opciones |
| `rdc config edit` (editor interactivo) | 🔴 refused, sin anulación | Inspeccionar con `--dump --redacted` y cambiar un campo con `config field set --current` |
| `rdc config edit --apply <file>` | 🔴 refused, sin anulación | Igual; un humano en un terminal aplica las ediciones del documento completo |
| `rdc config edit --reveal` | 🔴 refused, sin anulación | Igual |
| `rdc config field rotate --pointer <pointer>` | 🔴 refused | Un humano lo ejecuta en un terminal interactivo |
| Cambiar un repositorio grand (producción) | 🔴 refused | Aceptación explícita de un humano para ese repositorio, dentro de una política que permita cambios en repositorios grand ([más abajo](#one-decision-opt-in-and-policy-ceiling)) |
| Operaciones de ciclo de vida de clústeres o datastores | 🔴 refused | Aceptación explícita de un humano para ese clúster, dentro de una política que permita operaciones de clúster |
| `rdc term connect <machine>` (SSH directo a la máquina) | 🔴 refused | Primero bifurcar un repositorio y conectarse al fork |

Todo lo que se rechaza a un agente se escribe en el registro de auditoría con `outcome: refused` y una razón. La edición del documento de configuración completo no tiene ningún camino para un agente: la configuración contiene la credencial LUKS de cada repositorio, y un agente que pudiera reescribirla también podría borrar una credencial sin la cual el volumen cifrado no se puede abrir.

## Cómo se detectan los agentes

La CLI trata un proceso como un agente cuando se cumple cualquiera de estas condiciones:

- Una de las variables `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI` está establecida en `"1"`, o `CURSOR_TRACE_ID` está establecida en absoluto.
- En Linux: cualquier proceso padre en la cadena de ascendencia tiene alguna de esas variables en su entorno (a través de `/proc/<pid>/environ`). Incluso si el agente elimina sus propias variables con `env -i` o un script envolvente, la cadena de padres sigue indicando a la CLI quién lo inició.

La detección se ejecuta una vez por proceso y se almacena en caché. No se puede desactivar. Una concesión de MCP remoto marca sus llamadas como llamadas de agente en el ejecutor, sin necesidad de detección.

## Una sola decisión: aceptación explícita Y techo de política

Toda superficie que ejecuta un comando `rdc` (la CLI, el servidor MCP local, el servidor MCP remoto, `rdc --proxy` y la consola web) consulta la misma función de decisión, de modo que todas rechazan y permiten lo mismo. Aplica dos condiciones, y un agente solo actúa donde se cumplen ambas:

1. **El techo de política.** La política de la organización, restringida por la política del equipo, decide qué comandos, máquinas y repositorios puede usar quien llama, y si se permiten en absoluto los cambios en repositorios grand (`allowGrandRepos`) y las operaciones de clúster (`allowClusterOps`). Una configuración sin registro de política recurre a un valor por defecto según el rol: los propietarios y administradores pueden actuar, los miembros no. La política es un registro sellado aparte que solo escriben propietarios y administradores ([Modelo de seguridad](/es/docs/security-model#policy)); ningún agente ni comando de la CLI puede editarla.
2. **La aceptación explícita del humano.** Dentro del techo, un agente sigue necesitando que un humano nombre el repositorio grand o el clúster que puede cambiar:
   - **Agentes locales** (CLI y MCP local): el humano exporta `REDIACC_ALLOW_GRAND_REPO` (nombres de repositorio, o `*`) o `REDIACC_ALLOW_CLUSTER_OPS` (nombres de clúster, o `*`) en el terminal antes de iniciar el agente. La CLI comprueba la ascendencia de procesos, así que una variable que el agente define a mitad de sesión no cuenta ([cómo se comprueba en cada sistema operativo](#how-a-local-opt-in-is-verified-on-each-os)).
   - **Agentes remotos** (MCP remoto): las aceptaciones forman parte de la concesión que el humano crea en la interfaz de la cuenta ([Servidor remoto](/es/docs/ai-agents-mcp#remote-server)).

Una aceptación explícita nunca amplía el techo: un repositorio que la política cierra sigue cerrado, diga lo que diga el entorno o la concesión. Los forks no necesitan aceptación. Un repositorio que la CLI no puede identificar cuenta como grand.

**Los cambios destructivos preguntan primero.** Cuando un agente está autorizado para un cambio destructivo en un repositorio grand (por ejemplo `repo delete`), la respuesta es `needs_confirmation`. Un cliente MCP muestra al usuario un aviso de confirmación; un cliente que no lo tiene recibe un argumento `confirm` que devuelve tras preguntar al usuario. En la CLI, el humano vuelve a ejecutar el comando con `--confirm-grand <repo>`.

Cada respuesta lleva un código estable (`POLICY_DENIED`, `GRAND_REPO_DENIED`, `CLUSTER_OPS_DENIED`, `AGENT_OPT_IN_MISSING`, `FORK_BLOCKED`, `AGENT_BLOCKED`, `CONFIRMATION_REQUIRED`), de modo que un script o un agente se guía por el código y no por el mensaje ([Salida JSON](/es/docs/ai-agents-json-output)).

## El modelo de compuerta de conocimiento

Las mutaciones sensibles siguen la convención `passwd(1)`: para cambiar un secreto, demuestra que ya lo conocías. **Simétrico para humanos y agentes**. Ambos pasan por la misma compuerta. No existe ningún atajo por estar "en el teclado".

- ¿Quieres rotar un token de API almacenado en `/credentials/cfDnsApiToken`?
- La CLI pregunta: "¿cuál es el valor actual?"
- El agente (o el humano) proporciona el texto plano mediante `--current "$OLD"`. La CLI aplica SHA-256 a `$OLD` y lo compara con el digest del valor almacenado actualmente. Coincidencia → la escritura se realiza. Discrepancia → rechazado, auditado.
- Para rotar sin verificar el valor anterior, pasa `--rotate-secret` (mutuamente excluyente con `--current`). Se audita de forma explícita como rotación y solo cuenta para un humano en un terminal interactivo: un agente, o un script sin terminal en stdin, sigue necesitando `--current`.

El modelo cierra tres superficies de ataque:

1. **Rotación silenciosa**: un llamante (agente o humano) sin acceso previo a `$OLD` no puede reemplazarlo con un valor propio.
2. **Exfiltración mediante sondeo**: la respuesta del digest nunca contiene texto plano; incluso un registro de auditoría comprometido muestra `expected abc12345…, got deadbeef…`, no los valores subyacentes.
3. **Sobreescritura accidental de la configuración de producción**: requiere un `--current` deliberado cada vez, incluso desde un TTY. Detecta el error de "quería establecer STRIPE_TEST pero estoy en el shell de producción".

### Sugerencias de próxima acción estructuradas

Cuando la precondición falla, el sobre JSON (`--output json`) incluye un campo estructurado `errors[].next` que indica a los agentes exactamente qué sugerir al humano:

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "...",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        { "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get mail --key STRIPE_KEY" },
        { "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set mail --key STRIPE_KEY --value <new> --mode file --rotate-secret" }
      ]
    }
  }]
}
```

**Los agentes deben transmitir `next.options[].run` literalmente al humano en lugar de inventar sus propios comandos.** Así se evita el fallo de que el agente invente un comando que no existe, y el operador conserva el control de la acción real. La opción de rotación es para que el humano la ejecute en un terminal; al propio agente se le rechaza.

### Ejemplo práctico

```bash
# Obtener el digest corto del stub de redacción (seguro para agentes).
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# Intentar sobrescribir sin prueba: rechazado.
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current

# Proporcionar el texto plano actual: permitido.
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

Si el agente nunca tuvo `$OLD_CF_TOKEN`, no puede satisfacer la precondición y la rotación se rechaza. Quien sí tiene el valor puede hacerla igualmente: pasando `--current` desde su shell, o con `rdc config field rotate` en un terminal interactivo.

## Redacción por defecto

Cada comando `rdc` que lee estado sensible: `config show`, `config field get`, `config machine list`, `config edit --dump --redacted`: devuelve **stubs de redacción** para los campos secretos, no texto plano:

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

El sufijo hexadecimal de 8 caracteres del stub son los primeros 8 caracteres de `sha256(canonicalize(value))`: suficiente para distinguir dos valores diferentes de un vistazo, no suficiente para revertirlos. Un agente puede usar un stub para rastrear si un valor ha cambiado sin verlo nunca.

`--reveal` elimina la redacción para humanos en un TTY interactivo. Los agentes son rechazados independientemente del estado del TTY. Cada concesión escribe una entrada de auditoría `reveal_granted`; cada rechazo escribe una entrada `refused` con las señales de agente del actor adjuntas.

## Cómo se verifica una aceptación explícita local en cada sistema operativo

`REDIACC_ALLOW_GRAND_REPO` y `REDIACC_ALLOW_CLUSTER_OPS` se basan ambas en la verificación de ascendencia para demostrar que la aceptación la estableció el humano y no la inyectó el agente. La verificación funciona en Linux, macOS y Windows, pero el testigo que lee difiere según la plataforma, y también la solidez de la garantía:

| Plataforma | Testigo | Solidez |
|---|---|---|
| Linux | `/proc/<pid>/environ` para cada proceso en la cadena | Instantánea en el tiempo de ejecución, servida por el kernel. Un proceso no puede editar retroactivamente con qué se inició. |
| macOS | Sysctl `kern.procargs2`, leído por un pequeño ayudante que se incluye dentro de `rdc` | La misma propiedad de instantánea en el tiempo de ejecución que Linux. Legible para tus propios procesos sin root. |
| Windows | El bloque de entorno en vivo de cada proceso ancestro (PEB), leído por el mismo ayudante, con guardias contra reutilización de PID | Más débil: Windows no mantiene una instantánea en el tiempo de ejecución, así que la verificación lee la memoria actual. Los ancestros todavía no pueden ser reescritos por nada que un agente normalmente ejecute, pero el testigo no está congelado por el kernel como lo está en Linux y macOS. |

En macOS y Windows la CLI lanza su binario `renet` incluido para hacer la lectura; el helper informa de cuáles de las variables vigiladas lleva cada ancestro, y toda la lógica de decisión permanece en la CLI. Si el helper falta, está desactualizado o falla por cualquier motivo, la CLI no puede verificar la aceptación y **falla en modo seguro**: la aceptación se rechaza y el error indica que la verificación no estaba disponible, no que se haya hecho algo mal. Una instalación que funciona nunca muestra ese mensaje; reinstalar `rdc` restaura el helper.

Lo que se mantiene en todas las plataformas: la aceptación ya debe estar presente en el entorno del proceso del agente cuando este arranca. Se exporta en el terminal y después se lanza el agente. Un agente que define la variable a mitad de sesión es rechazado.

## Registro de auditoría

Cada mutación, cada rechazo, cada concesión de `--reveal` escribe una línea JSONL en `~/.config/rediacc/audit.log.jsonl` (modo `0600`, rotado a los 10 MB). Cada línea está encadenada por hash: su campo `prevHash` es `sha256("<línea anterior>")`. Manipular cualquier línea rompe la cadena en todas las líneas siguientes.

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent environment","prevHash":"sha256:abc1..."}
{"ts":"2026-04-21T10:03:05.220Z","actor":{"kind":"human"},"command":"config show --reveal","paths":[],"outcome":"reveal_granted","configId":"...","configVersion":48,"prevHash":"sha256:deac..."}
```

### Inspección

```bash
# Listar entradas recientes
rdc config audit log --since 24h

# Filtrar por glob de puntero
rdc config audit log --path '/credentials/*'

# Solo entradas originadas por agentes
rdc config audit log --actor agent

# Transmitir nuevas entradas en vivo (Ctrl+C para detener)
rdc config audit tail

# Verificar que la cadena de hash está intacta
rdc config audit verify
# → "Chain integrity verified across 247 entries."
#   O
# → "Chain broken at line 103: file has been tampered with or corrupted."
```

### Qué nunca aparece en el registro de auditoría

- Valores de secretos en texto plano
- Contraseñas, tokens, claves SSH
- Los valores anterior/nuevo en un fallo de precondición `--current` (solo el prefijo de digest de 8 caracteres)

El registro es seguro para compartir con un revisor de seguridad o adjuntar a un informe de error.

## Límites del modelo de comportamiento

Las salvaguardas del agente son **de comportamiento, no criptográficas**. Un agente decidido o dirigido que se ejecuta bajo el mismo UID que el archivo de configuración siempre puede hacer `cat ~/.config/rediacc/rediacc.json` y leer el texto plano, porque el proceso puede leer el archivo.

Para una aplicación criptográfica real, usa el [almacén de configuración cifrado](/es/docs/config-storage): los secretos viven en el lado del servidor, cada campo sensible lleva un compromiso HMAC por campo, y el account worker rechaza escrituras cuya precondición `--current` no coincida por hash con lo que tiene almacenado. El servidor nunca ve el texto plano (zero-knowledge), pero sí aplica la compuerta.

Archivos locales: el camino fácil es el seguro. Almacén remoto: la ruta de evasión también es criptográficamente difícil.

## Lo que Rediacc no aísla

Las salvaguardas para agentes de esta página protegen la propia infraestructura de Rediacc: el archivo de configuración, el daemon Docker por repositorio, los datos del repositorio cifrados con LUKS, el sandbox SSH limitado. No protegen los servicios externos para los que tu repositorio guarda credenciales.

Una bifurcación de repositorio es un reflink BTRFS del volumen del padre. Lo que vive en disco en el padre es idéntico byte a byte en la bifurcación: código, datos y archivos `.env` por igual. Si tu repositorio contiene un `STRIPE_LIVE_KEY`, un `AWS_ACCESS_KEY_ID`, un token de API de Railway o cualquier otra credencial de larga duración para un servicio de terceros, la bifurcación la hereda. Un agente que opera en el sandbox de la bifurcación puede leer ese archivo, exfiltrar el valor o usarlo para llamar a la API del tercero. El servicio de terceros no tiene forma de saber que la llamada vino de una bifurcación en lugar de producción.

Esta es la línea de responsabilidad compartida:

| Frontera | Responsable |
|---|---|
| Datos del repositorio, espacio de nombres de montaje, alcance de Docker, salvaguardas del agente, registro de auditoría, inyección de secretos en el momento del despliegue | Rediacc |
| El código de la aplicación que usa esos secretos, y cualquier credencial integrada en la imagen en el momento de la compilación | Desarrollador del repositorio |

La mitigación principal está integrada: los **[secretos por repositorio](/es/docs/repositories#secrets)** se almacenan en un plano separado de la imagen del repositorio cifrado y no se copian a través del límite del fork. Los contenedores de un fork arrancan con un mapa de secretos vacío y se identifican como un principal externo diferente al del padre. Configúralos con `rdc repo secret set` (modo env para interpolación de compose, modo file para bloques tmpfs `secrets:`). La compuerta de mutación es simétrica. Tanto humanos como agentes deben proporcionar `--current` (precondición estilo passwd) para sobrescribir o eliminar un valor existente; `--rotate-secret` (rotación auditada) es la alternativa para un humano en un terminal.

**El aislamiento entre repositorios está impuesto.** Un compose file malicioso o descuidado en el repositorio B no puede referenciar el directorio de secretos del repositorio A. El validador de compose de renet rechaza terminantemente cualquier ruta `secrets: file:`, `configs: file:` o `env_file:` que apunte fuera del directorio `${REDIACC_NETWORK_ID}` del repositorio actual, y ese rechazo NO es anulable con `--unsafe`. Defensa en profundidad: el sandbox Landlock alrededor del subproceso bash del Rediaccfile limita las lecturas del sistema de archivos únicamente al directorio de secretos de la red actual, por lo que un `cat /var/run/rediacc/net-<other>/secrets/X` desde un Rediaccfile malicioso falla con EACCES a nivel de kernel. Lo mismo vale para la API de Docker: el socket de Docker de cada repositorio lo sirve un proxy de políticas de renet que rechaza con un `403` `--privileged`, `pid`, `ipc` y `uts` del host, las solicitudes de dispositivos y los binds que alcanzan el runtime o los datos de otro repositorio, de modo que un contenedor con `${DOCKER_SOCKET}` no puede usar la API para llegar a otro repositorio, y no solo se comprueba un compose file. Solo el operador puede ampliar la regla de binds, para directorios del host concretos, con una concesión propiedad de root en la que ningún contenedor puede escribir.

Dos patrones adicionales cierran los casos extremos:

1. **No integres credenciales de producción en el sistema de archivos del repositorio.** Un archivo `.env` incorporado en la imagen, o una credencial persistida en un volumen durante `up()`, se reflinks a la bifurcación. La función de secretos por repositorio solo protege los valores que guardas en el plano de secretos. No puede proteger retroactivamente los bytes que ya viven dentro de la imagen LUKS. Para repositorios existentes con archivos `.env` integrados, llévalos manualmente a secretos por repositorio.
2. **Restringe la red saliente del fork con filtrado de egreso eBPF** para que el fork solo pueda alcanzar localhost y endpoints de sandbox explícitos. El aislamiento de red por repositorio de Rediacc es la base; las listas de permitidos de egreso por fork no están disponibles hoy, pero el camino está abierto.

Rediacc gestiona la inyección en el momento del despliegue, el aislamiento entre forks y el aislamiento entre repositorios. La parte de "no lo integres en la imagen" es tu responsabilidad.

## Recetas rápidas

### Dejar que un agente trabaje en un repositorio grand

```bash
# Como humano, antes de iniciar el agente:
export REDIACC_ALLOW_GRAND_REPO='gitlab'
claude              # o cursor, gemini, etc.
```

El agente ya puede cambiar `gitlab`, donde la política permite cambios en repositorios grand, y ningún otro repositorio grand. Un cambio destructivo, como `repo delete gitlab`, sigue pidiendo confirmación.

### Rotar un token de la nube sin conocer el valor anterior

```bash
# Como humano, en un terminal interactivo:
rdc config field rotate --pointer /credentials/cfDnsApiToken --new "$NEW_CF_TOKEN"
```

La rotación sin `--current` queda en manos del humano. Un agente que conoce el valor actual usa en su lugar `rdc config field set --current`.

### Descubrir qué campos puede tocar un agente

```bash
rdc config field list --sensitive --output json
```

Devuelve cada plantilla de puntero, su tipo (`secret` / `credential` / `pii` / `identifier`) y si está comprometida con el sobre HMAC del lado del servidor.

## Véase también

- [Descripción general de integración de agentes de IA](/es/docs/ai-agents-overview): el recorrido general
- [Servidor MCP](/es/docs/ai-agents-mcp): MCP local y remoto, concesiones y sus aceptaciones explícitas
- [Modelo de seguridad](/es/docs/security-model): el registro de política y quién puede escribirlo
- [Configuración de Claude Code](/es/docs/ai-agents-claude-code): plantilla de integración
- [Sobre de salida JSON](/es/docs/ai-agents-json-output): respuestas legibles por máquina
- [Almacén de configuración cifrado](/es/docs/config-storage): aplicación criptográfica del lado del servidor
- [Seguridad de la cuenta](/es/docs/account-security): postura de seguridad del operador
