---
title: "Remote MCP: An Agent That Can Read Only What Its Person Can Read"
description: "Remote MCP runs on the three regional Workers. A grant holds one config's key and the policy keys of its person, never the master key, and tokens never outlive the grant."
author: Rediacc
publishedDate: 2026-11-25
category: announcement
tags:
  - mcp
  - ai-agents
  - security
  - policy
featured: false
language: en
---

> **TL;DR.** Remote MCP gives an AI agent a URL instead of a terminal. The design question was never how to connect the agent. It was what the agent may see once connected. The answer: exactly what the person who created the grant sees, and nothing the person does not.
>
> - A grant reaches **one config** and lives in **one region**.
> - Tokens last **1 hour** (access) and **30 days** (refresh) at most, and never longer than the grant itself.
> - The grant carries one config's content key and two **policy read keys**, never the master key of the config store.
> - Policy records changed format. Old ones are refused, and there is no migration path.

## A URL, not a login shell

The local MCP server (`rdc mcp serve`) runs next to the agent and inherits the access of the machine it runs on. The remote server is different. One MCP Worker runs per region at `mcp.<region>.rediacc.cloud`, and each agent connects to the URL of one grant: `https://mcp.<region>.rediacc.cloud/g/<grantId>`. Tool calls run on the organization's executor, not on a developer laptop.

Interactive clients such as claude.ai sign in through OAuth 2.1 with PKCE. Headless agents send an `rmcp_<grantId>.<secret>` bearer. Both forms identify the grant, so the id in the URL only names it.

## The grant is the boundary

A grant is a small, specific object. It names one config, an expiry and a scope: a read-only flag, a tool allowlist, and machine and repository name globs.

Three rules follow from that shape:

- **One config.** A `tools/call` that names another config is refused with `REDIACC_GRANT_SCOPE` before anything runs. A user with three configs authorizes three grants.
- **One region.** Grant ids start with their region. A request that reaches the wrong Worker is answered with HTTP 421 and the correct URL, never forwarded.
- **One lifetime.** An access token lasts the shorter of 1 hour and the time left on the grant. A refresh token lasts the shorter of 30 days and the time left on the grant. Every refresh looks the grant up again, so a revoked grant stops working at the next exchange. Presenting a refresh token twice revokes the grant.

A grant URL lives 7 days by default and 30 days at most.

## Judged as its person

The interesting part is the key material. A grant is a split secret. The browser draws a random value and shows it once. The account server stores only a hash of a tag derived from it, and the executor derives the slot key only while it holds both halves. What the slot key unwraps is the config's own content key, never the organization master key.

The same slot key also unwraps two **policy keys**. Policy, the authorization rules of a config entry, now lives in its own record, sealed under a key derived from the store key and the record's pointer: store, config, team and key generation. The grant carries the key of its own team config and the key of the organization-level config. Those are the two policy records its person reads, so the executor reads the same two.

The effect is that an agent is judged as its person. The ceiling is the organization policy narrowed by the team policy. The agent acts only where a human opt-in and that ceiling both allow it. It cannot edit policy, read secret values or widen its own grant. A key that the organization locks is ignored in a team policy, and the agent meets that outcome the same way the person does.

Binding each key to a pointer has a side effect worth stating. A holder of one policy key opens that pointer's records under that key generation and no others. A blob served for another store, config or team, or replayed under another version, fails its integrity tag.

## What changed for existing setups

- **Policy records are version 2.** A version-1 record, sealed under the store key itself, does not open. This is a clean break by design.
- **Hosted writes meet the same policy.** Config writes made through the hosted executor are checked against the policy ceiling before they are saved.
- **Local agents keep the same ceiling.** `REDIACC_ALLOW_CONFIG_EDIT` still opts an agent in to config edits for the pointers it names, but only inside what policy allows.
- **Expired and rotated grants fail loudly.** `initialize` and `tools/list` still answer, and each call returns `REDIACC_GRANT_EXPIRED`, `REDIACC_GRANT_REVOKED` or `REDIACC_KEY_ROTATED` with a `reauthUrl`.

Each grant allows 60 calls per minute and 5 in flight.

## What a leaked URL buys

A leaked URL acts as that user on its one config until it expires or is revoked. It opens no other config of the organization, and nothing outside the hosted executor of its region. Tool output does reach the model provider the user connects. Rediacc does not choose that provider.

The setup guide is [MCP Server Setup](/en/docs/ai-agents-mcp), and the key layout is in the [security model](/en/docs/security-model).
