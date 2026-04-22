---
title: Seguridad y salvaguardas para agentes de IA
description: 'Cómo la CLI de Rediacc evita que los asistentes de codificación con IA filtren secretos, sobreescriban credenciales o escalen privilegios: compuertas de conocimiento, redacción, anulaciones verificadas por ascendencia y un registro de auditoría encadenado por hash.'
category: Concepts
order: 35
language: es
sourceHash: "6a4f4ccd6ae806ee"
sourceCommit: "4bef9a170fb07db00a4ee2ef504aa27706bcd15a"
---

Cuando Claude Code, Cursor, Gemini CLI, Copilot CLI o cualquier otro asistente de codificación con IA maneja `rdc`, la CLI lo trata de forma diferente a un humano en el teclado. Esta página explica qué puede hacer el agente, qué no puede hacer y cómo las salvaguardas se mantienen incluso cuando el agente intenta sortearlas.

## Referencia rápida: qué pueden y no pueden hacer los agentes

| Operación | Comportamiento predeterminado del agente | Cómo desbloquear para un caso de uso específico |
|---|---|---|
| `rdc config show` (redactado) | ✅ allowed |  |
| `rdc config field get --pointer <pointer>` (stub redactado o digest) | ✅ allowed |  |
| `rdc config field get --pointer <pointer> --digest` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (campo público) | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (campo sensible, **con `--current` correcto**) | ✅ allowed |  |
| `rdc config edit --dump` (JSONC redactado) | ✅ allowed |  |
| `rdc config audit {log, tail, verify}` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (campo sensible, sin `--current`) | 🔴 refused | Proporcionar `--current "<valor anterior>"` |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 refused | Usar `--digest` en su lugar |
| `rdc config show --reveal` | 🔴 refused | Usar `rdc config show` sin opciones |
| `rdc config edit` (editor interactivo) | 🔴 refused | El humano establece `REDIACC_ALLOW_CONFIG_EDIT=*` antes de lanzar el agente |
| `rdc config edit --apply <file>` | 🔴 refused | La misma anulación |
| `rdc config field rotate --pointer <pointer>` | 🔴 refused | La misma anulación; usa confirmación interactiva |
| `rdc term connect -m <machine>` (SSH directo a la máquina) | 🔴 refused | Primero bifurcar un repositorio y conectarse al fork |

Todo lo que se rechaza a un agente se escribe en el registro de auditoría con `outcome: refused` y una razón.

## Cómo se detectan los agentes

La CLI trata un proceso como un agente cuando se cumple cualquiera de estas condiciones:

- Una de las variables `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI` está establecida en `"1"`, o `CURSOR_TRACE_ID` está establecida en absoluto.
- En Linux: cualquier proceso padre en la cadena de ascendencia tiene alguna de esas variables en su entorno (a través de `/proc/<pid>/environ`). Incluso si el agente elimina sus propias variables con `env -i` o un script envolvente, la cadena de padres sigue indicando a la CLI quién lo inició.

La detección se ejecuta una vez por proceso y se almacena en caché. No se puede deshabilitar.

## El modelo de compuerta de conocimiento

Las mutaciones sensibles siguen la convención `passwd(1)`: para cambiar un secreto, demuestra que ya lo conocías.

- ¿Quieres rotar un token de API almacenado en `/credentials/cfDnsApiToken`?
- La CLI pregunta: "¿cuál es el valor actual?"
- El agente proporciona el texto plano mediante `--current "$OLD"`. La CLI aplica SHA-256 a `$OLD` y lo compara con el digest del valor almacenado actualmente. Coincidencia → la escritura se realiza. Discrepancia → rechazado, auditado.

El modelo es simple pero cierra tres superficies de ataque:

1. **Rotación silenciosa**: un agente sin acceso previo a `$OLD` no puede reemplazarlo con un valor propio.
2. **Exfiltración mediante sondeo**: la respuesta del digest nunca contiene texto plano; incluso un registro de auditoría comprometido muestra `expected abc12345…, got deadbeef…`, no los valores subyacentes.
3. **Sobreescritura accidental de la configuración del usuario**: requiere un `--current` deliberado cada vez; sin sobreescritura automática en `set`.

### Ejemplo práctico

```bash
# Obtener el digest corto del stub de redacción (seguro para agentes).
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# Intentar sobrescribir sin prueba: rechazado.
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current (or --rotate-secret)

# Proporcionar el texto plano actual: permitido.
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

Si el agente nunca tuvo `$OLD_CF_TOKEN`, no puede satisfacer la precondición y la rotación se rechaza. El usuario que *sí* lo tiene puede hacerlo a través del editor o pasando `--current` desde su shell.

## Redacción por defecto

Cada comando `rdc` que lee estado sensible: `config show`, `config field get`, `config machine list`, `config edit --dump`: devuelve **stubs de redacción** para los campos secretos, no texto plano:

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

El sufijo hexadecimal de 8 caracteres del stub son los primeros 8 caracteres de `sha256(canonicalize(value))`: suficiente para distinguir dos valores diferentes de un vistazo, no suficiente para revertirlos. Un agente puede usar un stub para rastrear si un valor ha cambiado sin verlo nunca.

`--reveal` elimina la redacción para humanos en un TTY interactivo. Los agentes son rechazados independientemente del estado del TTY. Cada concesión escribe una entrada de auditoría `reveal_granted`; cada rechazo escribe una entrada `refused` con las señales de agente del actor adjuntas.

## La anulación `REDIACC_ALLOW_CONFIG_EDIT`

Algunas operaciones: el editor interactivo, `--apply`, `field rotate`: existen para humanos y no tienen una ruta segura para agentes. Si activamente quieres que un agente haga una de ellas, estableces:

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'          # omisión completa
# o
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/ssh/privateKey,/infra/cfDnsZoneId'
# (globs de alcance separados por comas: se permiten comodines * por segmento)
```

…y el agente lo hereda.

**Detalle crucial**: la anulación debe aparecer en un proceso **por encima** del agente en la cadena de ascendencia. Si el agente la establece en su propio entorno (o en una subshell que generó), la CLI rechaza y te lo indica:

> `Interactive editor is blocked in agent environments (REDIACC_ALLOW_CONFIG_EDIT was set but ancestry verification failed: the override must be set by your shell, not by an agent).`

El efecto: un agente no puede eludir una salvaguarda ejecutando `export REDIACC_ALLOW_CONFIG_EDIT='*'` a mitad de sesión. Solo un proceso padre (tú, en tu terminal, antes de lanzar el agente) puede abrir esa puerta.

## Registro de auditoría

Cada mutación, cada rechazo, cada concesión de `--reveal` escribe una línea JSONL en `~/.config/rediacc/audit.log.jsonl` (modo `0600`, rotado a los 10 MB). Cada línea está encadenada por hash: su campo `prevHash` es `sha256("<línea anterior>")`. Manipular cualquier línea rompe la cadena en todas las líneas siguientes.

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent without REDIACC_ALLOW_CONFIG_EDIT=*","prevHash":"sha256:abc1..."}
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

Para una aplicación criptográfica real, usa el [almacén de configuración cifrado](/es/docs/config-storage): los secretos viven en el lado del servidor, cada campo sensible lleva un compromiso HMAC por campo, y el account worker rechaza escrituras cuya precondición `--current` no coincida por hash con lo que tiene almacenado. El servidor nunca ve el texto plano: zero-knowledge: pero sí aplica la compuerta.

La ruta de archivo local es "el camino fácil es seguro". La ruta del almacén remoto es "el camino difícil también es difícil".

## Recetas rápidas

### Permitir que un agente rote un único token de nube

```bash
# Como tú, antes de iniciar el agente:
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/cfDnsApiToken'
claude-code              # o cursor, gemini, etc.
```

Ahora el agente puede ejecutar `config field rotate /credentials/cfDnsApiToken --new …` pero sigue sin poder editar `/credentials/ssh/privateKey` ni abrir el editor interactivo.

### Permitir que un agente realice una sesión amplia de edición de configuración

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'
claude-code
```

El agente puede abrir `rdc config edit`, usar `--reveal` y ejecutar `field rotate`. Cada acción sigue registrándose en el log de auditoría con `actor.kind: agent` y la señal `CLAUDECODE`.

### Descubrir qué campos puede tocar un agente

```bash
rdc config field list --sensitive --output json
```

Devuelve cada plantilla de puntero, su tipo (`secret` / `credential` / `pii` / `identifier`) y si está comprometida con el sobre HMAC del lado del servidor.

## Véase también

- [Descripción general de integración de agentes de IA](/es/docs/ai-agents-overview): el recorrido general
- [Configuración de Claude Code](/es/docs/ai-agents-claude-code): plantilla de integración
- [Sobre de salida JSON](/es/docs/ai-agents-json-output): respuestas legibles por máquina
- [Almacén de configuración cifrado](/es/docs/config-storage): aplicación criptográfica del lado del servidor
- [Seguridad de la cuenta](/es/docs/account-security): postura de seguridad del operador
