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

`account` is the source of truth for plans, contract overrides, machine activation state, and monthly repo license issuances.

`rdc` runs on your workstation. It logs you into the account server, requests the licenses it needs, and installs them on remote machines over SSH.

`renet` runs on the remote machine. It validates the installed signatures locally and decides whether a repository operation can continue. `renet` does not call the account server.

The normal human-operated flow looks like this:

1. You authenticate with `rdc subscription login`
2. You run a repository command such as `rdc repo create`, `rdc repo up`, or `rdc repo down`
3. If the required license is missing or expired, `rdc` requests it from `account`
4. `rdc` writes the signed license to the machine
5. `renet` validates the installed license and continues the operation

See [rdc vs renet](/en/docs/rdc-vs-renet) for the workstation-vs-server split, and [Repositories](/en/docs/repositories) for the repository lifecycle itself.

For automation and AI agents, use a scoped subscription token instead of browser login:

```bash
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

You can also inject the token directly through the environment so the CLI can issue and refresh repo licenses without any interactive login step:

```bash
export REDIACC_SUBSCRIPTION_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## Machine Licenses vs Repo Licenses

### Machine activation

Machine activation is the server-side machine state that represents account-backed access for a remote machine.

It is used for:

- floating machine-slot accounting
- machine-level activation checks
- bridging account-backed repo issuance to a specific machine

It is not an installed runtime artifact and it is not the runtime authority for repository start and stop.

### Repo license

A repo license is a signed license for one repository on one machine.

It is used for repository lifecycle operations such as:

- `repo create`
- `repo resize`
- `repo expand`
- `repo up`
- `repo down`
- `backup push`
- `backup pull`
- `backup sync`
- repo autostart on machine restart

Repo licenses are bound to the machine and the target repository, and Rediacc hardens that binding with repository identity metadata. For encrypted repositories, that includes the LUKS identity of the underlying volume.

In practice:

- machine activation answers: "can this machine participate in account-backed licensing?"
- repo license answers: "can this specific repo run on this specific machine?"

## Default Limits

Repository size depends on the entitlement level:

- Community: up to `10 GB`
- paid plans: plan or contract limit

Default paid-plan limits are:

| Plan | Repository Size | Monthly repo license issuances |
|------|-----------------|-------------------------------|
| Community | 10 GB | 500 |
| Professional | 100 GB | 5,000 |
| Business | 500 GB | 20,000 |
| Enterprise | 2048 GB | 100,000 |

Contract-specific limits can raise or lower these values for a specific customer.

## What Happens During Repo Create, Up, Down, and Restart

### Repo create

When you create a repository, `rdc` contacts `account`, obtains the required license material, installs it on the target machine, and retries if needed.

That account-backed issuance counts toward your monthly **repo license issuances** usage.

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

Human login:

```bash
rdc subscription login
```

Automation or AI-agent login:

```bash
rdc subscription login --token "$REDIACC_SUBSCRIPTION_TOKEN"
```

For non-interactive environments, setting `REDIACC_SUBSCRIPTION_TOKEN` is the simplest option. The token should be scoped only for the subscription and repo-license operations the agent needs.

Show account-backed subscription status:

```bash
rdc subscription status
```

Show machine activation details for one machine:

```bash
rdc subscription activation-status -m hostinger
```

Show installed repo-license details on one machine:

```bash
rdc subscription repo-status -m hostinger
```

Refresh machine activation and batch-refresh repo licenses:

```bash
rdc subscription refresh -m hostinger
```

Repositories discovered on the machine but missing from local `rdc` config are rejected during batch refresh. They are reported as failures and are not auto-classified.

Force a repo-license refresh for an existing repository:

```bash
rdc subscription refresh-repo my-app -m hostinger
```

On first use, a licensed repo or backup operation that finds no usable repo license can trigger an account-authorization handoff automatically. The CLI prints an authorization URL, tries to open the browser in interactive terminals, and retries the operation once after authorization and issuance succeed.

In non-interactive environments, the CLI does not wait for browser approval. Instead, it tells you to supply a scoped token with `rdc subscription login --token ...` or `REDIACC_SUBSCRIPTION_TOKEN`.

For first-time machine setup, see [Machine Setup](/en/docs/setup).

## Offline Behavior and Expiry

`renet` stays offline from the account server. It only trusts the installed signed licenses.

That means:

- a running environment does not need live account connectivity on every command
- repo restarts can continue while the repo license is stale but still valid
- truly expired repo licenses must be refreshed through `rdc`

Machine activation and repo runtime licenses are separate surfaces. A machine can be inactive in account state while some repositories still have valid installed repo licenses. When that happens, inspect both surfaces separately instead of assuming they mean the same thing.

## Recovery Behavior

Automatic recovery is intentionally narrow:

- `missing`: the CLI may authorize account access if needed, issue a repo license, and retry once
- `expired`: the CLI may refresh the repo license and retry once
- `machine_mismatch`: fails fast and tells you to reissue from the current machine context
- `repository_mismatch`: fails fast and tells you to refresh repo licenses explicitly
- `sequence_regression`: fails fast as a repo-license integrity/state problem
- `invalid_signature`: fails fast as a repo-license integrity/state problem

These fail-fast cases do not automatically consume account-backed refresh or issuance calls.

## Monthly Repo License Issuances

This metric counts successful account-backed repo-license issuance activity in the current UTC calendar month.

It includes:

- first-time repo-license issuance
- successful repo-license refresh that returns a newly signed license

It does not include:

- unchanged batch entries
- failed issuance attempts
- untracked repositories rejected before issuance

If you need a customer-facing view of usage and recent repo-license issuance history, use the account portal. If you need machine-side inspection, use `rdc subscription activation-status -m` and `rdc subscription repo-status -m`.
