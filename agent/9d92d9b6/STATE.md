## SESSION legacy 2026-08-28T09:17:20Z (adopted from a pre-section document)

# 9d92d9b6 — wave 0827-1, epic `f2757830`, PR #579 (DRAFT)

`origin/0827-1` = `3dbdfbb1f`. Local head `9d3dd06dc`, 1 commit unpushed.

## The PR wave is DONE

Trailer green (`all 84 commits name a known epic`), `.ci/config/carried-reds.json`
EMPTY, first fully green receipt (exit 0, stable, whole). Submodule PRs open and
review-answered: **rediacc/account#83**, **rediacc/renet#109**. Operator ruled
review starts only AFTER CI is green.

## Two agents landed. BOTH sets verified against the artifact, not on report.

**Ladder set** (`wl_checks.py`, `wl_wait.py`, `worklist_messages.py`,
`worklist-cases/{01,05,08,14,15,21,23}.sh`, `test-always-tier.py`, registrations
in `test-worklist-v5.sh` + `test-hooks.sh`). Staged. My independent run: **854/0**.

**Judge set** (`wl_judge.py`, `test-judge-schema.py`, new `wl_bravedefault.py`,
`wl_classsweep.py`, `wl_rules.py`, `calibrate-judge-rules.py`). NOT yet staged.
**141 controls**, live calibration 14/14 against real haiku.

## What verification actually caught (all three would have shipped silently)

1. **`check:ci-python-lint` was RED on `wl_checks.py`** — my own about-to-commit
   file, found only because the judge agent reported it. Format-only, fixed by
   `ruff format` on THAT ONE FILE (the gate's advice names all 66; running it
   would have rewritten peer files).
2. **The always-tier is NOT inflated — my alarm was a broken grep.** `grep` can't
   span multiline `vadd(` calls, so "7 before / 8 now" was wrong. AST comparison:
   **21 → 27**, added `no-waiter`, `no-waiter-asked`, `requests` (the three
   planned promotions), `unread-reports` (planned graduation), `waiter-lapsed`
   (new, from the tombstone), `pr-finish` (the operator's open-PR-red mandate).
   Nothing removed. Defensible set.
3. **The deepcopy was a comment, not a contract.** All four pre-existing
   non-mutation controls assert MEMBERSHIP of one key, and the builder only
   rebinds `required` to a fresh list — so every one survived a shallow copy.
   10 new controls pin it. **I planted M9 myself:** `deepcopy → dict()` gives
   exactly 2 reds naming the shared nested objects; restore byte-identical; 141.
   e580532b re-verified independently and agreed: *"I wrote a comment claiming a
   contract and a control that could not fail on it."*

## The DEFAULT wording: the class was wider than either of us said

My note said 4 sites (103/127/217/**1563**). `1563` does not exist. The agent
found **5** exact-literal sites (103, 127, 217, 1614, 2218). Sweeping the class
myself found **5 MORE** timid variants — `:166`, `:272`, `:1032`, `:1465`,
`:1495` — of which `:272`'s `<what happens if nobody acts>` is the worst, passive
voice inviting "nothing". All ten now read
`DEFAULT: <the ACTION you take alone if unanswered -- 'hold' is not one>`.
Three `<action>` sites were already correct and left alone. Whole file re-parsed;
zero timid placeholders remain.

## Placement drift in agent reports (CLAUDE.md rule 4, confirmed again)

Every BEHAVIOR the judge agent claimed is present; its line refs drift ~30 lines.
`judge_schema_for` is at `wl_judge.py:604` (claimed 617); the `evidence_kind:
none` fire logic is at `wl_classsweep.py:263` (claimed 229) and is correct —
`swept: true` with `evidence_kind none` counts as NOT swept, the operator's
"evidence, not assertion" made mechanical.

## Open question, hypothesis only

Agent reported "5 stop-suite failures, base 833/5". My run: 854/0. Its cases
failed **rc=127** (command not found) and it installed `ruff` partway through.
Likely environment, not code. The in-flight re-run settles it — do not report
either number as fact until it lands.

## Verify-don't-trust: tools that lied this session

1. `worklist.py --git force-push --execute` printed "2 command(s) ran" and pushed
   nothing — it HALTS at the TOP, so `| tail` hides it. **Verify with
   `git ls-remote`.** Fixed.
2. A dead scan read identical to a clean one (`|| true` ate the status).
3. `ci_watch_armed` has ONE call site, after a job already failed.

Read CI with `.ci/scripts/ci/ci-trace.py`, never raw `gh`: a `success` run may be
**Watchdog Monitor**, and a one-job run is never full CI.

## LANDED

- **`12de2e910`** ladder set, 13 files. Suite re-run after `ruff format`: **854/0,
  exit 0**.
- **`f4b1e...`** judge set, 6 files (see `git log`). 141 controls, M9 planted and
  restored byte-identical.

## `git commit -F` COMMITS THE INDEX. It bit me TWICE in one session.

1. It swept two of a peer's STAGED files into `449b95f09`.
2. I staged `worklist_messages.py`, THEN made the DEFAULT edits, then committed:
   `12de2e910` does **not** contain the wording change its own message claims.
   Audited the rest of that message — `--timeout 900 -> 60` IS in it, always tier
   27 IS in it, only the wording claim is not. The tree has all 10 sites; they
   land in the next commit.

**No hook guards this.** `.claude/hooks/pre-bash/` has 7 git guards and none
checks whether a staged path was edited afterwards. Adding
`warn-stale-index.sh`: paths in BOTH `diff --cached --name-only` and
`diff --name-only` commit their STALE version while the message describes disk.

## IN FLIGHT / UNCOMMITTED

`wl_git.py`, `test-hooks.sh` (floor 40 -> 55), `worklist_messages.py` (the 10
DEFAULT sites). Held until `test-hooks.sh` reports — it is the gate that would
have caught the force-push rot and it has been red.

## The force-push probe trio was RED and UNREACHABLE, by my own earlier fix

Fixture hardcoded branch `0826-3` from a previous wave. Once that branch was gone
AND force-push learned (correctly, my fix) to skip a submodule lacking the
branch, every submodule was skipped and `staged_deletions` was never called.
Branch now read from the repo; three `CONTROL: ... REACHED the probe` assertions
added. Replanting `0826-3` fires all six reds. **57 PASS/3 FAIL -> 63 PASS/0
FAIL.** Floor bumped 40 -> 55 per that file's own policy.

## TWO DEFECT CLASSES SWEPT (#e6e76009), not two instances

**Class A — mention-vs-target.** My own new `warn-stale-index.sh` reintroduced it
within the hour: `echo do not run git commit here` WARNED. Sweeping found a LIVE
sibling — **`block-git-empty-commit.sh` BLOCKED (exit 2) on prose**. Its own
header says it was routed through `command-scan.sh` to stop matching prose; that
fixed the QUOTED case only. `hook_scan_target` strips quoted spans, so an
unquoted sentence survives to a matcher that looked ANYWHERE. Both anchored to
command position. Probed from a FILE — running the strings inline makes the
harness its own subject and the chain refuses it. **BEFORE: 2 FAIL. AFTER: 6/6,
all four blocking controls still blocking.** `block-untagged-commit.sh` and
`block-commit-meta.sh` probed clean.

**Class B — controls pinned to ambient machine state.**
`test-block-host-toolchain-run.py` hardcoded `want=2` for `private/renet` and
went red the moment `ruff` was installed on this host mid-session; the guard then
correctly declined to route, exactly as its own *THE HOST IS ASKED, NOT ASSUMED*
comment says. Expectation now DERIVED from the same fact the guard uses.
Inverting the derivation fires the red; restore byte-identical. Same class as
`wl_git`'s force-push trio (branch `0826-3` from an earlier wave), hours earlier.
Swept the rest: the `0826-x` literals in `test-hooks.sh` are command STRINGS
parsed by hooks, not ambient state — probed `block-unverified-push` with a
non-current branch to confirm (both exit 0). **Class has exactly 2 members, both
fixed.**

Neither went green and lied. Both went RED for a reason unrelated to what they
assert, which is worse: a red nobody can explain is a red everybody learns to
ignore.

## Next action

1. Definitive suite `bsvsgpdl3` (prev run was PASS=1730 FAIL=1, that 1 now
   fixed) → then ONE commit: `wl_git.py`, `test-hooks.sh`, `worklist_messages.py`,
   `warn-stale-index.sh`, `block-git-empty-commit.sh`,
   `test-block-host-toolchain-run.py`, `settings.json`.
   **Re-stage every path immediately before committing** — the stale-index
   defect above is exactly what bit `12de2e910`.
2. Push, then `ci-trace.py` on the new head; when green `gh pr ready` #579,
   request review, resolve threads. **Never merge, never push `main`.**

## SESSION 9d92d9b6 2026-08-28T09:39:46Z

Wave 0827-1, epic `f2757830`, PR #579 (DRAFT). `origin/0827-1` = `da2ecc5b5`,
verified with `git ls-remote`, not with the tool that claims the push. Both
submodules (rediacc/account#83, rediacc/renet#109) have 0 unpushed.

## Four commits landed and pushed

- `12de2e910` priority ladder. Independent suite 854/0, re-run after formatting.
- `609314a41` two judged rules (sweep-the-class, brave defaults). 141 controls.
- `0583b1690` two guards that matched a MENTION; two controls that could not be REACHED.
- `da2ecc5b5` formatters, plus two reds named in carried-reds.

`test-hooks.sh` = **PASS=1737 FAIL=0** (was 1730/1).

## UNCOMMITTED, verified, needs one commit + push

`scripts/ci-runner/manifest.ts` — `check:ci-landmarks` and `check:ci-ssr-locale`
gained `slow: true` + `needs: ['build:www']`, and
`.ci/config/carried-reds.json` is back to EMPTY (mandatory: a carried entry
whose gate stops failing is stale and REFUSES the next push).
Also `agent/PLAN-local-ci-gate-prerequisites.md` (Status: executing).

Both gates now report DEFERRED, not failed. Green: `check:ci-parity` (323 gates,
both directions), `check:ci-gate-manifest` (323 entries), runner selftest (21).

## Next action

1. Read `ciq4.out` (task `bdowtcx7g`). The receipt must show `failed: []`.
   `check:ci-gate-manifest` was the last failure and is now green.
2. Commit the manifest + carried-reds + plan, then push. **Re-stage every path
   immediately before committing**: `git commit -F` commits the INDEX, and a
   path staged then edited commits its stale version. That bit `12de2e910`,
   whose message claims a DEFAULT rewording the commit does not contain.
3. Read CI with `.ci/scripts/ci/ci-trace.py`, never raw `gh`. Watch
   `bcywk2wkn` is tracing `da2ecc5b5` to a final verdict. The previous red was
   PR-description staleness (329 min); the body has since been synced from the
   republished snapshot, so that edit is now newer than the head commit.
4. When green: `gh pr ready` on #579, request review, resolve threads.
   **Never merge, never push `main`.**

## Live hazards

- Shared worktree. A peer session (`e580532b`) runs a GPU/TTS pipeline in
  `private/growth`. Do NOT build `packages/www` here — that is why the two www
  gates are deferred rather than satisfied.
- `agent/e580532b/STATE.md` is dirty and is THEIRS. Never stage it.
- `npm run ci` writes NO receipt; only `ci:quick` does (`run.ts:786`).
- `gh api .../logs` needs `--allow-escape-sequences` or it exits 1 with an
  EMPTY body and the reason on stderr alone — piped to grep that reads as
  "no findings".
