---
title: "Subscription & Licensing"
description: "Understand how account, rdc, and renet handle machine slots, repo licenses, and plan limits."
category: "Guides"
tags:
  - account
subcategory: account
order: 7
language: en
---

# Subscription & Licensing

So Rediacc licensing breaks down into three moving parts:

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
rdc subscription login --token "$REDIACC_TOKEN"
```

You can also inject the token directly through the environment so the CLI can issue and refresh repo licenses without any interactive login step:

```bash
export REDIACC_TOKEN="rdt_..."
export REDIACC_ACCOUNT_SERVER="https://www.rediacc.com/account"
```

## Machine Slots and Repo Licenses

### Machine slots (server-side)

Machine slot tracking is enforced server-side. When the CLI issues a repo license, the account server checks the subscription's machine slot quota. Every self-serve plan (Community, Professional, Business) includes one machine slot; multi-machine deployments are an Enterprise setup sized with our partners. A slot is held for 5 hours from the last repo license issuance on that machine and auto-releases after inactivity. Because a slot is only held while you are actively provisioning, a single slot can still cover several machines over the course of a month.

The ceiling is read from your subscription record, not from a hard-coded plan constant, so a negotiated activation count is honored as soon as it is set on the subscription. The plan tier only decides the starting value.

Issuance and renewal are enforced differently, and the difference matters:

- **Issuing a new license blocks at the ceiling.** If every slot is taken, the request fails with `MAX_MACHINES_REACHED` and nothing is provisioned.
- **Renewing an existing license never blocks.** A machine that renews while every slot is taken keeps running and its slot is recorded as over limit. You can see this in the portal on the Machines page, in `rdc subscription status`, and in the `overLimitCount` field of the license status API. The flag clears itself once the machine is back inside the limit.

Renewal is deliberately the softer path. A machine renewing a license it already holds is not new capacity, and refusing it would stop backups on infrastructure that was already paid for. What stays blocked is adding capacity.

No machine license file is stored on the machine. Slot enforcement happens at issuance time on the server.

### Repo license

A repo license is a signed license for one repository on one machine. It is the only license file stored on the machine, laid out per datastore and per signing key:

```
/var/lib/rediacc/license/repos/{guid}/{keyId}.json
/var/lib/rediacc/license/datastores/{datastoreId}/repos/{guid}/{keyId}.json
```

Repositories on a machine's default storage use the first path. Repositories in a named datastore use the second, where `{datastoreId}` is the identity that datastore was given when it was created. That scoping is what makes a datastore fork meter honestly: a forked datastore gets a brand new identity, so its repositories start with an empty license population, report `missing` on their first licensed operation, and get their own licenses issued. A repository whose license names a different datastore than the one it is sitting in fails fast as `identity_mismatch` rather than auto-reissuing, which is what stops a license file from being copied sideways.

`{keyId}` is a 16-hex fingerprint (the first 8 bytes of `SHA-256` of the signing server's Ed25519 public key). A repository managed by more than one account universe (for example production and bench deploying to the same box) holds one file per signing key under its `{guid}` directory. The machine's renet build validates only the file its baked key, or a delegation cert chained to it, can verify; other universes' files are inert. Switching universes never invalidates licenses: the first operation in a new universe issues that universe's license once (a `missing` result auto-issues), and both coexist afterwards.

It is used for:

- `rdc repo create`, `rdc repo fork`, and `rdc repo commit`, validated before provisioning (pre-issued without identity proofs, then re-issued with identity proofs after creation, because the repository does not exist yet at the moment of the check)
- `rdc repo resize`, `rdc repo expand`, `rdc repo merge`, and `rdc repo promote`, **fully validated including expiry**
- backup transfer, **fully validated including expiry**: `rdc repo push`, `rdc repo pull`, `rdc repo migrate`, and scheduled backups
- `rdc repo up`, `rdc repo up --all`, `rdc repo exec`, and repo autostart on machine restart, validated with **expiry and the delegation cert window both skipped**
- `rdc repo down`, `rdc repo delete`, and read-only commands such as listing repos need no license at all

Signatures, key binding, machine binding, repository binding, and every delegation cert constraint are enforced on all of these. What the last group relaxes is only the two time windows, so an expired license or a lapsed cert can never stop you running or shutting down your own data.

Repo licenses are bound to the machine and the target repository. Each license contains the machine ID, repository GUID, subscription ID, plan limits, and expiry. For encrypted repositories, Rediacc also verifies the LUKS identity of the underlying volume.

Multiple subscriptions can coexist on the same machine. Each repository carries its own license with its own subscription context.

## Clusters

Clustering is sold through our partners as part of an Enterprise agreement. It is not a self-serve plan option, and the sections below describe how it is metered rather than how to buy it.

**A node is a machine.** A cluster has no licensing identity of its own. Every node in it is an ordinary machine with the Renet Agent installed, and it is counted exactly like a standalone machine.

**There is no pooling.** A five-node cluster does not draw from one shared cluster slot. Each node claims its own slot the first time a repository is placed on it, and that slot follows the same 5-hour float as any other: it is held for 5 hours from the last repo license issuance on that node and releases on its own after that.

**Building the cluster is free. Placing repositories is what meters.** Creating the cluster, joining nodes, installing the distributed storage layer, and standing up the Kubernetes control plane cost no slots. Metering starts when a repository lands on a node.

**A cluster fork re-meters per repository.** Forking a whole cluster gives the forked datastore a new identity, so each repository in the fork gets its own license the first time it is touched, on whichever node it is running. Plain migration is the opposite case: moving a repository between machines carries its license with it and keeps validating, because nothing about its storage identity changed.

**Renewal on a cluster follows the soft-claim rule above.** Nodes renew their own licenses unattended, so a cluster that has grown past its activation count keeps running and reports its over-limit nodes rather than failing backups in the middle of the night. Adding a new node still blocks at the ceiling.

Sizing a cluster is a conversation, not a checkbox. Activation counts for clusters are agreed in the order, and your partner sets them on the subscription directly. See [Contact](/en/contact) to start that conversation.

## Default Limits

Repository size depends on the entitlement level:

- Community: up to `10 GB`
- paid plans: plan or contract limit

Default paid-plan limits are:

| Plan | Floating Licenses | Repository Size | Monthly repo license issuances | Delegation cert default / max |
|------|-------------------|-----------------|-------------------------------|---|
| Community | 1 | 10 GB | 100 | 15d / 30d |
| Professional | 1 | 100 GB | 2,000+ | 60d / 120d |
| Business | 1 | 500 GB | 5,000+ | 90d / 180d |
| Enterprise | Custom | 1 TB+ | 15,000+ | 120d / 365d |

Contract-specific limits can raise or lower these values for a specific customer. Delegation cert validity is also hard-capped at `subscription.expiresAt + 3 day grace`, so monthly-billed subscriptions naturally get certs aligned to their billing cycle. See [License Chain & Delegation - Validity Policy](/en/docs/license-chain) for the full rules.

## Free Trial and the Community Fallback

New signups start a 14-day free trial on Professional or Business. A credit card is collected at signup, and the first charge only lands when the trial ends, so cancelling before then costs nothing. One trial is available per customer.

Community is the standing free floor. It is no longer a direct signup option for new accounts; instead, an account lands on Community whenever a subscription ends: cancelling during the trial, cancelling a paid plan later, or a failed payment. On the Community fallback you keep one machine with 10 GB per repository and 100 setups a month. Accounts created before the trial-based model launched keep their existing Community access.

Enforcement stays soft where it matters most: running repositories keep working even after a subscription ends (`up`, `down`, `delete`, autostart). Beyond that, two different rules apply, and mixing them up is what makes the 60-day grace look inconsistent:

- **Operations that need the account server** cannot happen without an active subscription, because the server refuses to sign. That is `create`, `fork`, and any license refresh or renewal. Nothing new gets provisioned once the subscription lapses.
- **Operations that only need a valid installed license** keep working until that license hard-expires, with no server involved. That is `resize` and `expand` on repositories you already have, and backup transfer (`push`, `pull`, scheduled backups). A repository's primary license hard-expires 60 days after the subscription end date, which is where the 60-day grace comes from. A fork's license is much shorter-lived, capped at 7 days, which is why fork-heavy machines depend on the self-renewal described below.

So a lapsed subscription stops you growing your fleet immediately, and stops you growing the repositories in it 60 days later.

## VM Migration Grace Period

When a hosting provider migrates a VM to different physical hardware, the machine ID changes (it's derived from hardware identifiers like DMI UUID, `/etc/machine-id`, and NIC MAC addresses). Repo licenses are bound to the machine ID, so a migration would normally invalidate all licenses.

To handle this transparently, repo licenses include a **40-day machine ID grace period**. If the machine ID doesn't match but the license was issued less than 40 days ago, the license is still accepted. Since licenses refresh every 30 days, the next refresh automatically binds to the new machine ID.

In practice:
- VM migrated, machine ID changes: repos keep running (within 40-day window)
- Next `rdc` operation refreshes the license with the new machine ID
- No manual intervention required
- Check machine ID and license status with `rdc machine status <machine> --system --licenses`

**Edge channel accounts** run on the Community plan with 2X the limits (20 GB repos, 200 setups/month, 2 machines). Paid plans are only available on the Stable channel. See [Release Channels](/en/docs/release-channels) for details.

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

Autostart uses the same rules as `rdc repo up`: expiry is skipped, so repositories always restart freely.

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
rdc subscription login --token "$REDIACC_TOKEN"
```

For non-interactive environments, setting `REDIACC_TOKEN` is the simplest option. The token should be scoped only for the subscription and repo-license operations the agent needs.

Show account-backed subscription status:

```bash
rdc subscription status
```

Show machine activation details for one machine:

```bash
rdc subscription status -m hostinger
```

Show installed repo-license details on one machine:

```bash
rdc subscription status -m hostinger
```

Refresh a repository's license on a machine:

```bash
rdc subscription refresh -m hostinger --repo my-app
```

The `--repo` ref must resolve in your local `rdc` config. A repository discovered on the machine but missing from local config is rejected: it is reported as a failure and not auto-classified.

On first use, a licensed repo or backup operation that finds no usable repo license can trigger an account-authorization handoff automatically. The CLI prints an authorization URL, tries to open the browser in interactive terminals, and retries the operation once after authorization and issuance succeed.

In non-interactive environments, the CLI does not wait for browser approval. Instead, it tells you to supply a scoped token with `rdc subscription login --token ...` or `REDIACC_TOKEN`.

For first-time machine setup, see [Machine Setup](/en/docs/setup).

## License Self-Renewal

Everything above assumes you are at a keyboard. Scheduled backups are not, and that is the case self-renewal exists for.

A scheduled backup validates at the strict tier, so it needs a license that has not expired. A fork's license is capped at 7 days. Your machines hold no account credentials by design, so before self-renewal a fork's backup simply stopped a week after it was created, quietly, at three in the morning.

### How a machine renews without holding a token

Every license Rediacc issues or renews carries a `renewalUrl`, the full address of the renewal endpoint on the account server that signed it. A machine reads that address out of its own installed license, so it never has to be told where its account server is.

The machine then presents the installed license back to that endpoint. The license is its own credential: it is signed, the server verifies that signature, and no API token is involved anywhere. The server returns a fresh license with new validity windows, and the machine installs it and re-validates it before considering the renewal done.

Renewal is a machine-wide operation:

```bash
sudo renet license renew
```

Repositories are grouped by the server that signed them, so a machine serving two account universes contacts each one once. A lock file keeps two renewals from running at the same time, and `--jitter` spreads a fleet of machines that would otherwise all wake on the hour.

The server refuses a renewal in three cases, and each one means something different:

| Refusal | What it means |
|---|---|
| The subscription has lapsed, is suspended, or is past its grace period | Billing. Renewal resumes on its own once the subscription is active again |
| The delegation cert is expired or revoked | On-premise setup. Renew the cert on your on-premise server, then the machines renew normally |
| The machine identity no longer matches and the 40-day grace has passed | The license belongs to a machine this one is not. Reissue from the current machine context |

A refusal never stops the whole run. One lapsed repository does not block the renewal of the others on the same machine.

### Scheduled backups renew themselves

Every backup unit Rediacc writes runs a renewal first:

```
ExecStartPre=-<renet> license renew --jitter 45s
```

The leading `-` marks it as best effort on purpose. A refused renewal, a network blip, or an older Renet Agent that does not know the command yet must never take out the backup itself. The backup runs, and the license is renewed on the way in whenever it can be.

### When a backup is blocked

If licensing does refuse a backup, the machine records it. That marker is the only signal that unattended backups have stopped copying data, so it is surfaced loudly:

```bash
rdc machine status <machine> --licenses
```

The `backups` column reads `BLOCKED` with the reason, and the same information is printed under the table as an error so it is not lost among thirty repositories. The `renewed` column shows how the last unattended renewal went, including the server's refusal code when there was one, which is what tells you whether the fix is a billing question or an on-premise cert question.

A successful renewal clears the marker, and so does a backup that passes its license check. There is nothing to acknowledge or reset by hand.

## Offline Behavior and Expiry

License validation happens locally on the machine. You don't need to contact the account server to operate your repositories.

That means:

- a running environment does not need live account connectivity on every command
- all repos can always start, stop, and be deleted even with expired licenses, users are never locked out of operating their own repositories
- provisioning operations (`create`, `fork`) require a pre-issued repo license, and growth operations (`resize`, `expand`) require a valid repo license
- truly expired repo licenses must be replaced before resize/expand, either through `rdc` from your workstation or by the machine renewing itself
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
- `cert_expired`: fails fast on growth operations (`create`, `fork`, `resize`) and on backup transfer (`push`, `pull`); `repo up` and autostart keep working, matching the soft license-expiry model. Renew the delegation cert
- `cert_invalid`: fails fast, the delegation cert failed a constraint (bad master-key signature, subscription/plan mismatch, size cap, or sequence over `maxTotalIssuances`). Reissue the cert after fixing the underlying limit

These fail-fast cases do not automatically consume account-backed refresh or issuance calls.

Two notes on reading this list:

- `missing` is not always a problem. It is also the normal result the first time a repository is touched inside a freshly forked datastore, and it is exactly what makes that fork meter: the license is issued, a slot is claimed, and the operation continues. `identity_mismatch` is the deliberate opposite, so a license file copied from another datastore fails fast instead of being quietly reissued.
- This list describes recovery from your workstation. A machine renewing itself has its own outcomes, reported by `rdc machine status <machine> --licenses` rather than raised as a command failure, because a scheduled backup has nobody to tell.

## Delegation Certificates for On-Premise

For on-premise and air-gapped deployments, this gets complex. The upstream account server issues a **delegation certificate** that authorizes your on-premise install to sign licenses with its own Ed25519 key. This constrains you to your plan limits and creates a tamper-evident chain.

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

If you need a customer-facing view of usage and recent repo-license issuance history, use the account portal. If you need machine-side inspection, use `rdc subscription status -m` and `rdc subscription status -m`.
