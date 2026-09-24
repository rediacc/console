# PLAN: extend block_host_toolchain_run.py to cover aws/bw/bws, with an exception list

Status: done
First-Seen: 2026-09-23
Owner: d778be9d
Updated: 2026-09-23

## Finding

`.claude/rediacc_hooks/guards/block_host_toolchain_run.py` already routes a gate or a bare tool invocation into the devbox when the host lacks the toolchain but the container has it (NEEDS, BARE_TOOLS, NEEDS_ENV tables). It does not cover `aws`, `bw`, `bws`.
Trigger: this session ran `.ci/scripts/release/assert-edge-tag-exists.sh` on the HOST, hit `Required command 'aws' is not available`, and nearly evaluated installing `awscli` on the host before the operator corrected course -- the devbox already carries aws-cli 2.36.40 (confirmed via `docker exec rediacc-devbox-94-console`).
Operator's standing rule: "doesn't exist on devbox" is never an acceptable reason to fall back to the host; the fix for a genuinely missing devbox tool is `.devcontainer/Dockerfile`, not an exception.

## Survey (Plan agent a7839b9d9e833367f, verified against the tree)

`.devcontainer/Dockerfile` bakes in all three, pinned: `aws` (lines 467-490, unpinned version -- flagged separately, out of scope here), `bw` (509-553, `BW_VERSION=2026.9.0`), `bws` (555-587, `BWS_VERSION=2.1.0`).

`aws` is genuinely `require_cmd`'d (fails without it) in 12 scripts: `assert-edge-tag-exists.sh`, `write-release-sentinel.sh`, `delete-r2-channel.sh`, `promote-r2-to-stable.sh`, `promote-r2-to-stable-hotfix.sh`, `simulate-promotion.sh`, `upload-repos-to-r2.sh`, `cleanup-versions.sh` (housekeeping), `upload-r2.sh` (media), `scrub-sentinel.sh`, `sync-media-to-r2.sh`, `sync-media-from-r2.sh` -- plus 2 that call it directly under `set -euo pipefail` with no guard (`upload-to-r2.sh`, `r2-oneshot-scrub.sh`), and the npm gate `check:ci-release-state` (`.ci/rediacc_ci/quality/release_state.py:446`).

Excluded deliberately, same precedent as `check:ci-actionlint`: `.ci/breakpoint/scripts/publish-endpoints.sh:96` degrades gracefully (skips a notification) rather than failing, so adding it would route a working path into the fix-the-image branch for free.

`bws`: no script shells out to it directly; registered in `.ci/rediacc_ci/setup/tools.py:566-584` as operator-only-in-practice (needs a machine token). `bw`: nothing in the tree invokes it; purely interactive/operator tool. Both still belong in `BARE_TOOLS` so a human typing them directly on a bare host gets routed.

## Table/code additions

- [x] `NEEDS` (line ~57-61): add `("check:ci-release-state", "aws")`.
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] New table `NEEDS_SCRIPT`, placed after `NEEDS`, before `NEEDS_ENV`: `(script-basename, tool)` pairs for the 14 direct-invocation scripts above, matched via `_is_invoked()` (never a plain substring test -- `NEEDS`'s own older substring approach is exactly the "reading a script is mistaken for running it" bug `_is_invoked` was built to fix for `NEEDS_ENV`).
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] New loop for `NEEDS_SCRIPT`, inserted after the existing `BARE_TOOLS` loop, setting `bare = True` so the refusal message says "this command needs 'aws'" rather than suggesting a nonsensical `npm run <script>.sh`.
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] `BARE_TOOLS`: add `"aws"`, `"bw"`, `"bws"`.
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] `NPX_TOOLS`: leave untouched -- no measured incident of `npx aws`/`npx bw` misuse; this file's own discipline is measured incidents, not hypotheticals.
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] `.ci/rediacc_ci/quality/toolchain_pins.py`'s `GATED_TOOLS`: leave untouched -- governs a different convention (unpinned `@latest` downloads via `toolchain_acquire`), and `aws`/`bw`/`bws` are baked into the Dockerfile directly, not pulled per-CI-run.
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites

## Exception-list mechanism

- [x] New file `.ci/policy/.host-toolchain-exceptions`, following the repo's existing BLOCKER-comment allowlist format (`# BLOCKER: <reason, >=30 chars, no banned vague phrases>` grouping the entries beneath it). Route it through `scripts/lib/policy-paths.ts`'s `POLICY_FILES`/`policyPath()` seam even though only a Python hook reads it.
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Parse/validate via a scoped import of `.ci`'s `rediacc_ci.core.allowlist` (same pattern as `.claude/rediacc_hooks/guards/block_prose_style_edit.py:230-244`: push `.ci` onto `sys.path`, import, pop it), reusing `parse_file`/`verify` rather than a second implementation.
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Consult the parsed entries right after `hit`/`need`/`bare` are computed, before the hostbound walk; a present, valid entry emits a NOTE naming the exception and its BLOCKER text, then allows.
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Add a companion gate test (e.g. `.ci/scripts/test/gates/test-host-toolchain-exceptions.sh`) that greps every parsed reason for the banned phrase family ("doesn't exist on devbox", "absent from the devbox image", "devbox lacks it", "not installed in devbox") and fails loudly if found -- the generic `allowlist.py` banned-phrase list does not know this domain-specific phrase.
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Ship the file empty at first, with a header comment documenting the one legitimate category (a host-only interactive auth ceremony a headless container cannot complete) versus the one illegitimate category (a devbox gap, which gets fixed in `.devcontainer/Dockerfile` instead).
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
      No current `aws`/`bw`/`bws` consumer needs an exception -- all resolve credentials from plain env vars.

## Test coverage (mirroring test-block_host_toolchain_run.py's existing pattern)

- [x] Gate-key case: `check:ci-release-state` with `aws` stripped from PATH, `have_box` true -> exit 2; host-has-it control -> exit 0.
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] `NEEDS_SCRIPT` case, the incident itself: `assert-edge-tag-exists.sh --version 1.3.0` with `aws` missing on host, present in devbox -> exit 2, message says "this command needs 'aws'", never "npm run ...".
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Reader/mention regression: `grep -n TODO assert-edge-tag-exists.sh` and `sed -n 1,5p <same path>` stay exit 0 even with `aws` stripped -- the exact bug class `_is_invoked` exists to prevent.
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] A second, smaller loop (not folded into the existing `ALL_TOOLS` loop, which asserts npx-misuse for every member) covering `aws`/`bw`/`bws` bare-tool routing: absent-from-host + devbox-has-it -> 2; shimmed-onto-host -> 0.
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Two-stage case: `NEEDS_ENV`'s credential check satisfied (`private/account/.env` sourced) but `aws` still missing on host -> `NEEDS_SCRIPT` still catches it, proving the two tables compose in the right order.
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Exception-file case: a present, valid exception for `("check:ci-release-state", "aws")` -> exit 0, silent/NOTE only.
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites

## Verification

- [x] `python3 .claude/rediacc_hooks/guards/test-block_host_toolchain_run.py` green, new cases included, both directions.
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] `check:ci-hook-integrity` green (TWIN/differential requirements unaffected).
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Live: `.ci/scripts/release/assert-edge-tag-exists.sh` run on the host now refuses/routes rather than reporting a bare "command not found".
    (ticked) 2026-09-23T12:19:36Z by d778be9d: retroactive record: closed by cc20cbec0 (2026-09-23) feat(hooks): route aws/bw/bws at the devbox, with a BLOCKER-gated exce -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites

## Outcome, 2026-09-23

Shipped. `python3 .claude/rediacc_hooks/guards/test-block_host_toolchain_run.py` reports `FAILURES: 0 (85 case(s), devbox_present=True)`, up from 40 cases before the change. `test_guards_differential.py -k host_toolchain` passes 255 cases against the frozen bash oracle, so none of the three new tables changes the verdict on any corpus payload.
`check:ci-hook-integrity`, `check:ci-host-toolchain-coverage`, `check:ci-policy-inventory` (22 files == 22 == 22), `check:ci-doc-region-parity` and `check:ci-shape-duplication` are all green.

Eight mutants were planted one at a time and the suite went red on every one: the NEEDS_SCRIPT loop emptied, its hit marked non-bare, its match downgraded from `_is_invoked` to a substring test, the `check:ci-release-state` row removed from NEEDS, `aws`/`bw`/`bws` removed from BARE_TOOLS, the exception consult removed, the devbox-gap refusal disabled, and an invalid BLOCKER made to grant an exception anyway.

### One deviation, and what replaced it

The companion gate test was to live at `.ci/scripts/test/gates/test-host-toolchain-exceptions.sh`.
A script placed there is not run by anything until it is registered as `gate-test:<name>` in `package.json`, `scripts/ci-runner/manifest.ts` and `scripts/ci-runner/gates.lock.json` (`.ci/rediacc_ci/quality/gate_id_convention.py:122-130` refuses an unregistered one), and a new gate moves the generated counts in CLAUDE.md and `docs/agent-reference/ci-gates.md` as well.
Three of those files are driver-owned.

The banned-phrase check landed IN THE GUARD instead, as `DEVBOX_GAP_PHRASES` plus the conjunction rule beneath it, which is strictly stronger than the planned grep: it fires at the moment an exception would be honoured rather than once per CI run, and the shipped file being clean is asserted too.
Its cases run in CI already -- `test_hooks_delegates.py` discovers `guards/test-*.py` by glob and `check:ci-pytest` collects it.

### The refusal needed two tiers, and the first one lost immediately

`DEVBOX_GAP_PHRASES` alone was the plan's design. The first reason written to test it -- "the devbox image does not have aws installed so the host is the only place this runs" -- was GRANTED: it says the banned thing in words no literal on the list carries.
So a conjunction rule sits underneath, over a devbox-ish subject, an absence verb and a tool-ish object including the binary actually being refused, and even that lost once more to "the container image ships no aws binary at all" before the `<verb> no <thing>` family was added. Nine paraphrases and two legitimate reasons are pinned as cases.

### `_is_invoked` has a false positive, found while writing this

`sh` is one of `_is_invoked`'s interpreter tokens and the alternation is not bounded on its left, so any path ending `.sh` followed by a space reads as an `sh <script>` invocation. `git ls-files | grep -F "/$f"` over a list of these script names was refused with the NEEDS_ENV credential message, because `upload-r2.sh .ci/scripts/deploy/sync-media-from-r2.sh` matched.
The fix is a left boundary on the interpreter alternation, and it is NOT in this change: `_is_invoked` is shared with NEEDS_ENV and its bash twin is frozen, so a behaviour change there is a differential question of its own rather than a line to slip into this one.

## Critical files

- `.claude/rediacc_hooks/guards/block_host_toolchain_run.py`
- `.claude/rediacc_hooks/guards/test-block_host_toolchain_run.py`
- `.ci/rediacc_ci/core/allowlist.py`
- `.ci/policy/.host-toolchain-exceptions` (new)
- `.ci/policy/README.md`, `scripts/lib/policy-paths.ts`, `docs/agent-reference/suppressions.md`

Design produced by a dispatched Plan agent (2026-09-23), citing exact file:line locations in the existing guard and a live-verified devbox tool survey; this session verified the trigger incident and the aws-in-devbox claim directly before writing this file.
