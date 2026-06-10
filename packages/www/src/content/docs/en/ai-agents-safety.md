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

So you're pointing an AI coding assistant at your infrastructure. When Claude Code, Cursor, Gemini CLI, Copilot CLI, or anything similar drives `rdc`, the CLI detects it and applies a different ruleset than a human at a keyboard. This page covers what the agent can and can't do, and how the guardrails hold even when it tries to talk its way out of them.

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

Every refusal gets written to the audit log with `outcome: refused` and a reason.

## How agents are detected

The CLI treats a process as an agent when any of these are true:

- One of `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI` is set to `"1"`, or `CURSOR_TRACE_ID` is set at all.
- On Linux: any parent process up the ancestry chain has one of those variables in its environment (via `/proc/<pid>/environ`). Even if the agent unsets its own variables with `env -i` or a wrapper script, the parent chain still tells the CLI who started it.

Detection runs once per process and is cached. It cannot be disabled.

## The knowledge-gate model

Sensitive mutations follow the `passwd(1)` convention: to change a secret, prove you already knew it. **Symmetric for humans and agents**. Both go through the same gate. There is no "I'm at the keyboard" bypass.

- You want to rotate an API token stored at `/credentials/cfDnsApiToken`?
- The CLI asks: "what's the current value?"
- The agent (or human) supplies the plaintext via `--current "$OLD"`. The CLI hashes `$OLD` with SHA-256 and compares against the digest of the currently-stored value. Match → write goes through. Mismatch → refused, audited.
- To rotate without verifying the prior value, pass `--rotate-secret` (mutually exclusive with `--current`). This is loudly audited as a rotation.

The model closes three attack surfaces:

1. **Silent rotation**: a caller (agent or human) without prior access to `$OLD` cannot replace it with a value of its own.
2. **Exfiltration via probing**: the digest response never contains plaintext; even a compromised audit log shows `expected abc12345…, got deadbeef…`, not the underlying values.
3. **Accidental stepping on production config**: requires deliberate `--current` each time, even at a TTY. Catches the "I meant to set STRIPE_TEST but I'm in the prod shell" mistake.

### Structured next-action hints

When the precondition fails, the JSON envelope (`--output json`) carries a structured `errors[].next` field telling agents exactly what to suggest the human do:

```json
{
  "errors": [{
    "code": "PRECONDITION_MISMATCH",
    "message": "...",
    "next": {
      "summary": "Provide the current value or acknowledge rotation.",
      "options": [
        { "description": "Re-read current digest, then retry with --current",
          "run": "rdc repo secret get --name mail --key STRIPE_KEY" },
        { "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set --name mail --key STRIPE_KEY --value <new> --mode file --rotate-secret" }
      ]
    }
  }]
}
```

**Agents should relay `next.options[].run` verbatim to the human rather than synthesizing their own commands.** This avoids the "agent invents a command that doesn't exist" failure mode and keeps the operator in control of the actual action.

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

## Platform support: how the override is verified on each OS

`REDIACC_ALLOW_CONFIG_EDIT` and `REDIACC_ALLOW_GRAND_REPO` both rely on ancestry verification to prove the override was set by you and not injected by the agent. The verification works on Linux, macOS, and Windows, but the witness it reads differs per platform, and so does the strength of the guarantee:

| Platform | Witness | Strength |
|---|---|---|
| Linux | `/proc/<pid>/environ` for every process up the chain | Exec-time snapshot, kernel-served. A process cannot retroactively edit what it was started with. |
| macOS | `kern.procargs2` sysctl, read by a small helper that ships inside `rdc` | Same exec-time snapshot property as Linux. Readable for your own processes without root. |
| Windows | The live environment block of each ancestor process (PEB), read by the same helper, with PID-reuse guards | Weaker: Windows keeps no exec-time snapshot, so the check reads current memory. Ancestors still can't be rewritten by anything an agent normally runs, but the witness is not kernel-frozen the way it is on Linux and macOS. |

On macOS and Windows the CLI spawns its bundled `renet` binary to do the reading; the helper reports which of the watched variables each ancestor carries, and all decision logic stays in the CLI. If the helper is missing, outdated, or fails for any reason, the CLI cannot verify the override and **fails closed**: the override is rejected and the error says verification was unavailable, not that you did something wrong. A working installation never shows that message; reinstalling `rdc` restores the helper.

What stays true on every platform: the override must already be present in the environment of the agent process when it starts. Export it in your terminal, then launch the agent. An agent that sets the variable mid-session is refused.

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

For real cryptographic enforcement, use the [encrypted config store](/en/docs/config-storage): secrets live on the server side, each sensitive field carries a per-field HMAC commitment, and the account worker refuses writes whose `--current` precondition doesn't hash-match what it has stored. The server never sees the plaintext (zero-knowledge), but it does enforce the gate.

Local files: the easy path is the safe one. Remote store: the bypass route is cryptographically hard too.

## What Rediacc does not isolate

The agent guardrails on this page protect Rediacc's own infrastructure: the config file, the per-repo Docker daemon, the LUKS-encrypted repository data, the scoped SSH sandbox. They do not protect external services that your repository holds credentials for.

A repository fork is a BTRFS reflink of the parent's volume. Whatever lives on disk in the parent is byte-identical in the fork: code, data, and `.env` files alike. If your repository contains a `STRIPE_LIVE_KEY`, an `AWS_ACCESS_KEY_ID`, a Railway API token, or any other long-lived credential for a third-party service, the fork inherits it. An agent operating in the fork's sandbox can read that file, exfiltrate the value, or use it to call the third-party API. The third-party service has no way to know the call came from a fork instead of production.

This is the shared-responsibility line:

| Boundary | Owner |
|---|---|
| Repository data, mount namespace, Docker scope, agent guards, audit log, deploy-time secret injection | Rediacc |
| Application code that uses those secrets, and any credentials baked into the image at build time | Repository developer |

The primary mitigation is built in: **[per-repo secrets](/en/docs/repositories#secrets)** are stored in a separate plane from the encrypted repository image and are not copied across the fork boundary. A fork's containers boot with an empty secrets map and identify themselves as a different external principal than the parent. Set them with `rdc repo secret set` (env-mode for compose interpolation, file-mode for tmpfs `secrets:` blocks). The mutation gate is symmetric. Humans and agents alike must supply `--current` (passwd-style precondition) or `--rotate-secret` (audited rotation) to overwrite or delete an existing value.

**Cross-repo isolation is enforced.** A malicious or careless compose file in repo B cannot reference repo A's secrets directory. Renet's compose validator hard-rejects any `secrets: file:`, `configs: file:`, or `env_file:` path that points outside the current repo's `${REDIACC_NETWORK_ID}` directory, and the rejection is NOT overridable by `--unsafe`. Defense-in-depth: the Landlock sandbox around the Rediaccfile bash subprocess scopes filesystem reads to the current network's secrets directory only, so a `cat /var/run/rediacc/secrets/<other>/X` from a malicious Rediaccfile fails with EACCES at the kernel layer.

Two additional patterns close edge cases:

1. **Do not bake production credentials into the repository's filesystem itself.** A `.env` file committed into the image, or a credential persisted into a volume during `up()`, is reflinked into the fork. The per-repo secrets feature only protects values you keep in the secrets plane. It cannot retroactively protect bytes that already live inside the LUKS image. For existing repos with baked-in `.env` files, lift them into per-repo secrets manually.
2. **Constrain the fork's outbound network with eBPF egress filtering** so the fork can only reach localhost and explicit sandbox endpoints. Rediacc's per-repo network isolation is the foundation; per-fork egress allowlists are not built today, but the path is open.

Rediacc handles the deploy-time injection, the cross-fork isolation, and the cross-repo isolation. The "don't bake it into the image" half is on you.

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
