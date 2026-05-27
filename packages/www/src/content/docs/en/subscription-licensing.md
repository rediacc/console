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

`account` is the source of truth for plans, contract overrides, machine slot state, and monthly repo license issuances.

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

## Machine Slots and Repo Licenses

### Machine slots (server-side)

Machine slot tracking is enforced server-side. When the CLI issues a repo license, the account server checks the subscription's machine slot quota (e.g., 2 machines for Community, 5 for Professional). A slot is held for 1 hour from the last repo license issuance on that machine and auto-releases after inactivity. This means a 5-slot plan can serve dozens of machines over time -- slots are only held while actively provisioning.

No machine license file is stored on the machine. Slot enforcement happens at issuance time on the server.

### Repo license

A repo license is a signed license for one repository on one machine. It is the only license file stored on the machine (`/var/lib/rediacc/license/repos/{guid}.json`).

It is used for:

- `rdc repo create` and `rdc repo fork`, validated before provisioning (pre-issued without identity proofs, then re-issued with identity proofs after creation)
- `rdc repo resize` and `rdc repo expand`, full validation including expiry
- `rdc repo up`, `rdc repo down`, `rdc repo delete`, validated with **expiry skipped**
- `rdc repo push`, `rdc repo pull`, `rdc repo sync`, validated with **expiry skipped**
- repo autostart on machine restart, validated with **expiry skipped**

Repo licenses are bound to the machine and the target repository. Each license contains the machine ID, repository GUID, subscription ID, plan limits, and expiry. For encrypted repositories, Rediacc also verifies the LUKS identity of the underlying volume.

Multiple subscriptions can coexist on the same machine -- each repository carries its own license with its own subscription context.

## Default Limits

Repository size depends on the entitlement level:

- Community: up to `10 GB`
- paid plans: plan or contract limit

Default paid-plan limits are:

| Plan | Floating Licenses | Repository Size | Monthly repo license issuances | Delegation cert default / max |
|------|-------------------|-----------------|-------------------------------|---|
| Community | 2 | 10 GB | 500 | 15d / 30d |
| Professional | 5 | 100 GB | 5,000 | 60d / 120d |
| Business | 20 | 500 GB | 20,000 | 90d / 180d |
| Enterprise | 50 | 2048 GB | 100,000 | 120d / 365d |

Contract-specific limits can raise or lower these values for a specific customer. Delegation cert validity is also hard-capped at `subscription.expiresAt + 3 day grace`, so monthly-billed subscriptions naturally get certs aligned to their billing cycle. See [License Chain & Delegation - Validity Policy](/en/docs/license-chain) for the full rules.

## VM Migration Grace Period

When a hosting provider migrates a VM to different physical hardware, the machine ID changes (it's derived from hardware identifiers like DMI UUID, `/etc/machine-id`, and NIC MAC addresses). Repo licenses are bound to the machine ID, so a migration would normally invalidate all licenses.

To handle this transparently, repo licenses include a **40-day machine ID grace period**. If the machine ID doesn't match but the license was issued less than 40 days ago, the license is still accepted. Since licenses refresh every 30 days, the next refresh automatically binds to the new machine ID.

In practice:
- VM migrated, machine ID changes: repos keep running (within 40-day window)
- Next `rdc` operation refreshes the license with the new machine ID
- No manual intervention required
- Check machine ID and license status with `rdc machine query --system --licenses --name <machine>`

**Edge channel users** receive 2X Community limits at no cost (20 GB repos, 1,000 issuances/month, 4 machines). Paid plans are only available on the Stable channel. See [Release Channels](/en/docs/release-channels) for details.

## What Happens During Repo Create, Up, Down, and Restart

### Repo create and fork

When you create or fork a repository:

1. `rdc` ensures your subscription token is available (triggers device-code auth if needed)
2. `rdc` pre-issues a repo license from the account server (the server checks machine slot quota and monthly issuance limits at this point)
3. The pre-issued repo license is written to the machine and validated locally (signature, machine ID, repo GUID, expiry, and size limit)
4. After successful creation, `rdc` re-issues the repo license with repository identity proofs (LUKS UUID or storage fingerprint)

That account-backed issuance counts toward your monthly **repo license issuances** usage. Each license contains the account holder's email and company name, which is logged when renet validates the license.

### Repo up, down, and delete

`rdc` validates the installed repo license on the machine but **skips the expiry check**. Signature, machine ID, repository GUID, and identity are still verified. Users are never locked out of operating their repositories, even with an expired subscription.

### Repo resize and expand

`rdc` performs full repo license validation including expiry and size limits.

### Machine restart and autostart

Autostart uses the same rules as `rdc repo up`, expiry is skipped, so repositories always restart freely.

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

Batch-refresh repo licenses on a machine:

```bash
rdc subscription refresh repos -m hostinger
```

Repositories discovered on the machine but missing from local `rdc` config are rejected during batch refresh. They are reported as failures and are not auto-classified.

Force a repo-license refresh for an existing repository:

```bash
rdc subscription refresh repo --name my-app -m hostinger
```

On first use, a licensed repo or backup operation that finds no usable repo license can trigger an account-authorization handoff automatically. The CLI prints an authorization URL, tries to open the browser in interactive terminals, and retries the operation once after authorization and issuance succeed.

In non-interactive environments, the CLI does not wait for browser approval. Instead, it tells you to supply a scoped token with `rdc subscription login --token ...` or `REDIACC_SUBSCRIPTION_TOKEN`.

For first-time machine setup, see [Machine Setup](/en/docs/setup).

## Offline Behavior and Expiry

License validation happens locally on the machine, it does not require live connectivity to the account server.

That means:

- a running environment does not need live account connectivity on every command
- all repos can always start, stop, and be deleted even with expired licenses, users are never locked out of operating their own repositories
- provisioning operations (`create`, `fork`) require a pre-issued repo license, and growth operations (`resize`, `expand`) require a valid repo license
- truly expired repo licenses must be refreshed through `rdc` before resize/expand
- license signatures are verified against an embedded public key, signature verification cannot be disabled

## Recovery Behavior

Automatic recovery is intentionally narrow:

- `missing`: `rdc` may authorize account access if needed, batch-refresh repo licenses, and retry once
- `expired`: `rdc` may batch-refresh repo licenses and retry once
- `machine_mismatch`: fails fast and tells you to reissue from the current machine context
- `repository_mismatch`: fails fast and tells you to refresh repo licenses explicitly
- `sequence_regression`: fails fast as a repo-license integrity/state problem
- `invalid_signature`: fails fast as a repo-license integrity/state problem
- `identity_mismatch`: fails fast, the repository identity does not match the installed license

These fail-fast cases do not automatically consume account-backed refresh or issuance calls.

## Delegation Certificates for On-Premise

For on-premise and air-gapped deployments, the upstream account server issues a **delegation certificate** authorizing your on-premise install to sign licenses with its own Ed25519 key. The cert constrains the on-premise to its plan limits and creates a tamper-evident chain.

Key points for subscription owners:

- **One active cert per subscription.** Each on-premise install enforces per-month and per-machine quotas against its own local ledger, so multi-install would multiply the effective quota with no possible reconciliation. Customers needing production + staging + DR must purchase one subscription per install.
- **Tier-based default validity** (15d / 60d / 90d / 120d) and ceilings (30d / 120d / 180d / 365d) - see the limits table above.
- **Self-service from the customer portal.** Org owners and admins can create, renew, and revoke delegation certs at `/account/delegation-certs`. The page is visible to all customers regardless of plan tier - only the limits differ.
- **Auto-renew** is supported via a one-click bootstrap that mints a `delegation:renew`-scoped api token for the on-premise to use for upstream renewal calls.
- **Air-gapped renewal** is supported via a signed renewal request manifest that the on-premise admin downloads, transfers offline to the upstream, and the upstream processes to issue a new cert.

See [On-Premise Installation - Licensing for Air-Gapped Deployments](/en/docs/on-premise) for the operational setup, and [License Chain & Delegation](/en/docs/license-chain) for the cryptographic design.

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
