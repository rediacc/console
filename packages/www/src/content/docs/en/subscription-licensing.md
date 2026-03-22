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
- `rdc` authenticates, requests licenses, delivers them to machines, and enforces them at runtime
- `renet` (the on-machine runtime) validates installed licenses locally without calling the account server

This page explains how those pieces fit together for local deployments.

## What Licensing Does

Licensing controls two different things:

- **Machine access accounting** through **Floating Licenses**
- **Repository runtime authorization** through **repo licenses**

These are related, but they are not the same artifact.

## How Licensing Works

`account` is the source of truth for plans, contract overrides, machine activation state, and monthly repo license issuances.

`rdc` runs on your workstation. It logs you into the account server, requests the licenses it needs, and installs them on remote machines over SSH. When you run a repository command, `rdc` ensures the required licenses are in place and validates them on the machine at runtime.

The normal flow looks like this:

1. You authenticate with `rdc subscription login`
2. You run a repository command such as `rdc repo create`, `rdc repo up`, or `rdc repo down`
3. If the required license is missing or expired, `rdc` requests it from `account`
4. `rdc` writes the signed license to the machine
5. The license is validated locally on the machine and the operation continues

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

Machine activation serves a dual role:

- **Server-side**: floating machine-slot accounting, machine-level activation checks, bridging account-backed repo issuance to a specific machine
- **On-disk**: `rdc` writes a signed subscription blob to `/var/lib/rediacc/license/machine.json` during activation. This blob is validated locally for provisioning operations (`rdc repo create`, `rdc repo fork`). The machine license is valid for 1 hour from the last activation.

### Repo license

A repo license is a signed license for one repository on one machine.

It is used for:

- `rdc repo resize` and `rdc repo expand` — full validation including expiry
- `rdc repo up`, `rdc repo down`, `rdc repo delete` — validated with **expiry skipped**
- `rdc repo push`, `rdc repo pull`, `rdc repo sync` — validated with **expiry skipped**
- repo autostart on machine restart — validated with **expiry skipped**

Repo licenses are bound to the machine and the target repository, and Rediacc hardens that binding with repository identity metadata. For encrypted repositories, that includes the LUKS identity of the underlying volume.

In practice:

- machine activation answers: "can this machine provision new repositories?"
- repo license answers: "can this specific repo run on this specific machine?"

## Default Limits

Repository size depends on the entitlement level:

- Community: up to `10 GB`
- paid plans: plan or contract limit

Default paid-plan limits are:

| Plan | Floating Licenses | Repository Size | Monthly repo license issuances |
|------|-------------------|-----------------|-------------------------------|
| Community | 2 | 10 GB | 500 |
| Professional | 5 | 100 GB | 5,000 |
| Business | 20 | 500 GB | 20,000 |
| Enterprise | 50 | 2048 GB | 100,000 |

Contract-specific limits can raise or lower these values for a specific customer.

## What Happens During Repo Create, Up, Down, and Restart

### Repo create and fork

When you create or fork a repository:

1. `rdc` ensures your subscription token is available (triggers device-code auth if needed)
2. `rdc` activates the machine and writes the signed subscription blob to the remote machine
3. The machine license is validated locally (it must be within 1 hour of activation) — the machine license also enforces the plan's repository size limit, blocking creation if the requested size exceeds the limit
4. After successful creation, `rdc` issues the repo license for the new repository

That account-backed issuance counts toward your monthly **repo license issuances** usage. Each license contains the account holder's email and company name, which is logged when renet validates the license.

### Repo up, down, and delete

`rdc` validates the installed repo license on the machine but **skips the expiry check**. Signature, machine ID, repository GUID, and identity are still verified. Users are never locked out of operating their repositories, even with an expired subscription.

### Repo resize and expand

`rdc` performs full repo license validation including expiry and size limits.

### Machine restart and autostart

Autostart uses the same rules as `rdc repo up` — expiry is skipped, so repositories always restart freely.

Repo licenses use a long-lived validity model:

- `refreshRecommendedAt` is the soft refresh point
- `hardExpiresAt` is the blocking point

If the repo license is stale but still before hard expiry, runtime can continue. Once it reaches hard expiry, `rdc` must refresh it for resize/expand operations.

### Other repository operations

Operations like listing repos, inspecting repo info, and mounting do not require any license validation.

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
rdc subscription activation status -m hostinger
```

Show installed repo-license details on one machine:

```bash
rdc subscription repo status -m hostinger
```

Refresh machine activation and batch-refresh repo licenses:

```bash
rdc subscription refresh -m hostinger
```

Repositories discovered on the machine but missing from local `rdc` config are rejected during batch refresh. They are reported as failures and are not auto-classified.

Force a repo-license refresh for an existing repository:

```bash
rdc subscription refresh repo my-app -m hostinger
```

On first use, a licensed repo or backup operation that finds no usable repo license can trigger an account-authorization handoff automatically. The CLI prints an authorization URL, tries to open the browser in interactive terminals, and retries the operation once after authorization and issuance succeed.

In non-interactive environments, the CLI does not wait for browser approval. Instead, it tells you to supply a scoped token with `rdc subscription login --token ...` or `REDIACC_SUBSCRIPTION_TOKEN`.

For first-time machine setup, see [Machine Setup](/en/docs/setup).

## Offline Behavior and Expiry

License validation happens locally on the machine — it does not require live connectivity to the account server.

That means:

- a running environment does not need live account connectivity on every command
- all repos can always start, stop, and be deleted even with expired licenses — users are never locked out of operating their own repositories
- provisioning operations (`create`, `fork`) require a valid machine license, and growth operations (`resize`, `expand`) require a valid repo license
- truly expired repo licenses must be refreshed through `rdc` before resize/expand
- license signatures are verified against an embedded public key — signature verification cannot be disabled

Machine activation and repo runtime licenses are separate surfaces. A machine can be inactive in account state while some repositories still have valid installed repo licenses. When that happens, inspect both surfaces separately instead of assuming they mean the same thing.

## Recovery Behavior

Automatic recovery is intentionally narrow:

- `missing`: `rdc` may authorize account access if needed, batch-refresh repo licenses, and retry once
- `expired`: `rdc` may batch-refresh repo licenses and retry once
- `machine_mismatch`: fails fast and tells you to reissue from the current machine context
- `repository_mismatch`: fails fast and tells you to refresh repo licenses explicitly
- `sequence_regression`: fails fast as a repo-license integrity/state problem
- `invalid_signature`: fails fast as a repo-license integrity/state problem
- `identity_mismatch`: fails fast — the repository identity does not match the installed license

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

If you need a customer-facing view of usage and recent repo-license issuance history, use the account portal. If you need machine-side inspection, use `rdc subscription activation status -m` and `rdc subscription repo status -m`.
