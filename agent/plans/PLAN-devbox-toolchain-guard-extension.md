# PLAN: extend block_host_toolchain_run.py to cover aws/bw/bws, with an exception list

Status: executing (implementation in progress, uncommitted: block_host_toolchain_run.py modified, test-block_host_toolchain_run.py modified, .ci/policy/.host-toolchain-exceptions created)
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

- [ ] `NEEDS` (line ~57-61): add `("check:ci-release-state", "aws")`.
- [ ] New table `NEEDS_SCRIPT`, placed after `NEEDS`, before `NEEDS_ENV`: `(script-basename, tool)` pairs for the 14 direct-invocation scripts above, matched via `_is_invoked()` (never a plain substring test -- `NEEDS`'s own older substring approach is exactly the "reading a script is mistaken for running it" bug `_is_invoked` was built to fix for `NEEDS_ENV`).
- [ ] New loop for `NEEDS_SCRIPT`, inserted after the existing `BARE_TOOLS` loop, setting `bare = True` so the refusal message says "this command needs 'aws'" rather than suggesting a nonsensical `npm run <script>.sh`.
- [ ] `BARE_TOOLS`: add `"aws"`, `"bw"`, `"bws"`.
- [ ] `NPX_TOOLS`: leave untouched -- no measured incident of `npx aws`/`npx bw` misuse; this file's own discipline is measured incidents, not hypotheticals.
- [ ] `.ci/rediacc_ci/quality/toolchain_pins.py`'s `GATED_TOOLS`: leave untouched -- governs a different convention (unpinned `@latest` downloads via `toolchain_acquire`), and `aws`/`bw`/`bws` are baked into the Dockerfile directly, not pulled per-CI-run.

## Exception-list mechanism

- [ ] New file `.ci/policy/.host-toolchain-exceptions`, following the repo's existing BLOCKER-comment allowlist format (`# BLOCKER: <reason, >=30 chars, no banned vague phrases>` grouping the entries beneath it). Route it through `scripts/lib/policy-paths.ts`'s `POLICY_FILES`/`policyPath()` seam even though only a Python hook reads it.
- [ ] Parse/validate via a scoped import of `.ci`'s `rediacc_ci.core.allowlist` (same pattern as `block_prose_style_edit.py:230-244`: push `.ci` onto `sys.path`, import, pop it), reusing `parse_file`/`verify` rather than a second implementation.
- [ ] Consult the parsed entries right after `hit`/`need`/`bare` are computed, before the hostbound walk; a present, valid entry emits a NOTE naming the exception and its BLOCKER text, then allows.
- [ ] Add a companion gate test (e.g. `.ci/scripts/test/gates/test-host-toolchain-exceptions.sh`) that greps every parsed reason for the banned phrase family ("doesn't exist on devbox", "absent from the devbox image", "devbox lacks it", "not installed in devbox") and fails loudly if found -- the generic `allowlist.py` banned-phrase list does not know this domain-specific phrase.
- [ ] Ship the file empty at first, with a header comment documenting the one legitimate category (a host-only interactive auth ceremony a headless container cannot complete) versus the one illegitimate category (a devbox gap, which gets fixed in `.devcontainer/Dockerfile` instead).
      No current `aws`/`bw`/`bws` consumer needs an exception -- all resolve credentials from plain env vars.

## Test coverage (mirroring test-block_host_toolchain_run.py's existing pattern)

- [ ] Gate-key case: `check:ci-release-state` with `aws` stripped from PATH, `have_box` true -> exit 2; host-has-it control -> exit 0.
- [ ] `NEEDS_SCRIPT` case, the incident itself: `assert-edge-tag-exists.sh --version 1.3.0` with `aws` missing on host, present in devbox -> exit 2, message says "this command needs 'aws'", never "npm run ...".
- [ ] Reader/mention regression: `grep -n TODO assert-edge-tag-exists.sh` and `sed -n 1,5p <same path>` stay exit 0 even with `aws` stripped -- the exact bug class `_is_invoked` exists to prevent.
- [ ] A second, smaller loop (not folded into the existing `ALL_TOOLS` loop, which asserts npx-misuse for every member) covering `aws`/`bw`/`bws` bare-tool routing: absent-from-host + devbox-has-it -> 2; shimmed-onto-host -> 0.
- [ ] Two-stage case: `NEEDS_ENV`'s credential check satisfied (`private/account/.env` sourced) but `aws` still missing on host -> `NEEDS_SCRIPT` still catches it, proving the two tables compose in the right order.
- [ ] Exception-file case: a present, valid exception for `("check:ci-release-state", "aws")` -> exit 0, silent/NOTE only.

## Verification

- [ ] `python3 .claude/rediacc_hooks/guards/test-block_host_toolchain_run.py` green, new cases included, both directions.
- [ ] `check:ci-hook-integrity` green (TWIN/differential requirements unaffected).
- [ ] Live: `.ci/scripts/release/assert-edge-tag-exists.sh` run on the host now refuses/routes rather than reporting a bare "command not found".

## Critical files

- `.claude/rediacc_hooks/guards/block_host_toolchain_run.py`
- `.claude/rediacc_hooks/guards/test-block_host_toolchain_run.py`
- `.ci/rediacc_ci/core/allowlist.py`
- `.ci/policy/.host-toolchain-exceptions` (new)
- `.ci/policy/README.md`, `scripts/lib/policy-paths.ts`, `docs/agent-reference/suppressions.md`

Design produced by a dispatched Plan agent (2026-09-23), citing exact file:line locations in the existing guard and a live-verified devbox tool survey; this session verified the trigger incident and the aws-in-devbox claim directly before writing this file.
