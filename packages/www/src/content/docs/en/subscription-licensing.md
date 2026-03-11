---
title: "Subscription & Licensing"
description: "Understand how account, rdc, and renet handle machine slots, repo licenses, and plan limits."
category: "Guides"
order: 7
language: en
---

# Subscription & Licensing

Rediacc licensing has three moving parts:

- `account` signs entitlements and tracks usage
- `rdc` authenticates, requests licenses, and delivers them to machines
- `renet` enforces the installed licenses on the machine without calling the account server

This page explains how those pieces fit together for local deployments.

## What Licensing Does

Licensing controls two different things:

- **Machine access accounting** through **Floating Licenses**
- **Repository runtime authorization** through **repo licenses**

These are related, but they are not the same artifact.

## How `account`, `rdc`, and `renet` Work Together

`account` is the source of truth for plans, contract overrides, machine-slot usage, and monthly floating license requests.

`rdc` runs on your workstation. It logs you into the account server, requests the licenses it needs, and installs them on remote machines over SSH.

`renet` runs on the remote machine. It validates the installed signatures locally and decides whether a repository operation can continue. `renet` does not call the account server.

The normal flow looks like this:

1. You authenticate with `rdc subscription login`
2. You run a repository command such as `rdc repo create`, `rdc repo up`, or `rdc repo down`
3. If the required license is missing or expired, `rdc` requests it from `account`
4. `rdc` writes the signed license to the machine
5. `renet` validates the installed license and continues the operation

See [rdc vs renet](/en/docs/rdc-vs-renet) for the workstation-vs-server split, and [Repositories](/en/docs/repositories) for the repository lifecycle itself.

## Machine Licenses vs Repo Licenses

### Machine license

A machine license is a short-lived, machine-scoped license that represents account-backed access for a remote machine.

It is used for:

- floating machine-slot accounting
- machine-level entitlement checks
- bridging account-backed operations to a specific machine

It is not the runtime authority for repository start and stop anymore.

### Repo license

A repo license is a signed license for one repository on one machine.

It is used for repository lifecycle operations such as:

- `repo create`
- `repo resize`
- `repo expand`
- `repo up`
- `repo down`
- repo autostart on machine restart

Repo licenses are bound to the machine and the target repository, and Rediacc hardens that binding with repository identity metadata. For encrypted repositories, that includes the LUKS identity of the underlying volume.

In practice:

- machine license answers: "can this machine participate in account-backed licensing?"
- repo license answers: "can this specific repo run on this specific machine?"

## Default Limits

Repository size depends on the entitlement level:

- registered user with no paid subscription: up to `4 GB`
- Community: up to `10 GB`
- paid plans: plan or contract limit

Default paid-plan limits are:

| Plan | Floating Licenses | Repository Size | Floating license requests |
|------|-------------------|-----------------|---------------------------|
| Community | 2 | 10 GB | 500 |
| Professional | 5 | 100 GB | 5,000 |
| Business | 20 | 500 GB | 20,000 |
| Enterprise | 50 | 2048 GB | 100,000 |

Contract-specific limits can raise or lower these values for a specific customer.

## What Happens During Repo Create, Up, Down, and Restart

### Repo create

When you create a repository, `rdc` contacts `account`, obtains the required license material, installs it on the target machine, and retries if needed.

That account-backed issuance counts toward:

- your machine-slot activity when a machine license is involved
- your monthly **Floating license requests**

### Repo up and repo down

`renet` checks the installed repo license locally before it allows the repository to start or stop.

This is important because users may change storage outside Rediacc. Licensing is enforced on the runtime path, not only at create time.

### Machine restart and autostart

Autostart also relies on the installed repo license. `renet` does not need live account access to decide whether the repository can start after reboot.

That is why repo licenses use a long-lived validity model:

- `refreshRecommendedAt` is the soft refresh point
- `hardExpiresAt` is the blocking point

If the repo license is stale but still before hard expiry, runtime can continue. Once it reaches hard expiry, `rdc` must refresh it.

## Checking Status and Refreshing Licenses

Login:

```bash
rdc subscription login
```

Show account-backed subscription status:

```bash
rdc subscription status
```

Show machine-license details for one machine:

```bash
rdc subscription status -m hostinger
```

Show installed repo-license details on one machine:

```bash
rdc subscription repo-status -m hostinger
```

Force a machine-license refresh:

```bash
rdc subscription refresh -m hostinger
```

Force a repo-license refresh for an existing repository:

```bash
rdc subscription refresh-repo my-app -m hostinger
```

For first-time machine setup, see [Machine Setup](/en/docs/setup).

## Offline Behavior and Expiry

`renet` stays offline from the account server. It only trusts the installed signed licenses.

That means:

- a running environment does not need live account connectivity on every command
- repo restarts can continue while the repo license is stale but still valid
- truly expired repo licenses must be refreshed through `rdc`

Machine licenses and repo licenses expire differently. A machine can show an expired machine license while some repositories on it still have valid repo licenses. When that happens, inspect both surfaces separately instead of assuming they mean the same thing.

## Floating Licenses vs Floating License Requests

These names are intentionally separate:

- **Floating Licenses** = active machine slots
- **Floating license requests** = monthly account-backed license issuance activity

Repo-license issuance contributes to floating-license-request usage. It is normal for those numbers to move independently.

If you need a customer-facing view of usage and recent repo-license issuance history, use the account portal. If you need machine-side inspection, use `rdc subscription status -m` and `rdc subscription repo-status -m`.
