---
title: MCP Server Setup
description: Connect AI agents to Rediacc infrastructure using the Model Context Protocol (MCP) server.
category: Guides
tags:
  - ai-agents
  - cli
subcategory: ai-agents
order: 33
language: en
---

## Overview

Two MCP (Model Context Protocol) servers draw their tools from one registry, and the remote server offers a subset:

| Server | Transport | Runs | Tools |
|---|---|---|---|
| Local | stdio | `rdc mcp serve`, spawned by the agent | Every tool |
| Remote | Streamable HTTP | `https://mcp.<region>.rediacc.cloud/g/<grantId>` | The remote tools, all but the local-only table |

**Prerequisites:** `rdc` installed and configured with at least one machine for the local server. A grant on a config for the remote server.

## Local server

`rdc mcp serve` starts an MCP server over stdio. The agent spawns it as a subprocess and talks JSON-RPC to it.

### Claude Code

The project's `.mcp.json` carries the entry:

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

Or with a named config:

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

Open Settings → MCP Servers → Add Server:

- **Name**: `rdc`
- **Command**: `rdc mcp serve`
- **Transport**: stdio

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--config <name>` | (default config) | Named config to use for all commands |
| `--timeout <ms>` | `120000` | Default command timeout in milliseconds |

## Remote server

One MCP Worker runs per region at `mcp.<region>.rediacc.cloud`. Each agent connects to the URL of one grant, `https://mcp.<region>.rediacc.cloud/g/<grantId>`. The grant names one config, an expiry and a scope: a read-only flag, a tool allowlist, and machine and repository name globs. Tool calls run on the grant's organization executor.

### Credentials

Both forms identify the grant; the grant id in the URL only names it.

| Form | Use | Sent as |
|---|---|---|
| OAuth access token | Interactive clients such as claude.ai | `Authorization: Bearer <token>` |
| Agent bearer `rmcp_<grantId>.<secret>` | Headless agents | `Authorization: Bearer` or `x-api-key` |

A credential in the query string is refused with 400. A missing, expired or wrong-grant OAuth token gets 401 with a `WWW-Authenticate: Bearer resource_metadata=...` header that points to the grant's protected-resource document, so an OAuth client refreshes or signs in. An unknown grant, a wrong secret and an agent bearer for another grant all get one bare 401.

### OAuth

The Worker is an OAuth 2.1 authorization server with PKCE (S256 only). Clients register through a Client ID Metadata Document or dynamic client registration at `/register`.

| Endpoint | Purpose |
|---|---|
| `/.well-known/oauth-authorization-server` | Server metadata |
| `/.well-known/oauth-protected-resource/g/<grantId>` | Protected-resource document of one grant |
| `/authorize` | Starts authorization and redirects to the account page `/account/mcp/authorize` |
| `/oauth/token` | Code exchange, refresh and revocation |
| `/register` | Dynamic client registration |

The client sends `resource=https://mcp.<region>.rediacc.cloud/g/<grantId>`. Authorization completes only for the grant that the resource names, and a token works only at the URL of its grant. The `/authorize` redirect carries a signed single-use handle and no secret.

### Token lifetimes

A token never outlives its grant.

| Token | Lifetime |
|---|---|
| Access token | The shorter of 1 hour and the time left on the grant |
| Refresh token | The shorter of 30 days and the time left on the grant |

Every code exchange and refresh looks the grant up again. An expired, revoked or key-rotated grant answers `invalid_grant` and revokes the OAuth grant. Refresh tokens rotate, and presenting one twice revokes the grant.

### One config per grant

A grant serves the one config it names. A `tools/call` with an argument that names another config (`config` or a spelling of it) is refused with `REDIACC_GRANT_SCOPE` before anything runs. A user with several configs authorizes one grant per config. A tool outside the grant's allowlist, or a write tool under a read-only grant, is absent from `tools/list` and refused when called.

### Regions

A grant id starts with its region, such as `eu_`. A request at `/g/<grantId>` on another region's Worker is answered 421 with the right URL:

```json
{
  "code": "REDIACC_WRONG_REGION",
  "message": "This grant lives in the us region. Use https://mcp.us.rediacc.cloud/g/us_...",
  "region": "us",
  "mcpUrl": "https://mcp.us.rediacc.cloud/g/us_..."
}
```

A grant is never accepted as an OAuth resource, token audience or authorization target outside its region.

### Grant states and limits

A grant that expired, was revoked, or lost its key to a config-store key rotation still answers `initialize` and `tools/list`. Each `tools/call` then returns `REDIACC_GRANT_EXPIRED`, `REDIACC_GRANT_REVOKED` or `REDIACC_KEY_ROTATED` with a `reauthUrl` the user opens to authorize again.

Each grant allows 60 calls per minute and 5 calls in flight. A call over either limit returns `REDIACC_RATE_LIMITED` with `retryAfterSeconds`.

## Available Tools

<!-- >>> gen-docs: mcp-tools -->
<!-- The tools a remote MCP client reaches, rendered from packages/shared/src/mcp/tools.generated.json; check:ci-mcp-docs-parity holds every locale copy to the same names in the same order. -->

Scans: the tools in `packages/shared/src/mcp/tools.generated.json` a remote MCP client reaches (every surface except `local`), one row per tool.

| Tool | Destructive | Description |
|---|---|---|
| `backup_browse` | no | List the files a repository contains. |
| `backup_cancel` | no | Cancel a running backup on a remote machine. |
| `backup_check` | no | Prove a stored snapshot opens with the passphrase by restoring one file |
| `backup_immutability_show` | no | Show the delayed-deletion window in force |
| `backup_list` | no | List backup artifacts on a machine. |
| `backup_manifests` | no | List backup snapshot manifests recorded on the server |
| `backup_reconcile` | yes | Reset a repository's stored-bytes ledger to what the store actually holds (never deletes a chunk) |
| `backup_repair` | yes | Re-upload chunks the store lost or holds wrong, from this machine's anchor |
| `backup_restore` | yes | Turn a backup artifact into a live repository. |
| `backup_retention` | no | Show the snapshot retention policy the server is enforcing. |
| `backup_retention_preview` | no | Show which snapshots the next sweep would delete and the space it would free. |
| `backup_run` | no | Run a backup now. |
| `backup_snapshot` | no | Upload a chunk-store snapshot: full inventory first, changed cells after. |
| `backup_status` | no | Show backup status and timer state on a remote machine. |
| `backup_strategy_list` | no | List all backup strategies |
| `backup_strategy_show` | no | Show backup strategy details |
| `backup_toc-key_sync` | no | Install the repository's listing key on its machine, or replace a different one |
| `backup_undelete` | no | Cancel a delayed snapshot delete before it takes effect |
| `backup_usage` | no | Show backup storage quota, stored bytes, and per-repo usage |
| `backup_verify` | no | Verify a repository's backup anchor against the chunk store. |
| `cluster_snapshot_list` | no | List the cluster's group snapshots. |
| `cluster_status` | no | List all clusters, or pass a cluster name to show that cluster's full config. |
| `config_access_list` | no | List the config's access keys |
| `config_prune` | no | Remove dead weight from the local config file at ~/.config/rediacc/&lt;config&gt;.json. |
| `config_reconcile` | no | Rebuild the local state bucket from machine truth (renet list all). |
| `config_show` | no | Show current config details |
| `credits` | no | Show the remaining credit balance for this account. |
| `datastore_list` | no | List named datastores, where they are attached, and what they hold. |
| `datastore_snapshot_list` | no | List a datastore's snapshots. |
| `datastore_status` | no | Show one datastore: its backend, attachment, usage, repositories and snapshots. |
| `feedback_list` | no | List the feedback reports visible to this machine: id, short fingerprint, status and dates. |
| `feedback_report` | no | Build a report from the newest failed command (--last), a recorded command (--command &lt;n&gt;) or a message alone, print exactly what would be sent, and send it after confirmation. |
| `feedback_show` | no | Show one feedback report by its id (or a unique prefix of it), with its status, occurrence count and dates. |
| `incident_status` | no | List the incidents of the organization, or show one with its scope, window, machine steps and the early-warning, notification and final-report deadline clocks. |
| `job_cancel` | yes | Cancel a running detached job |
| `job_dismiss` | yes | Give up on job tickets locally: their owed steps are dropped and the ticket stops showing up. |
| `job_gc` | yes | Remove finished jobs and their logs |
| `job_list` | no | List detached jobs on a machine, newest first |
| `job_logs` | no | Replay or follow a detached job's event log |
| `job_status` | no | Show a detached job's status |
| `job_wait` | no | Wait up to 50 s for a job to finish. |
| `legal` | no | Print the legal document links in the CLI language with the binding English links, the current Terms of Service version with its checksum and archive URL, the acceptance on record (from the account server when logged in, from this config when anonymous), and the contracting entity. |
| `machine_access_show` | no | Show the access keys bound to a machine and the ranges each resolves to there |
| `machine_add` | no | Register an existing machine you can reach over SSH. |
| `machine_containers` | no | List Docker containers on a machine. |
| `machine_converge` | yes | Restart every repository daemon still running on an older runtime layout, one repository at a time, so it moves onto the current one. |
| `machine_deprovision` | yes | Destroy a cloud-provisioned machine and remove from config |
| `machine_gpu_list` | no | List the GPUs detected on a machine, the CDI device names its specs define, and the repositories each device is granted to. |
| `machine_health` | no | Check machine health for CI/CD pipelines. |
| `machine_infra_show` | no | Show infrastructure configuration for a machine (base domain, public IPs, ports), shared TLS settings (cert email, CF DNS token), and Cloudflare zone ID |
| `machine_list` | no | List machines |
| `machine_provider_add` | no | Add a cloud provider |
| `machine_provider_list` | no | List configured cloud providers for machine provisioning |
| `machine_provider_remove` | yes | Remove a cloud provider configuration |
| `machine_provision` | yes | Provision a new machine on a cloud provider using OpenTofu. |
| `machine_prune` | yes | Remove orphaned datastore resources and stale snapshots from a machine. |
| `machine_remove` | yes | Remove a machine from the config. |
| `machine_repos` | no | List deployed repositories on a machine. |
| `machine_restart-services` | yes | Roll the renet daemons that still run a replaced binary onto the installed one, one unit at a time, each confirmed active on the new binary before the next. |
| `machine_scan-keys` | no | Record the machine's SSH host keys in the local config. |
| `machine_services` | no | List rediacc-managed systemd services on a machine (name, state, sub-state, restart count, memory, repository resolved to name with original in repository_guid) |
| `machine_setup` | no | Finish onboarding a machine: install renet and prepare it to host repositories. |
| `machine_status` | no | Get connection details (ip, user, port, datastore), system info, containers (repository resolved to name, original in repository_guid, domain, autoRoute), services (repository resolved to name), repositories (name resolved from GUID, original in guid), and resource usage for a machine. |
| `repo_admin_fsck` | no | Validate config refs (branches/HEAD) against the objects present on a machine; report dangling refs and orphan commits. |
| `repo_cat` | no | Read a bounded window of a file in a repository to stdout (diagnostics go to stderr). |
| `repo_checkout` | yes | Reflink-clone an immutable commit (or branch tip) into a fresh writable working fork and point HEAD at it. |
| `repo_commit` | yes | Freeze a mounted working fork into a new immutable commit (git-like). |
| `repo_create` | yes | Create a new repository. |
| `repo_delete` | yes | Delete a repository and its data. |
| `repo_diff` | no | Git-style file-level diff between two copy-on-write forked repositories. |
| `repo_down` | yes | Stop repository Docker containers (runs Rediaccfile down). |
| `repo_exec` | yes | Run a command inside a repository container. |
| `repo_flows` | no | List the network flows recorded for a repository in a time window: time, process, destination, bytes out and in, and the destination's ASN and country when known. |
| `repo_fork` | yes | Create a near-instant CoW fork of a repository with a NEW GUID and networkId (fully independent copy). |
| `repo_gc` | yes | Reachability garbage-collection: delete immutable commit objects on a machine that no branch/HEAD reaches. |
| `repo_health` | no | Run the repository's Rediaccfile health() checks and exit 0 (ok), 1 (warning) or 2 (error). |
| `repo_list` | no | List repositories on a machine. |
| `repo_log` | no | Print the commit history reachable from a working fork's current commit (or a commit reference), walking the parent chain recorded by 'rdc repo commit'. |
| `repo_logs` | no | Show application logs from a repository's containers. |
| `repo_merge` | yes | Lifecycle-safe merge of a source commit/fork into a target working fork. |
| `repo_migrate` | yes | Move a repository to another machine with minimal downtime: a two-phase copy (bulk sync while running, then a short stop + delta sync + start on the destination) with DNS cutover. |
| `repo_opens` | no | List the file opens recorded for a repository in a time window: time, process and path, with sensitive paths marked. |
| `repo_pull` | yes | Pull repository from another machine. |
| `repo_push` | yes | Push a repository backup to storage or directly to another machine. |
| `repo_replicate` | no | Provision read replicas of a repository. |
| `repo_replicate_remove` | yes | Remove a replica set: delete its generated k8s objects (label-scoped), discard its fork datastores, drop its snapshot, and forget the state. |
| `repo_replicate_status` | no | Show managed replica sets: replicas, hosting nodes, fork datastores, snapshot, and refresh timestamps. |
| `repo_secret_get` | no | Show the SHA-256 digest of a secret. |
| `repo_secret_list` | no | List secret keys and modes (never values, never digests). |
| `repo_status` | no | Get repository status (mount state, Docker daemon running, container count, disk usage). |
| `repo_trim` | no | Reclaim datastore pool space from mounted repositories (online, zero downtime). |
| `repo_up` | yes | Deploy/update a repository (runs Rediaccfile up via renet compose, starts containers). |

92 row(s). Generated by `npx tsx scripts/gen/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->

<!-- >>> gen-docs: mcp-tools-local -->
<!-- The tools only the local MCP server offers, from the same registry. -->

Scans: the tools in `packages/shared/src/mcp/tools.generated.json` only the local `rdc mcp serve` offers (surface `local`), one row per tool.

| Tool | Destructive | Description |
|---|---|---|
| `cluster_kubeconfig` | no | Fetch the kubeconfig from the cluster control node over SSH and cache it locally (0600) for kubectl. |
| `config_audit_log` | no | Read the audit log of mutations made through this config. |
| `config_audit_verify` | no | Verify the audit log's hash chain has not been tampered with. |
| `config_current` | no | Show the active config: name, file, resolved server and channel, token state |
| `config_list` | no | List all config files |
| `forensics_verify` | no | Recompute the audit day-file hash chain and the signed forensics batch chains of an evidence directory (an rdc incident export directory) and list every gap and edit. |
| `incident_export` | no | Write the incident's window to a directory: the incident record with its clocks, the merged timeline, the bytes-out aggregates, the raw chain manifest and the raw files it lists under their manifest keys. |
| `machine_infra_cert_status` | no | Show cached certificate inventory |
| `server_status` | no | Show the health, tier, certificate and image of an installed server |
| `version` | no | Print the CLI version, platform, update channel and the active license: the plan when logged in, "anonymous (FREE per repository)" without a login, and "unknown (server unreachable)" when the account server cannot be reached. |

10 row(s). Generated by `npx tsx scripts/gen/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->

## Example Workflows

**Check machine status:**
> "What's the status of my production machine?"

The agent calls `machine_status` and gets connection details, system info, containers, services, repositories and resource usage.

**Deploy an application:**
> "Deploy gitlab on my staging machine"

The agent calls `repo_up` with `name: "gitlab"` and `machine: "staging"`, which deploys the repository and returns success or failure.

**Follow a long job:**
> "Restore last night's backup of nextcloud"

The agent calls `backup_restore`. A command that outlives its window returns a job handle, and the agent calls `job_wait` (up to 50 s per call) and `job_logs` until the job finishes.

**Debug a failing service:**
> "My nextcloud is slow, figure out what's wrong"

The agent calls `machine_health`, then `machine_containers` and `repo_logs`, and suggests a fix.

## Security

The local MCP server enforces two layers of protection. The remote server's limits are under [Remote server](#remote-server).

### Fork-only mode (default)

By default, the server runs in **fork-only mode**: write tools (`repo_up`, `repo_down`, `repo_delete`, `repo_exec`, `repo_push`, `repo_pull`) can only operate on fork repositories. Agents cannot touch grand (original) repositories. By design.

> **Per-repo secrets are CLI-only by design.** `repo_secret_set` and `repo_secret_unset` are intentionally **not** exposed as MCP tools. Writes require a `--current <previous-value>` precondition (or `--rotate-secret` to acknowledge an unverified rotation), and that ceremony needs human eyes-on. Agents that need to suggest a secret rotation should call `repo_secret_get` to confirm the digest, then relay the operator-facing CLI command to the user via the structured `next.options[].run` field in the JSON error envelope. See [AI Agent Safety](/en/docs/ai-agents-safety#structured-next-action-hints) for the full pattern, and [Repositories § Secrets](/en/docs/repositories#secrets) for the user-facing how-to.

To allow an agent to modify grand repos, export `REDIACC_ALLOW_GRAND_REPO` in the terminal **before starting the agent that hosts the MCP server**:

```bash
export REDIACC_ALLOW_GRAND_REPO='gitlab'   # one repo
# or 'repo1,repo2,repo3' (whitespace around entries is ignored), or '*' for all repos
claude   # or cursor, gemini, etc.
```

The override is verified against the process ancestry: it only counts when it was already present in the environment of the agent process itself, which means it was exported before the agent (and the MCP server it spawned) started. An agent cannot grant itself access by setting the variable mid-session. There is deliberately no server flag for this: a flag in the MCP server arguments carries no proof of who put it there, while the ancestry check does. Machine-level access (such as `term connect <machine>` without a repo) still requires `*`; a list of repo names does not unlock it.

### Per-repo SSH keys and server-side sandbox

Each repository has its own SSH key pair. The public key is deployed to `authorized_keys` with a `command=` prefix that forces all SSH sessions through `renet sandbox-gateway <repo-name>`, a server-side ForceCommand that cannot be bypassed by any client, including VS Code.

**How it works:**
1. `rdc repo create` or `rdc repo fork` generates a unique ed25519 key pair per repo
2. The public key is deployed to the remote with `command="renet sandbox-gateway <name>"`
3. Every SSH connection using that key goes through the gateway, which applies:
   - **Landlock LSM**, kernel-level filesystem restrictions to the repo's mount path
   - **OverlayFS home overlay**, writes to `$HOME` captured per-repo, reads fall through to real home
   - **Per-repo TMPDIR** at `<datastore>/.interim/sandbox/<name>/tmp/`
   - **Docker access** via the repo's isolated Docker socket
   - **Privilege drop** to the universal user (`rediacc`)
4. The repo's `.envrc` is loaded automatically for Docker and environment setup

**Allowed RW**: repo mount path, per-repo sandbox workspace, home directory (via overlay), Docker socket
**Allowed RO**: system paths (`/usr`, `/bin`, `/etc`, `/proc`, `/sys`)
**Blocked**: other repos' mount paths, system files outside allowlist

**VS Code integration**: Each repo gets its own VS Code server installation at `<datastore>/.interim/sandbox/<name>/.vscode-server/`. Multiple repos can be open simultaneously with independent sandboxed environments, no server sharing between repos.

This prevents lateral movement. Even if an agent gains shell access to a fork, it cannot read or modify other repositories on the same machine. Machine-level SSH (without a repository) uses the team key and is not sandboxed.

## Architecture

The local MCP server is stateless. Each tool call spawns `rdc` as an isolated child process with `--output json --yes --quiet` flags. This means:

- No state leaks between tool calls
- Uses the existing `rdc` configuration and SSH keys
- Errors in one command don't affect others
