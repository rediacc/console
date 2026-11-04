---
title: Proxy & Executor
description: How browser and thin-client commands run without the client ever holding SSH keys or machine addresses
category: Concepts
tags:
  - security
  - networking
subcategory: architecture
order: 4
language: en
---

# Proxy & Executor

Normally, `rdc` runs on your machine with your config and SSH keys, and connects to your servers directly. The proxy model splits this in two: a thin client that holds no secrets, and an **executor** that holds them and does the work. The [web console](/en/docs/web-console)'s Run button and the CLI's `--proxy` flag are both thin clients, and they speak the same wire protocol.

## Command intent, not commands

A thin client never holds an SSH key, a machine address, or a decrypted config. When it wants to run something, it sends only the command intent: an identifier for the command (its path in the CLI contract, for example `repo up`) plus the parameters. The executor looks the command up in the same contract, resolves it to the underlying server-side function, resolves the target machine from the decrypted config, and runs it over its own SSH connection. Output streams back to the client.

The executor is the CLI itself, started as a server with `rdc serve`. The same binary that operators run on a laptop becomes the thing that runs commands on their behalf. It has two placements:

- **`--mode daemon`**: runs on a host you control, enrolled headlessly like any CLI (see [Config Storage](/en/docs/config-storage)), so it can derive the config key on its own and needs no per-session grant. This is the strict tier: SSH never leaves your network.
- **`--mode container`**: runs in an org-keyed container hosted for you. It starts with no key at all and can do nothing until a client grants one for the session. This is the convenience tier.

## The CEK grant

Config storage is zero-knowledge: the server only ever stores encrypted blobs, and the content encryption key (CEK) exists in the clear only on a client that unlocked it. A container-mode executor therefore has to be *granted* the key, and the grant must not expose it to the server in between.

The flow: an unlocked browser opens a session with the executor, receives the session's public key, and seals the CEK to that session using X25519. The sealed blob travels through the account server, but the server cannot open it, so zero-knowledge is preserved end to end. The executor decrypts the CEK into RAM only, with a 30-minute idle expiry; nothing is ever written to disk. Subsequent command requests reference the granted session via the `X-Config-Session` header.

One detail matters for auditing: the same user identity spans all three legs (opening the session, granting the key, executing commands). The account server never forwards its own credential to the executor. For each leg it mints a short-lived token attributed to the actual user, and re-checks that user's membership every time. The executor verifies whichever token it is presented before acting. A grant made by one user cannot be used by another.

The `state` half of a config (host-local runtime data) never travels in the config blob at all, so it never reaches an executor through this path either.

## What can run through a proxy

Not every command makes sense remotely. Each command in the contract carries a `proxyCapable` flag, and the executor enforces it server-side, independent of any policy configuration:

- **Machine-plane, non-interactive commands** (deploy, backup, status, logs, and so on) are proxy-capable.
- **Config-plane commands** are not: they edit the config, which on this path is the browser's job (the web console routes them to its config editor instead).
- **Interactive commands** (terminals, VS Code sessions) are not: there is no TTY across this wire.
- **Client-side transfer commands** (`rdc repo sync`) are not: they move data between the *client's* filesystem and a machine, and the executor does not have the client's files.

The web console reads the same flag to decide whether a command gets a Run button at all, but the executor refuses non-capable commands regardless of what the client sends.

## The mock executor

In development, when no real executor is configured, the account server answers command requests itself with mock streams and clearly fake data (resource names prefixed `mock-`). This makes the entire console exercisable, including forms, streaming, and result rendering, without a machine or an unlock. Real execution requires a real executor.

## Restricting where the executor connects from

The config's `access` bucket holds the allowed IPv4 and IPv6 source ranges for SSH keys. Ranges can be set config-wide, per key and per machine, so a machine accepts a key only from the addresses its executor connects from.

- `rdc config access add <key> --public-key ... --hosted-executor` registers a key and attaches the two ranges of the hosted executor, `104.28.0.0/16` and `2a09:bac0::/29`. Both are observed Cloudflare egress ranges, not a list that Cloudflare publishes, so they can change.
- `rdc machine access set <machine> --key <key>` assigns a key to a machine; `--ipv4`, `--ipv6` and `--clear-ranges` adjust the ranges for that machine.
- `rdc machine access push <machine>` writes the access lines to the machine, and `--dry-run` shows the result without changing anything.
- `rdc machine access show <machine>` prints the access lines in effect.

`machine setup` re-applies the access lines, so a rebuilt machine regains its restrictions.

A push that would lock out the current SSH session, because its address lies outside the ranges of the key in use, is refused with `ACCESS_LOCKOUT`, and nothing is written. A push is refused with `ACCESS_FILE_CHANGED` when the file changed on the machine in the meantime; nothing was applied, so the push is safe to retry.

## Jobs, tickets and polling

Every machine-plane command runs on the machine as a job: a systemd unit that renet owns, with its status and event log kept in a spool on the machine. A dropped connection therefore never stops the work, and any client can pick the job up again by its id.

- **The attach window.** The executor streams a job's events for up to 20 seconds, with a heartbeat line every 10 seconds while the stream is quiet. A job that finishes inside the window returns its result in the same request. A longer job returns a result with `state: running` and the job id, after a `job` line that carries the machine and any overlapping jobs.
- **Polling.** The client then asks `GET /v1/jobs/<id>/poll` for the events after the last line it saw, together with the job's status, and backs off between empty answers. `POST /v1/jobs/<id>/cancel` cancels the job. Both routes apply the same policy as the command that started the job, and the poll that first sees a terminal state writes the audit event once.
- **Tickets.** Each invocation also writes a ticket in the CLI's config directory (`jobs/<config>.jsonl`). `rdc job wait <id>` waits for a job and exits with its exit code, and `rdc job list`, `status`, `logs`, `cancel` and `gc` manage the rest. Ctrl-C during a follow detaches without cancelling and exits with 130, and a follow whose connection could not be re-established exits with 16 and keeps the ticket.
- **Steps.** Work that follows a job, such as recording a result in the config or rendering a listing, is a step recorded on the ticket and in the spool. A step runs once, in whichever place first sees the job finish: the command itself, `rdc job wait`, the notice printed by the next command, or the executor's poll. The claim is taken on the machine, so two observers never run the same step.
- **Overlaps.** A start that overlaps a live job on the same repository or machine prints a warning with the command that attaches to the live job. When the overlap policy refuses the start, the command exits with 15 (`BUSY`), and the refusal carries the overlapping jobs in `overlaps`.
- **Exceptions.** Interactive commands, client-side transfers and the `job` commands themselves do not run as jobs.
- **Retention.** The machine keeps a finished read-only job for one hour and any other finished job for seven days, and it keeps at most 2000 finished jobs.

## Related

- [Web Console](/en/docs/web-console), the browser client built on this model
- [Config Storage](/en/docs/config-storage), the zero-knowledge store the CEK protects
