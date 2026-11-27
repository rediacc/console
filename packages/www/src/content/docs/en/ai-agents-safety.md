---
title: AI Agent Safety & Guardrails
description: >-
  How Rediacc keeps AI coding assistants from leaking secrets,
  overwriting credentials, or escalating privilege. One decision for every
  surface, opt-in AND policy ceiling, knowledge-gates, redaction, and a
  hash-chained audit log.
category: Concepts
tags:
  - ai-agents
  - security
subcategory: ai-agents
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
| `rdc config edit --dump --redacted` (redacted JSONC) | ✅ allowed |  |
| `rdc config audit {log, tail, verify}` | ✅ allowed |  |
| `rdc config field set --pointer <pointer>` (sensitive field, no `--current`) | 🔴 refused | Supply `--current "<old value>"` |
| `rdc repo secret set <repo> --rotate-secret` (rotation without `--current`) | 🔴 refused | Supply `--current`, or a human runs the rotation at a terminal |
| `rdc config field get --pointer <pointer> --reveal` | 🔴 refused | Use `--digest` instead |
| `rdc config show --reveal` | 🔴 refused | Use plain `rdc config show` |
| `rdc config edit` (interactive editor) | 🔴 refused, no override | Inspect with `--dump --redacted`, change one field with `config field set --current` |
| `rdc config edit --apply <file>` | 🔴 refused, no override | Same; a human at a terminal applies whole-document edits |
| `rdc config edit --reveal` | 🔴 refused, no override | Same |
| `rdc config field rotate --pointer <pointer>` | 🔴 refused | A human runs it at an interactive terminal |
| Change a grand (production) repository | 🔴 refused | A human opt-in for that repo, inside a policy that allows grand-repo changes ([below](#one-decision-opt-in-and-policy-ceiling)) |
| Cluster or datastore lifecycle operations | 🔴 refused | A human opt-in for that cluster, inside a policy that allows cluster operations |
| `rdc term connect <machine>` (direct machine SSH) | 🔴 refused | Fork a repo first and connect to the fork |

Every refusal gets written to the audit log with `outcome: refused` and a reason. A whole-document config edit has no agent path at all: the config carries every repository's LUKS credential, and an agent that could rewrite it could also delete a credential that the encrypted volume cannot be opened without.

## How agents are detected

The CLI treats a process as an agent when any of these are true:

- One of `REDIACC_AGENT`, `CLAUDECODE`, `GEMINI_CLI`, `COPILOT_CLI` is set to `"1"`, or `CURSOR_TRACE_ID` is set at all.
- On Linux: any parent process up the ancestry chain has one of those variables in its environment (via `/proc/<pid>/environ`). Even if the agent unsets its own variables with `env -i` or a wrapper script, the parent chain still tells the CLI who started it.

Detection runs once per process and is cached. It cannot be disabled. A remote MCP grant marks its calls as agent calls on the executor, with no detection needed.

## One decision: opt-in AND policy ceiling

Every surface that runs an `rdc` command (the CLI, the local MCP server, the remote MCP server, `rdc --proxy` and the web console) asks the same decision function, so they refuse and allow the same things. It applies two conditions, and an agent acts only where both hold:

1. **The policy ceiling.** The organization policy, narrowed by the team policy, decides which commands, machines and repositories a caller may use, and whether grand-repository changes (`allowGrandRepos`) and cluster operations (`allowClusterOps`) are allowed at all. A config with no policy record falls back to a default by role: owners and admins may act, members may not. The policy is a separate sealed record that only owners and admins write ([Security model](/en/docs/security-model#policy)); no agent and no CLI command can edit it.
2. **The human opt-in.** Inside the ceiling, an agent still needs a human to name the grand repository or cluster it may change:
   - **Local agents** (CLI and local MCP): the human exports `REDIACC_ALLOW_GRAND_REPO` (repo names, or `*`) or `REDIACC_ALLOW_CLUSTER_OPS` (cluster names, or `*`) in the terminal before starting the agent. The CLI checks the process ancestry, so a variable the agent sets mid-session does not count ([how each OS is checked](#how-a-local-opt-in-is-verified-on-each-os)).
   - **Remote agents** (remote MCP): the opt-ins are part of the grant the human creates in the account UI ([Remote server](/en/docs/ai-agents-mcp#remote-server)).

An opt-in never widens the ceiling: a repository the policy closes stays closed, whatever the environment or the grant says. Forks need no opt-in. A repository the CLI cannot identify counts as grand.

**Destructive changes ask first.** When an agent is cleared for a destructive change to a grand repository (`repo delete`, for example), the answer is `needs_confirmation`. An MCP client shows the user a confirmation prompt; a client without one gets a `confirm` argument to send back after asking the user. On the CLI, the human reruns the command with `--confirm-grand <repo>`.

Each answer carries a stable code (`POLICY_DENIED`, `GRAND_REPO_DENIED`, `CLUSTER_OPS_DENIED`, `AGENT_OPT_IN_MISSING`, `FORK_BLOCKED`, `AGENT_BLOCKED`, `CONFIRMATION_REQUIRED`), so a script or an agent branches on the code rather than the message ([JSON output](/en/docs/ai-agents-json-output)).

## The knowledge-gate model

Sensitive mutations follow the `passwd(1)` convention: to change a secret, prove you already knew it. **Symmetric for humans and agents**. Both go through the same gate. There is no "I'm at the keyboard" bypass.

- You want to rotate an API token stored at `/credentials/cfDnsApiToken`?
- The CLI asks: "what's the current value?"
- The agent (or human) supplies the plaintext via `--current "$OLD"`. The CLI hashes `$OLD` with SHA-256 and compares against the digest of the currently-stored value. Match → write goes through. Mismatch → refused, audited.
- To rotate without verifying the prior value, pass `--rotate-secret` (mutually exclusive with `--current`). This is loudly audited as a rotation, and it counts only for a human at an interactive terminal: an agent, or a script without a terminal on stdin, still needs `--current`.

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
          "run": "rdc repo secret get mail --key STRIPE_KEY" },
        { "description": "Skip the precondition (rotation, audited)",
          "run": "rdc repo secret set mail --key STRIPE_KEY --value <new> --mode file --rotate-secret" }
      ]
    }
  }]
}
```

**Agents should relay `next.options[].run` verbatim to the human rather than synthesizing their own commands.** This avoids the "agent invents a command that doesn't exist" failure mode and keeps the operator in control of the actual action. The rotation option is for the human to run at a terminal; it is refused to the agent itself.

### Worked example

```bash
# Discover the redaction stub's short digest (safe for agents).
$ rdc config field get --pointer /credentials/cfDnsApiToken
{"pointer": "/credentials/cfDnsApiToken", "value": "<redacted:secret>:abc12345"}

# Try to overwrite without proof: refused.
$ rdc config field set --pointer /credentials/cfDnsApiToken --new '"agent-picked-value"'
✗ Precondition failed: sensitive path requires --current

# Supply the current plaintext: allowed.
$ rdc config field set --pointer /credentials/cfDnsApiToken \
    --current "$OLD_CF_TOKEN" \
    --new   "$NEW_CF_TOKEN"
Set /credentials/cfDnsApiToken
```

If the agent never had `$OLD_CF_TOKEN`, it can't satisfy the precondition and the rotation is refused. The user who *does* have it can still do it by passing `--current` from their shell, or with `rdc config field rotate` at an interactive terminal.

## Redaction by default

Every `rdc` command that reads sensitive state: `config show`, `config field get`, `config machine list`, `config edit --dump --redacted`: returns **redaction stubs** for secret fields, not plaintext:

```
"sshKey":       "<redacted:credential>:9f3a2c1b"
"cfDnsApiToken":"<redacted:secret>:abc12345"
"storages.s3-prod.vaultContent": "<redacted:secret>:1f2e3d4c"
```

The stub's 8-char hex suffix is the first 8 chars of `sha256(canonicalize(value))`: enough to distinguish two different values at a glance, not enough to reverse. An agent can use a stub to track whether a value has changed without ever seeing it.

`--reveal` unredacts for humans on an interactive TTY. Agents are refused regardless of TTY state. Each grant writes a `reveal_granted` audit entry; each refusal writes a `refused` entry with the actor's agent signals attached.

## How a local opt-in is verified on each OS

`REDIACC_ALLOW_GRAND_REPO` and `REDIACC_ALLOW_CLUSTER_OPS` both rely on ancestry verification to prove the opt-in was set by the human and not injected by the agent. The verification works on Linux, macOS, and Windows, but the witness it reads differs per platform, and so does the strength of the guarantee:

| Platform | Witness | Strength |
|---|---|---|
| Linux | `/proc/<pid>/environ` for every process up the chain | Exec-time snapshot, kernel-served. A process cannot retroactively edit what it was started with. |
| macOS | `kern.procargs2` sysctl, read by a small helper that ships inside `rdc` | Same exec-time snapshot property as Linux. Readable for your own processes without root. |
| Windows | The live environment block of each ancestor process (PEB), read by the same helper, with PID-reuse guards | Weaker: Windows keeps no exec-time snapshot, so the check reads current memory. Ancestors still can't be rewritten by anything an agent normally runs, but the witness is not kernel-frozen the way it is on Linux and macOS. |

On macOS and Windows the CLI spawns its bundled `renet` binary to do the reading; the helper reports which of the watched variables each ancestor carries, and all decision logic stays in the CLI. If the helper is missing, outdated, or fails for any reason, the CLI cannot verify the opt-in and **fails closed**: the opt-in is rejected and the error says verification was unavailable, not that anything was done wrong. A working installation never shows that message; reinstalling `rdc` restores the helper.

What stays true on every platform: the opt-in must already be present in the environment of the agent process when it starts. Export it in the terminal, then launch the agent. An agent that sets the variable mid-session is refused.

## Audit log

Every mutation, every refusal, every `--reveal` grant writes a JSONL line to `~/.config/rediacc/audit.log.jsonl` (mode `0600`, rotated at 10 MB). Each line is hash-chained: its `prevHash` field is `sha256("<previous line>")`. Tampering with any line breaks the chain on every following line.

```jsonl
{"ts":"2026-04-21T10:02:47.831Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config field set","paths":["/credentials/cfDnsApiToken"],"outcome":"ok","configId":"...","configVersion":48,"prevHash":"sha256:9f3a..."}
{"ts":"2026-04-21T10:02:51.114Z","actor":{"kind":"agent","agentSignals":["CLAUDECODE"]},"command":"config edit","paths":[],"outcome":"refused","reason":"agent environment","prevHash":"sha256:abc1..."}
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

The primary mitigation is built in: **[per-repo secrets](/en/docs/repositories#secrets)** are stored in a separate plane from the encrypted repository image and are not copied across the fork boundary. A fork's containers boot with an empty secrets map and identify themselves as a different external principal than the parent. Set them with `rdc repo secret set` (env-mode for compose interpolation, file-mode for tmpfs `secrets:` blocks). The mutation gate is symmetric. Humans and agents alike must supply `--current` (passwd-style precondition) to overwrite or delete an existing value; `--rotate-secret` (audited rotation) is the human-at-a-terminal alternative.

**Cross-repo isolation is enforced.** A malicious or careless compose file in repo B cannot reference repo A's secrets directory. Renet's compose validator hard-rejects any `secrets: file:`, `configs: file:`, or `env_file:` path that points outside the current repo's `${REDIACC_NETWORK_ID}` directory, and the rejection is NOT overridable by `--unsafe`. Defense-in-depth: the Landlock sandbox around the Rediaccfile bash subprocess scopes filesystem reads to the current network's secrets directory only, so a `cat /var/run/rediacc/net-<other>/secrets/X` from a malicious Rediaccfile fails with EACCES at the kernel layer. The same holds on the Docker API: each repo's Docker socket is served by a renet policy proxy that refuses `--privileged`, host `pid`, `ipc` and `uts`, device requests, and binds that reach another repo's runtime or data with a `403`, so a container holding `${DOCKER_SOCKET}` cannot use the API to reach another repo, and not only a compose file is checked. Only the operator can widen the bind rule, for named host directories, with a root-owned grant that no container can write.

Two additional patterns close edge cases:

1. **Do not bake production credentials into the repository's filesystem itself.** A `.env` file committed into the image, or a credential persisted into a volume during `up()`, is reflinked into the fork. The per-repo secrets feature only protects values you keep in the secrets plane. It cannot retroactively protect bytes that already live inside the LUKS image. For existing repos with baked-in `.env` files, lift them into per-repo secrets manually.
2. **Constrain the fork's outbound network with eBPF egress filtering** so the fork can only reach localhost and explicit sandbox endpoints. Rediacc's per-repo network isolation is the foundation; per-fork egress allowlists are not built today, but the path is open.

Rediacc handles the deploy-time injection, the cross-fork isolation, and the cross-repo isolation. The "don't bake it into the image" half is on you.

## Quick recipes

### Let an agent work on one grand repository

```bash
# As the human, before starting the agent:
export REDIACC_ALLOW_GRAND_REPO='gitlab'
claude              # or cursor, gemini, etc.
```

The agent can now change `gitlab`, where the policy allows grand-repository changes, and no other grand repository. A destructive change, such as `repo delete gitlab`, still asks for confirmation.

### Rotate a cloud token without knowing the old value

```bash
# As the human, at an interactive terminal:
rdc config field rotate --pointer /credentials/cfDnsApiToken --new "$NEW_CF_TOKEN"
```

Rotation without `--current` stays with the human. An agent that knows the current value uses `rdc config field set --current` instead.

### Discover which fields an agent is allowed to touch

```bash
rdc config field list --sensitive --output json
```

Returns every pointer template, its kind (`secret` / `credential` / `pii` / `identifier`), and whether it's committed to the server-side HMAC envelope.

## See also

- [AI Agent Integration Overview](/en/docs/ai-agents-overview): the top-level tour
- [MCP server](/en/docs/ai-agents-mcp): local and remote MCP, grants and their opt-ins
- [Security model](/en/docs/security-model): the policy record and who can write it
- [Claude Code setup](/en/docs/ai-agents-claude-code): integration template
- [JSON output envelope](/en/docs/ai-agents-json-output): machine-readable responses
- [Encrypted config store](/en/docs/config-storage): server-side cryptographic enforcement
- [Account security](/en/docs/account-security): operator-facing security posture
