---
title: Security Model
description: Who can see what in config storage, how keys are scoped, what agents and remote MCP can reach, and what is recoverable.
category: Guides
tags:
  - security
  - account
subcategory: account
order: 14
language: en
---

# Security Model

This page states what config storage protects, which key opens what, and what each kind of caller can reach. For setup steps see [Config Storage](/en/docs/config-storage); for sessions and tokens see [Account Security & API](/en/docs/account-security).

## Who can see what

A stored config is encrypted in three layers. The SDK layer and the org passphrase layer are keyed by the server. The middle layer is the content encryption key (CEK), which only key-slot holders can unwrap: a slot secret held on the device combines with a server-held secret, and neither half alone opens it.

| Attacker holds | Sees config content | Why |
|---|---|---|
| A database copy only | No | Config blobs live in object storage, not the database |
| The database and the object storage | No | The org passphrase layer needs the Worker secret, and the CEK layer needs a slot secret |
| A full server compromise | Not without a slot secret | The server layers fall, but the CEK stays behind passkey PRF output or the 160-bit recovery kit, and neither is guessable |
| A removed member's device | What was already pulled | Later versions stay closed after a CEK rotation |
| A leaked agent URL | One config, as that user | See [Agents and remote MCP](#agents-and-remote-mcp) |

The server can still see metadata (config ids, teams, versions, timestamps, blob sizes) and can refuse, delay or delete requests. An operator who serves malicious portal code can read keys in the browser. Every blob is bound to its store, config, team and version, so the server cannot swap or edit one undetected, and the CLI refuses a version older than one it has seen.

## Key scope

- One config store per organization, and one CEK per store. Teams are server-side access control, not cryptographic isolation: a recovery kit or key slot opens the whole organization's CEK.
- Key slots are unique per store, user and method, so a recovery kit is one per user per organization. A user in two organizations holds two kits, and there is no team kit.
- A machine secret is one per machine per organization and enrolls a headless machine.
- Each config has its own content key under the CEK. An agent grant carries one config's content key, so no other config of the organization opens with it.
- Each config's authorization policy is a separate record under a key derived from the CEK and the record's pointer. A holder of one policy key opens that pointer's records only.

## Agents and remote MCP

An agent grant is the key-holder type behind a remote MCP URL. It carries one config's content key and the policy keys of the grant's own team config and of the organization-level config, never the CEK, so an agent reads exactly what its person reads.

- **Lifetime.** A URL lives 7 days by default and 30 days at most, then expires or is revoked. An expired grant is refused and the client re-authorizes.
- **Scope.** A grant reaches one config and belongs to one region (eu, us or asia). A URL presented to another region is refused with the right region named, never forwarded. On-premise installs are a single region.
- **Policy.** An agent acts only where a human opt-in and the policy ceiling both allow it. The ceiling is the organization policy narrowed by the team policy. An agent cannot edit policy, read secret values or widen its own grant.
- **Blast radius.** A leaked URL acts as that user on its one config until it expires or is revoked. It opens nothing outside the hosted executor of its region.

Tool output reaches the model provider the user connects, which Rediacc does not choose.

### On-premise

There is no Cloudflare in the path. The Worker secrets of the cloud become environment variables or config on the customer host, so host access replaces the Worker-secret boundary in the table above, and tool calls run on the customer's own daemon executor.

## Policy

The policy is a separate record, sealed per config entry with authenticated data that binds store, config, team, version and key generation. The server cannot read it, and a replayed or swapped record fails its integrity tag. Version-1 policy records are refused.

Only an organization owner or admin writes the organization policy, and only a team admin (or an owner or admin) writes that team's policy. A write needs 2FA and an elevated session, and a bound passkey when the store requires passkeys. Every member and every executor serving them reads it. A key the organization locks is ignored in a team policy.

## What is recoverable

| Situation | Recovery |
|---|---|
| Lost passkey | Unlock with the recovery kit, then enroll a new passkey |
| Lost kit | Regenerate it from a working passkey; the old printout stops working |
| Both lost | An owner or admin re-adds the member through the member handoff |
| Last key holder loses both | Unrecoverable, which is why a second key holder is advised |
| Member removed | Their slots and tokens go at once; a CEK rotation closes later versions to a key they kept |
| CEK rotation | Re-wraps the CEK under a new generation and invalidates every recovery kit |

The server refuses a slot deletion, member removal or member leave that would leave fewer than two key holders and no recovery slot. Every member receives a mandatory recovery kit at enrollment, and keeping it is the member's responsibility.
