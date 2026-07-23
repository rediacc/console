# 02. Licensing Design

Operator-locked decisions first, then the designs. Anything marked RECOMMENDED needs a
one-question confirmation at planning time; anything marked SPIKE needs a short
verification before implementation.

## Locked by the operator (do not relitigate)

- Per-machine slots, floating 5-hour window, NO cluster pooling. Each cluster machine
  is one slot when forking or creating repos. Infrastructure provisioning stays free;
  repo placement meters.
- Backup transfer (`push`/`pull`/`sync`, scheduled backups) KEEPS the strict full-
  validation tier. Do not re-soften it. The staleness gap is closed by self-renewal
  (section 3), not by weakening validation.
- The two-tier validation model from the previous campaign stands (Operate vs Full).

## 1. Tier map becomes explicit and total

Replace the fail-open `default: TierNone` with a total, explicit classification:
every registered renet function (walk the registrations under
`pkg/functions/commands/`) appears in ONE tier map with an explicit tier, including
`TierNone` as a recorded decision. Cluster/datastore/kube/ceph verbs are explicitly
`TierNone` under the locked model (metering happens at repo issuance), with one
exception introduced by section 2. The completeness gate in 03 (T2) enforces totality
forever. The CLI derives its licensed-function knowledge from this map via the
generated contract (04), killing the prefix heuristic.

## 2. Fork-metering fix (closes hole 1)

Intent: a fork is a licensed event ("each fork = a slot claim"), including datastore
and whole-cluster forks, including same-node forks.

RECOMMENDED variant: **bind repo licenses to datastore identity**.
- Make fork identity real on disk: `datastore fork` (or first `attach` of a fork)
  writes the fork's own registry key (`<parent>:<tag>`) into the cloned descriptor
  (`.rediacc/datastore.json` Name field; today the clone keeps the parent's).
  SPIKE: confirm where attach mounts the clone and the safe write point; confirm the
  descriptor is inside the snapshot scope so nested forks chain correctly.
- Add a datastore-identity field to the repo-license payload (issued by account,
  validated by renet exactly like `luksUuid`/`storageFingerprint`: mismatch =
  `identity_mismatch`, fail fast). The CLI supplies the datastore identity at
  issuance (it already supplies luksUuid and storageFingerprint; find the scan in
  `repository_license_scan.go` and `license.ts` issuance body).
- Effect: a clone's repos carry the parent's datastore identity in their inherited
  license files but live in a datastore whose identity now differs, so validation
  fails closed as `identity_mismatch`, the CLI reissues on first touch, issuance
  claims the slot. Same-node forks meter; cross-node forks already metered.
- Rejected alternatives, for the record: making `datastore_fork` itself a licensed
  event (needs account reachability at fork time, breaks the offline-fork property);
  GUID remint at fork (touches every GUID consumer: state mirror, compose naming,
  backup lineage; far too invasive).
- Grace: the fix must NOT break plain datastore MIGRATION (same datastore, new node):
  identity travels with the datastore, so migration keeps validating; only forks
  (new identity) re-meter. Add tests for both directions.
- Interaction with operator decision point 5 (README): with this variant, cluster
  fork meters via per-repo reissuance on first touch, which is the locked model's
  natural reading. A single cluster-level issuance event would need decision 1
  revisited; default to per-repo.

## 3. License self-renewal (closes the scheduled-backup trap and hole 2)

Problem recap: machine-local scheduled backups validate strictly, licenses refresh
only via CLI touches, fork licenses hard-expire in 7 days, renet holds no credentials.

Design: **the current signed license blob IS the renewal credential.**
- New account endpoint `POST /account/api/v1/licenses/renew`: body carries the current
  signed blob (and the machine's current machineId). Server verifies the blob's
  signature (master or delegated chain, reuse existing validation), verifies the
  machineId matches the blob (40-day grace semantics as in renet), checks the
  subscription is still active/entitled, then returns a fresh signed blob (same guid,
  same kind, bumped sequence/chain, new windows). Refusals: lapsed subscription,
  revoked cert, identity mismatch. No session, no api-token: the blob is the bearer.
  Airlock the response DTO like every other route.
- RECOMMENDED slot policy: renewal is SLOT-NEUTRAL. It never inserts an activation
  row; at most it touches `lastSeenAt` of an existing row. Only NEW issuance (new
  guid, or first issuance for a machineId) claims a slot. This makes slots meter
  setup, not heartbeats, and defuses the refresh-confluence cliff at the root.
- renet: new `renet license renew` command: loads the installed per-key blob(s) for
  its repos, calls the renew endpoint (server URL source: SPIKE, see below), writes
  the refreshed blobs atomically alongside existing per-key files. Add jitter so
  fleets do not thundering-herd.
- Server URL on the machine: renet knows no account server today. Options: embed the
  renewal URL in the license payload at issuance (RECOMMENDED: server self-describes,
  works for cloud and on-prem/delegated automatically, air-gapped installs point at
  the on-prem server); or a config file dropped by the CLI at deployment. SPIKE both,
  prefer the payload field.
- Scheduled-backup unit integration: the generated units gain a best-effort
  `ExecStartPre=<renet> license renew ...` (never fails the backup by itself), plus a
  LOUD persistent failure marker when a backup is blocked by licensing: mirror the
  reconcile pattern (`/var/lib/rediacc/reconcile/failed/<guid>`), e.g.
  `/var/lib/rediacc/license/failed/<guid>` with the reason payload. Surface it in
  `machine status --licenses`.
- CLI: `rdc subscription refresh` stays; proactive refresh stays; renewal is additive.
- Concurrency: renewal must be idempotent and safe under races (two units renewing the
  same blob concurrently; renewal racing a CLI refresh). Sequence/chain semantics:
  server bumps sequence per renewal; renet's equal-sequence rule (equal seq + equal
  chainHash passes) already tolerates same-blob re-reads; ADD tests for interleaved
  renewals (04 covers the contract).

## 4. Slot-race hardening (closes hole 3)

Make the activation cap enforcement correct under parallel first-time issuances:
transactional insert-with-count or a compensating check after insert (D1/SQLite lacks
multi-statement transactions in this path; the config-store seed race in
`config.service.ts` documents the same constraint). Acceptable outcome: small
overshoot prevented by unique-index plus recount-and-reject-or-release; deterministic
tests required either way (03). Also add jitter guidance for CLI batch refresh across
machines.

## 5. Cluster identity telemetry (closes hole 7)

`activate-repo`/`activate-repo-batch` (and `renew`) gain an OPTIONAL informational
`clusterId` (the cluster CA fingerprint when the machine belongs to a cluster; the CLI
reads membership from its config). Stored on the activation row and license audit
events. No enforcement semantics in this big-bang; it exists so support, analytics,
and any future policy can see cluster context.

## 6. Failure UX and pre-flight (closes hole 6)

- CLI pre-flight for cluster provisioning and any multi-machine placement: before
  issuing, compare machines-about-to-issue against `maxActivations` and live slot
  state from `/licenses/status`; fail early with a message that names the limit and
  the Enterprise/partner path. No server round-trip semantics change.
- `MAX_MACHINES_REACHED` error copy (server and CLI guidance): say what it means, the
  5-hour window, and the upgrade path.
- Define and test the mid-provisioning failure state: what exists after a partial
  cluster placement stops at the wall, and what the user runs next.

## 7. Public surfaces (docs, pricing, ToS, portal)

All copy changes ride the same rules as the previous campaign: English first, then the
12-locale naturalization delta by a Sonnet agent, hashes/ledgers updated, search index
regenerated, zero em dashes anywhere including CJK/RU.

- `subscription-licensing.md`: new section on clusters (nodes are machines; bursts;
  the renewal mechanism; fork metering). `license-chain.md`: renewal endpoint.
- Pricing surface: cluster positioning stays partner/Enterprise per operator decision
  point 3; FAQ entry for "how are cluster nodes counted".
- ToS section 5: Cluster/Node definitions, activation wording, the Enterprise ceiling
  question (operator approves text; do not invent legal language silently).
- Portal: Machines page shows activation rows; consider labeling cluster membership
  (via clusterId telemetry) as a small enhancement; eval-license grants for cluster
  POCs need slot counts (partner flow input).
- Verify-and-close: the "60-day grace" claim vs the grand +60d hard-expiry window
  (01); if they match, align the copy explicitly and close the ledger item.
