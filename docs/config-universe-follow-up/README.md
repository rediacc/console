# Config-Universe Follow-Up Big-Bang: Licensing for Clusters, Self-Renewal, and the Testing Substrate

Design documentation for the follow-up big-bang to the 2026-07-23 config-universe campaign
(config = universe, fingerprint licensing + two-level delegation, config transfer). That
campaign is COMPLETE and sits UNCOMMITTED on the working tree; see
`~/.claude/projects/-home-muhammed-monorepo-console/memory/project_bigbang_universe_2026_07_23.md`
and the plan files under `~/.claude/plans/i-want-to-go-velvet-parnas*.md`.

## Read order

1. `01-verified-context.md` : the verified current state, the holes, the numbers
2. `02-licensing-design.md` : the operator-locked model and the designs to implement
3. `03-testing-pillar.md` : the testing work, which comes FIRST
4. `04-integration-contracts.md` : renet / rdc / account consistency contracts
5. `05-execution-guide.md` : staffing, phases, spikes, gates, definition of done

## Non-negotiable working ethos

**Validate, do not believe.** Every file:line reference in these documents was verified
when written, but the tree moves (multiple sessions work here). Treat every claim as a
hypothesis: open the file, run the command, plant a control before trusting any zero
(see the prove-the-instrument memory; the sweep-missed-arrays failure happened twice).
A previous plan's claim about code you have not read is a hypothesis, not a fact.

**Everything stays local and uncommitted.** No commits, no branches, no pushes, no PRs
unless the operator explicitly asks in-task. The tree holds other sessions' work: never
`git checkout/restore/stash/clean`; repair forward.

**Testing and concurrency are first-class deliverables**, not afterthoughts. The testing
substrate (03) lands before the licensing model so the model lands on rails.

**Staffing**: code changes go through writing sub-agents, Opus by default, Fable for the
challenging pieces (listed in 05), Sonnet for translations/naturalization. At most 2
concurrent writers with disjoint file ownership, exact ownership stated in every prompt.

## Scope

**Wave 1, testing substrate** (independent of any model decision):
license-enforcement e2e in CI, tier-map completeness gate, single-source license
contract, un-skip the skipped system suite. Details in 03.

**Wave 2, licensing model**: per-machine slot model confirmed for clusters (no pooling),
fork-metering fix, license self-renewal, slot-race hardening, confluence policy,
clusterId telemetry, failure UX, ToS/pricing/portal surfaces. Details in 02.

**Wave 3, harness + cluster coverage**: scripted drills, cluster CLI verbs live
coverage, the live validation battery. Details in 03 and 05.

**Explicitly OUT of this big-bang** (standing ledger, operator schedules separately):
corpus-wide locale-docs cross-link sweep (`/en/docs/` leakage + inline English),
config-store hardening bundle (COALESCE unique-index migration, 2-round-trips
optimization, member-add command, IP-binding ergonomics, enroll-404 message split),
`invalidSignatureDetected` misnomer rename, on-prem dual-keypair consolidation,
account.team/region retirement (P4), issue #421 tutorial-account integration.
If the operator pulls any of these in at planning time, they attach to Wave 2.

## Operator decision points (ask EARLY, before implementing Wave 2)

1. Fork-metering fix variant: datastore-identity binding (recommended) vs licensed
   fork/attach event vs GUID remint. See 02 section 2.
2. Renewal slot-neutrality: recommended = renewal never claims a slot; only new
   issuance (new guid or new machine) does. Confirm. See 02 section 3.
3. Self-serve cluster availability: none / capped taste / partner-only (recommended:
   partner-only, matching current marketing). Affects pricing page and ToS text.
4. ToS section 5 wording: new Cluster/Node definitions and the Enterprise activation
   ceiling ("up to 25") vs larger negotiated clusters. Operator approves final text.
5. Whether `cluster fork` should consume a repo-license issuance per contained repo or
   a single cluster-level issuance event (interacts with decision 1).
