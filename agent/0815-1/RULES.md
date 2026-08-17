# RULES: branch 0815-1

Carried forward from `backup-storage`, which is where this campaign was built. The branch
was renamed at PR time to match the repo's `MMDD-N` convention; the work is identical.

**The tree is now COMMITTED and pushed.** Four PRs are open (console#568 draft, renet#103,
account#79, elite#15), so the shared-checkout hazards below have changed shape: uncommitted
work is no longer the thing to protect, a pushed branch is. That means: never force-push,
never amend a pushed commit, never push `main`, and never merge -- `/pr-merge` is the
operator's call, not this loop's.

This file is the branch's DURABLE memory. It is not freshness-gated, so it
holds what stays true; `STATE.md` holds what is true right now and goes stale by
design. If a line here would still be true next month, it belongs here. If it
would be wrong tomorrow, it belongs in STATE.md.

Written by the session that owns this branch. Session 2fd369e0's section at the
bottom is theirs; leave it byte-for-byte.

## Rules that cost real money on this branch

Each one was paid for once, in a live run or a live tree. They are written as
orders rather than observations because the reader is usually a fresh context
deciding fast.

- **NEVER narrow `BackupDestinationSchema`.** `kind` carries
  `.default('storage')`, and production holds a destination with no `kind` field
  at all. Narrowing the union makes that config unreadable, which bricks config
  load for the one machine that matters.
- **Deploy account and renet TOGETHER** (`docs/backup-storage/08-cutover-runbook.md`
  section 0.1). SigV4 presigned URLs sign their headers, so the server and the
  client have to change in the same step or every upload 403s.
- **For cold specifically, deploy renet BEFORE the generator.** A unit emitting
  `--cold` against an older renet dies at cobra's flag parse, inside a timer, at
  03:00, and surfaces only as a backup that silently never ran.
- **i18n: re-translate FIRST, hashes SECOND**, then regenerate the CLI contract.
  Generating hashes early marks stale translations as current and the gate then
  certifies the wrong text forever.
- **A garbage collector may only ADD reasons to keep a file, never remove one.**
  The first prune cut here REPLACED the repo-lock probe with the staging-lock
  probe and broke two tests that were right; a live upload's staging file read as
  abandoned junk, and prune deletes what it finds stale.
- **A cold backup must REFUSE, never degrade.** Every path that stops containers
  takes the datastore cold lock first, and a repo that did not actually quiesce
  is refused rather than snapshotted hot. A hot snapshot wearing a cold label is
  discovered at restore, which is the worst possible time.

## How work is proved on this branch

The campaign's defects have a signature: **the check ran, went green, and was
looking at nothing.** So proof here is narrower than "the tests pass".

- **Run the real thing before you claim it.** Every one of the cold path's three
  worst bugs survived a full unit suite and died in the first live run on an ops
  VM: staging that could never succeed, an outage paid before an unlicensed
  repo was refused, and a barrier reporting `1 repositories quiesced` while the
  fixture container never missed a sample.
- **A test's FIXTURE is part of the system under test.** That last bug was
  invisible because the discovery fake returned the same repos forever, so a
  barrier that stopped nothing looked exactly like one that stopped everything.
  When a live run finds something a unit test should have caught, fix the
  fixture, not just the code.
- **Mutate the check before you trust it.** Break the thing on purpose and watch
  the check go red, then restore. A gate that has never failed in front of you
  is a gate you are guessing about. Both directions matter for a conditional:
  always-on and always-off are different bugs.
- **Ask what the check was LOOKING at.** Both shell gates passed a file carrying
  a blatant error because they walked four hardcoded directories and the file sat
  outside them. Prefer an enumerator (`git ls-files`) over a list of roots, and
  make any gate refuse an empty input set, because linting nothing exits 0
  exactly like linting everything.
- **Read the artifact, not the report.** Subagent summaries here have been wrong
  in both directions: one abbreviated its output so correct files looked broken,
  another's differential was honest but blind to a defect present on BOTH sides.
  Check the file.

## Working in this tree

- **The tree is shared and uncommitted.** Never `git checkout`/`restore`/`stash`/
  `clean` to undo your own mistake; repair forward. Other sessions' work is in
  here and it has no other copy.
- **Verify a worker is alive by its OUTPUT STREAM, never by a roster.** The
  harness's running-task list keeps entries after the process is gone. A session
  read that list literally, concluded a dead worker was alive, and came one
  command away from pointing a second writer at its files.
- **Two writers, disjoint files, named explicitly.** State the exact file list a
  writing agent owns and forbid everything else.

## What 2fd369e0 built here (COMMITTED 2026-08-15 in 0815-1, note kept for provenance)

**These are no longer uncommitted and no longer carved out.** The operator ruled that all
uncommitted work in this tree is one wave's, including work from earlier sessions and from
before a compaction: *"all the changes are YOURS, including the Pre-compact changes."* All
five shipped in `0815-1` as their own labelled commit. The heading below is kept because
the provenance is worth knowing when reading that commit, not because anything is reserved.

## What 2fd369e0 originally contributed

Five uncommitted hardenings that rode across the branch switch, all built
2026-08-09 during the autopilot wave and kept local by operator ruling:

- `.ci/scripts/quality/check-label-inventory.sh` — GitHub's 100-char label
  description cap, control-first.
- `.ci/scripts/quality/check-workflows.sh` — bans `gh --slurp` combined with
  `--jq` (the runner's gh rejects it; local gh accepts it).
- `.ci/scripts/security/check-autopilot-workflow-invariants.sh` +
  `.ci/scripts/test/gates/test-autopilot-workflow-invariants.sh` —
  `model-round-file-tools` invariant and its mutation case.
- `.ci/scripts/quality/check-submodule-branches.sh` — submodule-PR review
  REPORT must be answered (closes the account#78 hole).

Everything else dirty in this tree belongs to other sessions.
