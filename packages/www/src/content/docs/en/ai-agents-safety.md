---
title: AI Agent Safety & Guardrails
description: >-
  How Rediacc's CLI keeps AI coding assistants from leaking secrets,
  overwriting credentials, or escalating privilege. Knowledge-gates,
  redaction, ancestry-verified overrides, and a hash-chained audit log.
category: Concepts
order: 35
language: en
---

When Claude Code, Cursor, Gemini CLI, Copilot CLI, or any other AI coding assistant drives `rdc`, the CLI treats it differently from a human at a keyboard. This page explains what the agent can do, what it cannot do, and how the guardrails hold even when the agent tries to talk itself out of them.

## Quick reference: what agents can and can't do

| Operation | Agent default | How to unblock for a specific use case |
|---|---|---|
| `rdc config show` (redacted) | ✅ allowed |  |
| `rdc config field get --pointer <pointer>` (redacted stub or digest) | ✅ allowed |  |
| `rdc config field get --pointer <pointer> --digest` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (public field) | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (sensitive field, **with correct `--current`**) | ✅ allowed |  |
| `rdc config edit --dump` (redacted JSONC) | ✅ allowed |  |
| `rdc config audit {log, tail, verify}` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (sensitive field, no `--current`) | 🔴 refused | Supply `--current "<old value>"` |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 refused | Use `--digest` instead |
| `rdc config show --reveal` | 🔴 refused | Use plain `rdc config show` |
| `rdc config edit` (interactive editor) | 🔴 refused | Human sets `REDIACC_ALLOW_CONFIG_EDIT=*` before launching the agent |
| `rdc config edit --apply <file>` | 🔴 refused | Same override |
| `rdc config field rotate --pointer <pointer>` | 🔴 refused | Same override; uses interactive confirmation |
| `rdc term connect -m <machine>` (direct machine SSH) | 🔴 refused | Fork a repo first and connect to the fork |

Everything an agent is refused from gets written to the audit log with `outcome: refused` and a reason.

## How agents are detected

The CLI treats a process as an agent when any of these are true:

- One of `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI` is set to `"1"`, or `CURSOR_TRACE_ID` is set at all.
- On Linux: any parent process up the ancestry chain has one of those variables in its environment (via `/proc/<pid>/environ`). Even if the agent unsets its own variables with `env -i` or a wrapper script, the parent chain still tells the CLI who started it.

Detection runs once per process and is cached. It cannot be disabled.

## The knowledge-gate model

Sensitive mutations follow the `passwd(1)` convention: to change a secret, prove you already knew it.

- You want to rotate an API token stored at `/credentials/cfDnsApiToken`?
- The CLI asks: "what's the current value?"
- The agent supplies the plaintext via `--current "$OLD"`. The CLI hashes `$OLD` with SHA-256 and compares against the digest of the currently-stored value. Match → write goes through. Mismatch → refused, audited.

The model is simple but closes three attack surfaces:

1. **Silent rotation**: an agent without prior access to `$OLD` cannot replace it with a value of its own.
2. **Exfiltration via probing**: the digest response never contains plaintext; even a compromised audit log shows `expected abc12345…, got deadbeef…`, not the underlying values.
3. **Accidental stepping on the user's config**: requires deliberate `--current` each time; no auto-overwrite on `set`.

### Worked example

```bash
# Discover the redaction stub's short digest (safe for agents).
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# Try to overwrite without proof: refused.
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current (or --rotate-secret)

# Supply the current plaintext: allowed.
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

If the agent never had `$OLD_CF_TOKEN`, it can't satisfy the precondition and the rotation is refused. The user who *does* have it can still do it either through the editor or by passing `--current` from their shell.

## Redaction by default

Every `rdc` command that reads sensitive state: `config show`, `config field get`, `config machine list`, `config edit --dump`: returns **redaction stubs** for secret fields, not plaintext:

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

The stub's 8-char hex suffix is the first 8 chars of `sha256(canonicalize(value))`: enough to distinguish two different values at a glance, not enough to reverse. An agent can use a stub to track whether a value has changed without ever seeing it.

`--reveal` unredacts for humans on an interactive TTY. Agents are refused regardless of TTY state. Each grant writes a `reveal_granted` audit entry; each refusal writes a `refused` entry with the actor's agent signals attached.

## The `REDIACC_ALLOW_CONFIG_EDIT` override

Some operations: the interactive editor, `--apply`, `field rotate`: exist for humans and have no agent-safe path. If you actively want an agent to do one of them, you set:

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'          # full bypass
# or
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/ssh/privateKey,/infra/cfDnsZoneId'
# (comma-separated scope globs: * wildcards allowed per segment)
```

…and the agent inherits it.

**Crucial detail**: the override must appear in a process **above** the agent in the ancestry chain. If the agent sets it in its own environment (or in a subshell it spawned), the CLI refuses and tells you so:

> `Interactive editor is blocked in agent environments (REDIACC_ALLOW_CONFIG_EDIT was set but ancestry verification failed: the override must be set by your shell, not by an agent).`

The effect: an agent can't talk its way past a guardrail by running `export REDIACC_ALLOW_CONFIG_EDIT='*'` mid-session. Only a parent process (you, in your terminal, before launching the agent) can open that door.

## Audit log

Every mutation, every refusal, every `--reveal` grant writes a JSONL line to `~/.config/rediacc/audit.log.jsonl` (mode `0600`, rotated at 10 MB). Each line is hash-chained: its `prevHash` field is `sha256("<previous line>")`. Tampering with any line breaks the chain on every following line.

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent without REDIACC_ALLOW_CONFIG_EDIT=*","prevHash":"sha256:abc1..."}
{"ts":"2026-04-21T10:03:05.220Z","actor":{"kind":"human"},"command":"config show --reveal","paths":[],"outcome":"reveal_granted","configId":"...","configVersion":48,"prevHash":"sha256:deac..."}
```

### Inspect

```bash
# List recent entries
rdc config audit log --since 24h

# Filter by pointer glob
rdc config audit log --path '/credentials/*'

# Only agent-originated entries
rdc config audit log --actor agent

# Stream new entries live (Ctrl+C to stop)
rdc config audit tail

# Verify the hash chain is intact
rdc config audit verify
# → "Chain integrity verified across 247 entries."
#   OR
# → "Chain broken at line 103: file has been tampered with or corrupted."
```

### What never appears in the audit log

- Plaintext secret values
- Passphrases, tokens, SSH keys
- The old/new values in a `--current` precondition mismatch (only the 8-char digest prefix)

The log is safe to share with a security reviewer or attach to a bug report.

## Limits of the behavioral model

The agent guardrails are **behavioral, not cryptographic**. A determined or prompted agent running as the same UID as the config file can always do `cat ~/.config/rediacc/rediacc.json` and read the plaintext, because the file is readable by the process.

For real cryptographic enforcement, use the [encrypted config store](/en/docs/config-storage): secrets live on the server side, each sensitive field carries a per-field HMAC commitment, and the account worker refuses writes whose `--current` precondition doesn't hash-match what it has stored. The server never sees the plaintext: zero-knowledge: but it does enforce the gate.

The local-file path is "easy path is safe". The remote-store path is "hard path is hard too".

## Quick recipes

### Let an agent rotate a single cloud token

```bash
# As you, before starting the agent:
export REDIACC_ALLOW_CONFIG_EDIT='/credentials/cfDnsApiToken'
claude-code              # or cursor, gemini, etc.
```

Now the agent can `config field rotate /credentials/cfDnsApiToken --new …` but still can't edit `/credentials/ssh/privateKey` or open the interactive editor.

### Let an agent do one broad config edit session

```bash
export REDIACC_ALLOW_CONFIG_EDIT='*'
claude-code
```

The agent can open `rdc config edit`, use `--reveal`, and run `field rotate`. Every action is still audit-logged with `actor.kind: agent` and the `CLAUDECODE` signal.

### Discover which fields an agent is allowed to touch

```bash
rdc config field list --sensitive --output json
```

Returns every pointer template, its kind (`secret` / `credential` / `pii` / `identifier`), and whether it's committed to the server-side HMAC envelope.

## See also

- [AI Agent Integration Overview](/en/docs/ai-agents-overview): the top-level tour
- [Claude Code setup](/en/docs/ai-agents-claude-code): integration template
- [JSON output envelope](/en/docs/ai-agents-json-output): machine-readable responses
- [Encrypted config store](/en/docs/config-storage): server-side cryptographic enforcement
- [Account security](/en/docs/account-security): operator-facing security posture
