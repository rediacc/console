---
title: Proxy & Executor
description: How browser and thin-client commands run without the client ever holding SSH keys or machine addresses
category: Concepts
order: 4
language: en
sourceHash: "3f522a473a550b0c"
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

## Related

- [Web Console](/en/docs/web-console), the browser client built on this model
- [Config Storage](/en/docs/config-storage), the zero-knowledge store the CEK protects
