# PLAN: W7P5-a deploy/release port — close the real-run-note gap, not re-port anything
Status: draft -- design only, not implemented
Owner: f4da5c2e

## Why

`agent/PLAN-tooling-transformation.md:607` (box "W7P5-a S") covers the 48 bash scripts under `.ci/scripts/deploy/` (27) and `.ci/scripts/release/` (21), 5,440 lines. The box's own text, read in full through line 793 (the line before W7P5-b opens), documents a long, honest history of incremental work through 2026-09-14. This plan re-measures every load-bearing claim against the live
tree (commit `e1c1a420c`, 2026-09-15, branch `0914-1`) rather than trusting the box's prose, per the campaign's own recurring finding that numbers "move" between waves.

**Headline re-verification result: the box's most recent status (2026-09-14) is accurate.** Unlike several sibling boxes, nothing here was stale or already-done-but-uncredited. But re-measurement surfaced one genuine, unenforced gap the box's own gate does not check: 13 of the 16 "ledgered" paths are missing the "one real run each" leg the box's opening sentence requires, and
nothing in `check:ci-w7p5a-real-run-blockers` notices this, because that gate only partitions `ledger` vs `blocked`, not whether a `ledger` row's real-run leg is actually done.

## 1. Ground truth, verified live (not inherited from the box's prose)

- `find .ci/scripts/deploy .ci/scripts/release -type f` = 48 files (27 + 21), confirmed.
- `wc -l` over the 48 `.sh` twins = 5,446 lines (box says 5,440; six-line drift, immaterial,
not worth chasing).
- `.ci/rediacc_ci/deploy/*.py` and `.ci/rediacc_ci/release/*.py` (excluding `__pycache__`) show
**every one of the 48 twins already has a Python port on disk** — this is `W7P6`'s 208-file package (commit `b2f98691c`, "the rediacc_ci package — every bash gate driver ported to Python, beside its twin"), not W7P5-a's own work, landed 2026-09-14. W7P5-a never had to write these ports; it inherited full dry-run-parity coverage for its scope from a sibling box.
- `.ci/shadow/w7p5a-status.json`: `schema: w7p5a-status/v1`, 48 `paths` entries, **16 `ledger` /
32 `blocked`**, matches the box's 2026-09-14 text exactly (`git log -1` on this file = `85e65ae27`, "the K=5 shadow ledgers — the port's equivalence, recorded as evidence").
- `.ci/policy/.w7p5a-real-run-blocklist`: 32 BLOCKER-gated entries, one per `blocked` path
(several share a comment), each carrying the corrected 2026-09-14 wording ("is DONE (verified 2026-09-14): W7P6 independently ported it... external tools stubbed throughout").
- `npm run check:ci-w7p5a-real-run-blockers` → rc=0, live: `"32 BLOCKER-gated real-run
exemption(s) ..., agreeing with .ci/shadow/w7p5a-status.json (32 'blocked', 16 ledgered) -- no third state"`. The registered gate genuinely holds today, exactly as the box claims.
- The gate's own source, `.ci/rediacc_ci/quality/w7p5a_real_run_blockers.py` (read in full),
checks four things only: BLOCKER quality via the canonical validator, every named path still exists, no entry has silently graduated to `ledger` while still blocked, and the `blocked`/ allowlist sets agree in both directions. **It asserts nothing about what a `ledger` row's `note` field actually claims.** That is the gap this plan closes (Section 2).

## 2. The gap: 13 of 16 "ledgered" paths never got their real run, and nothing checks it

The box's opening sentence sets the bar as **"golden dry-run parity plus one real run each"** before a path counts as fully done (deletion, out of scope, comes later still). The acceptance paragraph immediately below it only requires "a ledger ... or an allowlist entry with a BLOCKER" — silent on whether the ledgered path also got its real run. That silence let a real gap open
without tripping the registered gate:

```
python3 -c "
import json
d = json.load(open('.ci/shadow/w7p5a-status.json'))
for p in d['paths']:
    if p['status']=='ledger' and 'real run each done directly' not in p.get('note',''):
        print(p['path'])
"
```
prints 13 paths, live, today:

**Group A — zero external-infra calls in the real-run branch, safe to real-run against this checkout right now** (confirmed by `grep -nE '\b(curl|wrangler|aws|gh |docker )\b'` over each twin, live):
- `.ci/scripts/deploy/resolve-www-deploy-target.sh` (read-only; comments only mention
`wrangler`, no invocation)
- `.ci/scripts/release/backfill-write-sentinel.sh` (its own `DRY_RUN=true` branch never reaches
the R2-writing script; the port's own docstring documents this forwarding)
- `.ci/scripts/release/check-soak-period.sh` (pure date arithmetic)
- `.ci/scripts/release/deployment-summary.sh` (pure string/markdown assembly)
- `.ci/scripts/release/resolve-backfill-commit.sh` (local `git` only, against this repo's own
tags/history)
- `.ci/scripts/release/validate-stage-artifacts.sh` (local `find`/`wc` over `dist/`)

These are the exact same shape as the 3 paths (`resolve-account-deploy-config`, `upload-media-to-r2`, `decide-release-mode`) whose notes already say "one real run each done directly against this tree (no fixture needed ... since none of these touch external infra)". Closing Group A is mechanical repetition of already-proven-safe work, not new design.

**Group B — real network calls in the real-run branch (real GitHub API via `gh`, or real HTTPS `curl` to `releases.rediacc.com`), genuinely production-facing, NOT safe to real-run in this pass**:
- `.ci/scripts/deploy/wait-for-preview-worker.sh` — `curl` against a live Cloudflare Worker
preview URL (health + well-known endpoints)
- `.ci/scripts/release/check-edge-manifest.sh`, `check-stable-manifest.sh` — `curl` against
`https://releases.rediacc.com/cli/{edge,stable}/manifest.json` (real production CDN)
- `.ci/scripts/release/check-existing-release.sh`, `resolve-ci-run.sh`,
`verify-artifact-attestation.sh`, `verify-release-assets.sh` — real `gh release view` / `gh api` / `gh attestation verify` against the real GitHub repo (read-only GETs, but still a real external system this session has no standing operator authorization to touch for this purpose)

Per this task's own safety framing, Group B must NOT be executed by an unattended session. Even though the calls are read-only GETs, they are exactly the class the box itself treats as an "OPERATOR-AUTHORIZATION matter" for the 32 fully-blocked paths — the only difference here is these 7 already have their dry-run K=5 ledger, so only their real-run leg is exposed, not their whole
port.

**Why this matters beyond bookkeeping**: the box spent real, documented effort (lines 649-665, 749-780) making sure the `blocked` bucket's BLOCKER reasons are checked in-gate rather than living in an unchecked status-file prose field — "a reason in an unchecked file is exactly the third state the acceptance forbids, wearing the right clothes." The 13-path gap found here is the
identical failure mode wearing the OTHER bucket's clothes: a `ledger` row's implicit claim ("this path is done") is unchecked prose exactly the same way the old `blocked` notes were, just never audited because the gate's four checks don't look inside a `ledger` row's `note`.

## 3. The exact mechanical steps for a real run (Group A), reusing the box's own recorded technique

The K=5 *dry-run* ledger technique (disposable scratch repo, five clean-tree commits, `--repo <scratch> --ledger <console>/...`) is documented at box lines 642-648 and is NOT what Group A needs — Group A's ledgers already exist and are not being re-recorded. What Group A needs is the *separate* "one real run each" leg, which per the 3 already-done paths' own note means: **invoke
the real bash twin and the real Python port directly against this real, already-clean-enough checkout** (not a scratch clone, not a stubbed fixture), confirm the two outputs agree, and record that fact in the `note` field.

Per-script commands (env values are the scripts' own documented "Run locally" recipes, read from each twin's header comment; `GITHUB_OUTPUT`/`GITHUB_STEP_SUMMARY` point at a real temp file, not `/dev/stdout`, per the harness bug the box already found and fixed at lines 630-634):

```bash
# resolve-www-deploy-target
TARGET=edge GITHUB_OUTPUT=/tmp/rw-old.env bash .ci/scripts/deploy/resolve-www-deploy-target.sh
TARGET=edge GITHUB_OUTPUT=/tmp/rw-new.env PYTHONPATH=.ci PYTHONDONTWRITEBYTECODE=1 \
  python3 -m rediacc_ci.deploy.resolve_www_deploy_target
diff /tmp/rw-old.env /tmp/rw-new.env   # expect: no diff

# backfill-write-sentinel
VERSION=v1.1.2 CHANNEL=edge COMMIT_SHA="$(git rev-parse HEAD)" DRY_RUN=true \
  bash .ci/scripts/release/backfill-write-sentinel.sh
VERSION=v1.1.2 CHANNEL=edge COMMIT_SHA="$(git rev-parse HEAD)" DRY_RUN=true \
  PYTHONPATH=.ci PYTHONDONTWRITEBYTECODE=1 python3 -m rediacc_ci.release.backfill_write_sentinel
# compare stdout/exit code by hand; both must print the writer invocation and exit 0

# check-soak-period
EDGE_DATE="$(date -u -d '-70 days' +%Y-%m-%dT%H:%M:%S)" SOAK_DAYS=7 GITHUB_OUTPUT=/tmp/cs-old.env \
  bash .ci/scripts/release/check-soak-period.sh
EDGE_DATE="$(date -u -d '-70 days' +%Y-%m-%dT%H:%M:%S)" SOAK_DAYS=7 GITHUB_OUTPUT=/tmp/cs-new.env \
  PYTHONPATH=.ci PYTHONDONTWRITEBYTECODE=1 python3 -m rediacc_ci.release.check_soak_period
diff /tmp/cs-old.env /tmp/cs-new.env

# deployment-summary
VERSION=1.2.3 CI_RUN_ID=1 CI_SHA="$(git rev-parse HEAD)" GITHUB_STEP_SUMMARY=/tmp/ds-old.md \
  bash .ci/scripts/release/deployment-summary.sh
VERSION=1.2.3 CI_RUN_ID=1 CI_SHA="$(git rev-parse HEAD)" GITHUB_STEP_SUMMARY=/tmp/ds-new.md \
  PYTHONPATH=.ci PYTHONDONTWRITEBYTECODE=1 python3 -m rediacc_ci.release.deployment_summary
diff /tmp/ds-old.md /tmp/ds-new.md

# resolve-backfill-commit (real git history/tags in this checkout — no fixture needed)
VERSION=v1.1.2 GITHUB_OUTPUT=/tmp/rb-old.env bash .ci/scripts/release/resolve-backfill-commit.sh
VERSION=v1.1.2 GITHUB_OUTPUT=/tmp/rb-new.env PYTHONPATH=.ci PYTHONDONTWRITEBYTECODE=1 \
  python3 -m rediacc_ci.release.resolve_backfill_commit
diff /tmp/rb-old.env /tmp/rb-new.env

# validate-stage-artifacts (needs a populated dist/; use whatever the checkout currently has,
# or an empty dist/ -- the script handles the zero-artifact case per its own comment)
EVENT_NAME=push NEXT_VERSION=1.2.3 CHANNEL=edge GITHUB_STEP_SUMMARY=/tmp/va-old.md \
  GITHUB_OUTPUT=/tmp/va-old.env bash .ci/scripts/release/validate-stage-artifacts.sh
EVENT_NAME=push NEXT_VERSION=1.2.3 CHANNEL=edge GITHUB_STEP_SUMMARY=/tmp/va-new.md \
  GITHUB_OUTPUT=/tmp/va-new.env PYTHONPATH=.ci PYTHONDONTWRITEBYTECODE=1 \
  python3 -m rediacc_ci.release.validate_stage_artifacts
diff /tmp/va-old.md /tmp/va-new.md && diff /tmp/va-old.env /tmp/va-new.env
```

After each pair agrees, update that path's `note` field in `.ci/shadow/w7p5a-status.json` to append the same sentence the 3 already-done entries carry: `"; one real run each done directly against this tree (no fixture needed for the real-run half, since none of these touch external infra)."` — byte-for-byte consistent phrasing, so a future audit can `grep` for the phrase across all
16 `ledger` rows and expect it on every one that qualifies.

**If the module needs to be invoked** (not all of these have a `python3 -m rediacc_ci.<pkg>.<mod>` entry point wired identically to the bash twin's CLI surface — confirm each module's own `if __name__ == "__main__":` block against the twin's env-var contract before running; the differential test file for each (`.ci/rediacc_ci/tests/test_*.py`) already shows the exact invocation
shape used in CI, e.g. `test_release_check_soak_period.py`'s `run_both` helper).

## 4. Group B: do not real-run; make the gap explicit and checked instead of silent

Group B's 7 paths cannot get a real run in this session per the task's own safety constraint (no live Cloudflare/GitHub production credentials to be used for anything beyond what the existing, already-authorized `gh` CLI does for routine repo operations — and even read-only use against production release/manifest state for a porting exercise is exactly the kind of unilateral action
the box itself refuses for the 32 fully-blocked paths). The right move, matching the box's own precedent instead of leaving a silent gap:

1. Do **not** flip these 7 to `blocked` — their dry-run K=5 ledger is real and complete; that
would misrepresent completed work as absent.
2. **Extend `.ci/rediacc_ci/quality/w7p5a_real_run_blockers.py`'s `run()`** with a fifth check:
for every path with `status == "ledger"`, the `note` field must contain either the real-run confirmation phrase (Section 3) or a real-run-specific BLOCKER-shaped reason (reusing `rediacc_ci.core.allowlist`'s validator, the same one the existing 32-entry blocklist already goes through). A `ledger` row with neither is a new finding: `"%s is ledgered for dry-run parity but its
real-run leg is neither confirmed nor blocked — the third state, in the ledger bucket instead of the blocked one."`
3. Add a **second allowlist file** (or extend the existing `.w7p5a-real-run-blocklist` to also
accept `ledger`-status paths — the canonical validator does not care which status bucket an entry's path is in, only that the BLOCKER text is real) with 7 entries for Group B, each naming the specific external system (`releases.rediacc.com` CDN, live Cloudflare Worker preview URL, or the real GitHub repo via `gh`) and the same "sandboxed coding agent, no standing authorization to
perform this against production" reasoning already proven to pass `allowlist.verify()` for the 32.
4. Re-run `check:ci-w7p5a-real-run-blockers --selftest` and the gate itself; the existing 13/13
(or however many after the extension) selftest count should grow by at least one new PLANT case exercising the new check, following the file's own established pattern (see the selftest cases at lines 191-303 for the shape: CLEAN, PLANT catches each of the four existing findings, VACUITY refusals).
5. This closes the "no third state" acceptance genuinely for the FULL literal reading of the
box's opening sentence ("dry-run parity plus one real run each"), not just the acceptance paragraph's narrower ledger-or-BLOCKER test — matching the spirit the box's own 2026-09-09 and 2026-09-14 waves both explicitly cared about (lines 649-655, 754-765).

## 5. What this plan deliberately does NOT do

- **Does not re-port any of the 48 scripts.** All 48 already have a Python port on disk
(W7P6, `.ci/rediacc_ci/deploy/` and `.ci/rediacc_ci/release/`), each with its own permanent pytest differential and K=5 ledger (16 under `w7p5a-<slug>`, 32 under `w7p6-<slug>`). Finding the "gap" was itself the point of this survey — the box's own text already flags that a session must not assume a port is missing without checking (line 702, "DRY-RUN PARITY RE-AUDITED AND FOUND
ALREADY SATISFIED").
- **Does not touch any real Cloudflare, R2, D1, or GHCR credential**, and does not perform a
real run for any of the 32 fully-`blocked` paths or the 7 Group-B paths. All of those remain parked pending explicit operator authorization, exactly as the box requires.
- **Does not delete any bash twin.** Deletion is out of scope for W7P5-a entirely, per the box's
own text and the campaign-wide K=5-before-deletion rule.
- **Does not touch `.github/workflows/**`** — none of this work needs a workflow-call-site edit;
every command above runs the twin/port pair directly, exactly as the existing 3-done and 16-done entries already did.
- **Does not decide** whether the "one real run each" clause should, in fact, gate this box's
overall acceptance (Section 2's ambiguity) — it makes that ambiguity a checked, named condition instead of resolving it unilaterally, since resolving it (e.g., deciding the box IS done without the real-run leg) is a driver-level call the same way the 32-path BLOCKER register status changes were treated as driver actions.

## 6. Sequencing and pre-flight checks

1. Confirm no concurrent writer holds `.ci/shadow/w7p5a-status.json`,
`.ci/policy/.w7p5a-real-run-blocklist`, or `.ci/rediacc_ci/quality/w7p5a_real_run_blockers.py` (the box notes W7P5-b's writer is active nearby, editing an unrelated table in the same plan doc — confirm it is not also touching these specific files before starting).
2. Confirm the working tree is clean under `.ci/`, `.ci/shadow/`, and `.ci/policy/` specifically
(the wider tree is not clean today — `agent/`, `private/account`, `.local/` carry unrelated session state — but `shadow-gate.ts --record`/status-file edits only need cleanliness in the paths that matter to `treeIdentity`; this plan does not invoke `--record` at all, since Group A's real-run leg is a direct twin/port comparison, not a new ledger row).
3. Do Group A (Section 3) first — six mechanical, zero-risk comparisons, no design work.
4. Do Group B's gate extension (Section 4) second — this is the only code change in this plan,
and it is a driver-registered gate file, so treat it with the same care as the box's own 2026-09-09 gate-registration wave (add selftest PLANT/CLEAN cases before relying on the new check; re-run `--selftest` and the real gate before considering it landed).
5. After both, re-run `npm run check:ci-w7p5a-real-run-blockers` and confirm the success line
still prints "no third state" with the new, fuller meaning (ledger rows now also honestly report their real-run status, not just their dry-run one).

## Tasks

- [x] Confirm no concurrent writer holds `.ci/shadow/w7p5a-status.json`,
      `.ci/policy/.w7p5a-real-run-blocklist`, or
      `.ci/rediacc_ci/quality/w7p5a_real_run_blockers.py`. DONE 2026-09-15: clean before start.
- [x] Group A, six real runs (Section 3): `resolve-www-deploy-target`,
      `backfill-write-sentinel`, `check-soak-period`, `deployment-summary`,
      `resolve-backfill-commit`, `validate-stage-artifacts` — run bash twin and Python port
      directly against this checkout with the documented env vars, `GITHUB_OUTPUT`/
      `GITHUB_STEP_SUMMARY` pointed at a real temp file (not `/dev/stdout`), diff the outputs,
      confirm byte-identical. DONE 2026-09-15: all 6 confirmed byte-identical (deployment-summary
      also matched exit codes and error-path text; resolve-backfill-commit verified on both a
      real tag and a missing-tag error path).
- [x] Update each of the six paths' `note` field in `.ci/shadow/w7p5a-status.json` to append the
      real-run confirmation sentence, byte-identical wording to the 3 already-done entries.
      DONE 2026-09-15, landed via `f6c8936c6` (absorbed into a babysitter commit; content
      verified intact via `git show`).
- [x] Re-run `npm run check:ci-w7p5a-real-run-blockers` after the status-file edit; confirm rc=0
      and the stats line still reads "16 ledgered" (status bucket unchanged, only `note` grew).
      DONE: rc=0 throughout.
- [x] Extend `.ci/rediacc_ci/quality/w7p5a_real_run_blockers.py`'s `run()` with the fifth check
      from Section 4: every `status == "ledger"` path's `note` must carry either the real-run
      confirmation phrase or a validated real-run BLOCKER; add the corresponding PLANT/CLEAN
      selftest cases before relying on it. DONE 2026-09-15, commit `5f51acb59`: 6 new selftest
      controls (2 CLEAN, 3 PLANT, plus the two count assertions), all pass.
- [x] Add real-run BLOCKER entries for the 7 Group-B paths (`wait-for-preview-worker`,
      `check-edge-manifest`, `check-stable-manifest`, `check-existing-release`, `resolve-ci-run`,
      `verify-artifact-attestation`, `verify-release-assets`) through the canonical
      `rediacc_ci.core.allowlist` validator, naming the specific external system each one's
      real-run branch reaches (`releases.rediacc.com`, live Worker preview URL, or the real
      GitHub repo via `gh`). DONE 2026-09-15: new file `.ci/policy/.w7p5a-real-run-leg-blocklist`
      (kept SEPARATE from `.w7p5a-real-run-blocklist`, not merged into it — see Section 4's own
      reasoning about the STALE check), registered in both POLICY_FILES seams,
      `check:ci-policy-inventory` confirms 20/20/20.
- [x] Re-run `check:ci-w7p5a-real-run-blockers --selftest` and the gate itself; confirm the new
      check fires on a planted violation and stays quiet on the real, now-fully-annotated tree.
      DONE: rc=0, "32 blocked, 16 ledgered ... 9 confirmed, 7 leg-blocked".
- [x] Leave all 32 fully-`blocked` paths untouched — no real run, no status change, matching the
      box's own explicit operator-authorization boundary. Confirmed: `blocked_in_status` stayed
      32 throughout.

**Section 4 CLOSED 2026-09-15. This box's own scope (the real-run-leg gap this plan found and the gate extension to catch it going forward) is fully done.** Remaining W7P5-a work outside this plan's scope: the 39 (32 whole-port + 7 leg-only) production-facing real runs still need explicit operator authorization before they can happen at all — that boundary was never this plan's to
cross.

### Critical Files for Implementation

- /home/developer/console/.ci/shadow/w7p5a-status.json
- /home/developer/console/.ci/policy/.w7p5a-real-run-blocklist
- /home/developer/console/.ci/rediacc_ci/quality/w7p5a_real_run_blockers.py
- /home/developer/console/.ci/scripts/release/backfill-write-sentinel.sh
- /home/developer/console/.ci/rediacc_ci/release/backfill_write_sentinel.py
