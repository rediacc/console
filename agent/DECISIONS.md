# DECISIONS: the register of locked decisions, with PREFIXED ids

Status: live Owner: 8f55d4f0 Updated: 2026-09-09

Enforced by `check:ci-decision-ids` (`.ci/scripts/quality/check_decision_ids.py`).

## Why this file exists, and the collision that paid for it

Three id schemes collided on the same-looking token and two adjacent boxes of `agent/PLAN-tooling-transformation.md` ended up pointing at OPPOSITE FILES because of it. `W12 P2.7` cited "A5 in `docs/ci-overhaul/04-decisions.md`", and `grep` for that token in that file returns 0: it meant the GATE RULE in `.ci/scripts/quality/check_plan_boxes.py:41`. Box X0.1 fixed the source on
2026-09-08 by prefixing: gate rules are `G-A<n>`, operator decisions are `D-A<n>`, and a bare `A5` is now wrong in both directions rather than ambiguous in both. This file is the other half: the rows those `D-` ids resolve to.

## The id grammar, and the one shape it deliberately cannot express

An id is `D-<SRC><n>`. `<SRC>` is a source key declared in the table below, `<n>` is the number the SOURCE DOCUMENT itself uses, never a number invented here. That is what makes an id transcribable: a reader who has the source in front of them can derive the id without consulting this file, and a reader who has only the id can find the source.

  | `<SRC>` | Source document |
  |---|---|
  | `A` | `docs/ci-overhaul/04-decisions.md` section A, locked by the operator |
  | `B` | `docs/ci-overhaul/04-decisions.md` section B, decided by recommendation |
  | `S` | `agent/PLAN-secret-namespace-migration.md`, locked by the operator 2026-09-02 |

**The `D-1`..`D-9` labels in `docs/ci-overhaul/04-decisions.md:57-112` are NOT register ids and must never be read as one.** They label section C, "Open decision points", which are questions carrying a recommended default rather than decisions. They have no letter, so the grammar below cannot read `D-6` as a register id at all; only a hurried reader can. The same file's section F
then uses `D8`, `D9` and `D10` (`docs/ci-overhaul/04-decisions.md:184-201`) for something else again, defect ids from an earlier plan, and `docs/ci-overhaul/04-decisions.md:93` carries both on one line (`**D-6. D6: how does a submodule draft PR get flipped ready?**`). Those are left exactly as they are: renumbering a document to suit a register is how a register starts lying about
its sources.

**`agent/PLAN-secret-namespace-migration.md:158`, `:170` and `:193` carry three further rounds of operator rulings numbered `8quater`, `8ter` and `8bis`.** They are rulings, not decisions, and the grammar has no room for them because `<n>` is a number. They hang off `D-S8`'s Notes column with their line numbers rather than being silently dropped, and one of them is the reason
`D-S10` exists at all: `8ter` accepted the naming table with `BACKUP_S3_* -> CLOUDFLARE_R2_BACKUP_*`, and `D-S10` overturned that row the same day.

## What a gate can and cannot enforce here

No gate can tell a good substitution from a bad one. `D-A6` is a standing licence to substitute a better design, and judging the substitution is a reader's job. What a gate CAN assert is the licence's PRECONDITION: that the substitution was stated out loud, at a pointer that resolves, naming the licence it was taken under. So:

  * every cited `D-` id resolves to a row here;
  * every row's `Source` resolves to a real file and line;
  * a row taken under a licence names a row that exists and is itself still `live`;
  * a `superseded-by` ADDED by a change must be cited by a commit in that change.

The last one is the licence half. It cannot stop a bad substitution and does not claim to; it stops a SILENT one.

## The register

| Id | Decision | Source | Status | Licence | Notes |
|---|---|---|---|---|---|
| D-A1 | No personal PAT ever; the GitHub App token is the only long-lived credential | docs/ci-overhaul/04-decisions.md:9 | live | | Anything needing a personal or org-scoped credential is dropped, not deferred |
| D-A2 | Workflow-file edits by an agent are dropped; the autopilot escalates to the human | docs/ci-overhaul/04-decisions.md:12 | live | | |
| D-A3 | Commits are unsigned and attributed to the operator | docs/ci-overhaul/04-decisions.md:14 | live | | Impersonation by configuration, documented as such in docs/ci-overhaul/03-v2-autonomy.md |
| D-A4 | Projects v2 is deferred to a v2 issue, with the reasons recorded | docs/ci-overhaul/04-decisions.md:17 | live | | |
| D-A5 | Three merges from one approval, not one bundle and not three asks | docs/ci-overhaul/04-decisions.md:20 | live | | |
| D-A6 | Standing licence to substitute a better design, provided the substitution is stated out loud | docs/ci-overhaul/04-decisions.md:22 | live | | The licence every `Licence` column below points at |
| D-A7 | One language per folder, reached by a staged port; bash survives only as an allowlisted shim carrying a BLOCKER reason | docs/ci-overhaul/04-decisions.md:24 | live | D-A6 | Stated out loud under the licence because it overturns an earlier ruling of the operator's own, recorded at agent/PLAN-shell-resource-profiling.md:7 |
| D-B1 | Do not buy GitHub Team | docs/ci-overhaul/04-decisions.md:45 | live | | Merge queue on private repos needs Enterprise Cloud; draft PRs are free everywhere |
| D-B2 | The babysit trigger is `workflow_run`; the label is a state flag | docs/ci-overhaul/04-decisions.md:46 | live | | `pull_request.labeled` carries no author identity |
| D-B3 | The E2E matrix is cut from five to two in v1 | docs/ci-overhaul/04-decisions.md:47 | live | | Wall-neutral; safety leans on the nightly |
| D-B4 | Delete coverage rather than revive it | docs/ci-overhaul/04-decisions.md:48 | live | | Reviving needs a baseline store that does not exist |
| D-S1 | Provider-named prefixes; component prefixes stay for values a component owns | agent/PLAN-secret-namespace-migration.md:136 | live | | The vendor is the namespace, because minting and revoking is what you do with these |
| D-S2 | Unify the namespaces: one name everywhere, and the `SECRET_*` shim goes away | agent/PLAN-secret-namespace-migration.md:140 | live | | |
| D-S3 | Bitwarden gets the clean names; GitHub keeps the old ones transitionally | agent/PLAN-secret-namespace-migration.md:143 | live | | No org-secret flag-day, so the rename never needs `admin:org` |
| D-S4 | Backup bucket region-suffixing is fixed standalone, ahead of the rename | agent/PLAN-secret-namespace-migration.md:146 | live | | |
| D-S5 | The two rotation defects fold into the rename PR, not a standalone submodule PR | agent/PLAN-secret-namespace-migration.md:148 | live | | Until it lands, `rotate cf-breakpoint` reports success while pushing nothing |
| D-S6 | `private/growth`'s six uncovered secrets are in scope | agent/PLAN-secret-namespace-migration.md:152 | live | | Needs a coordinated commit on the GitLab remote |
| D-S7 | The leaked `AUTOPILOT_PRIVATE_KEY` stays closed as accepted risk | agent/PLAN-secret-namespace-migration.md:156 | live | | The GPG half of the same round was overturned at agent/PLAN-secret-namespace-migration.md:991, which is a premise, not this ruling |
| D-S8 | R2 token `backup-s3-20260901T103133Z` is kept, then narrowed to the backup buckets only | agent/PLAN-secret-namespace-migration.md:210 | live | | Three further ruling rounds sit at agent/PLAN-secret-namespace-migration.md:158, :170 and :193 and have no id of their own |
| D-S9 | Mint the five; ASIA stays absent on purpose | agent/PLAN-secret-namespace-migration.md:1570 | live | | |
| D-S10 | Both backup families are renamed and `CLOUDFLARE_` comes off the S3 family | agent/PLAN-secret-namespace-migration.md:1745 | live | | Overturns the `BACKUP_S3_* -> CLOUDFLARE_R2_BACKUP_*` row that ruling round `8ter` had accepted the same day |

## Adding a row

Add the row, cite its `Source` as a full path and line, and leave `Status` as `live`. To supersede a row, change its `Status` to `superseded-by D-<id>` and name that id in the commit message. The gate reads the commit range, so the supersession is recorded where a reader of `git log` will find it rather than only where a reader of this file will.
