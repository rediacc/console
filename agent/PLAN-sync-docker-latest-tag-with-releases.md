# PLAN: the nightly asserts an unreleased version against the last released image
Status: compacted Owner: e6500e92 Full-Text: f01516cac agent/PLAN-sync-docker-latest-tag-with-releases.md Full-Text-Blob: 785e89eea1f5954063ba22f0fe60adc16ce7eed1 Record-Sig: 0b752061

## Why
Scheduled Console CI failed deterministically on Validate Install Methods with "expected 1.2.27, got 1.2.26". Four facts in sequence: the scope step is gated on `pull_request` so on a schedule run every scope output is empty; the job admits on `run_install_methods != 'false'` and empty is not `'false'`, so it runs; the channel assertion requires `schedule` to resolve an EMPTY
channel; and `constants.sh` then turns an empty `DOCKER_TAG` into `latest`. So the nightly pulled the last RELEASED image and asserted the NEXT version against it, and every `bump-none` merge widened the gap. A permanently red nightly trains readers to ignore the one run that watches main.

## Outcome
SHIPPED, including the gate. Header `done` is TRUE. Measured 2026-09-06.

- Option A is in `.github/workflows/ci.yml` (blob
2fb6ffdd88f57883a992fcf01a8952bdaf75f7a2): `validate-install`'s `if:` now carries `needs.initialize.outputs.channel != ''` at `:1543`, with the four-step cause traced in the comment above it, matching `validate-promote` at `:1626`.
- The dead fallback is repaired: `.ci/scripts/test/test-install-methods.sh:756` (blob
b88d85f7fe1269a7ab155a1da35f6330f6499a67) is now plainly `local tag="${DOCKER_TAG}"`, with `:749-751` recording why the `:-${VERSION}` arm could never fire.
- The gate exists and is registered in both directions:
`.ci/scripts/security/check-ci-workflow-invariants.sh` (blob d4c6aa0d56a4184704be1bd9d2b1e6b630bbdb4c) as `check:ci-workflow-invariants` (`package.json:38`, `scripts/ci-runner/gates.lock.json:4176`), and `.ci/scripts/test/gates/test-ci-workflow-invariants.sh` (blob 487369fd7fbbe067cfaebcf2be935bb9db98089a) as `gate-test:ci-workflow-invariants`
(`scripts/ci-runner/gates.lock.json:4563`).
- Landing: console commit 38989e791, "fix(ci): the nightly validated the last released
image against the next version" (2026-08-21).
- STILL UNPROVEN, exactly as the plan declared: nothing here shows the nightly GREEN. The
evidence is the gate and its planted controls.

## Lessons
- ALL FOUR COMMIT SHAS THIS PLAN CITED ARE DEAD. Every one answers "Not a valid object
name" today, because `gh pr merge --rebase` rewrote them, including the historical commit the gate's own most important control was run against. Quoted inside a fence because they are evidence of a dead pointer rather than citations to follow:

```
b0184561c   claimed as the landing, on PR #570 branch 0820-1
f1e57ee32   the unrelated promotion-timeout fix on the same PR
6584a8795   the previous main, and the gate's historical red control
ba7b175c1   the main this plan says it was verified against
```

The live landing is 38989e791 and the durable pointers are the blobs above.
- The obvious class-level invariant was FALSE, and saying so is the most useful thing in
this plan. "A job that passes the channel into a reusable workflow must gate on channel != ''" would have broken `stage-artifacts`, which passes the channel and MUST run with an empty one. The shipped invariant is scoped to `docker_tag`, because tag selection is the discriminating detail: an empty channel there resolves to a DIFFERENT IMAGE rather than to nothing.
- A fallback that cannot fire is a lie in the shape of a safety net. `${DOCKER_TAG:-${VERSION}}`
read as a guard for years and was unreachable by construction.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted Prior-Status: done Compacted-By: 8f55d4f0 Compacted-At: 2026-09-06T17:32:37Z Boxes: 0 attested, 0 open, 0 abandoned Epics: none Touched: .ci/config/constants.sh Gates: check:ci-parity, check:ci-workflow-invariants Why-Source: author Read-History: `git show 785e89eea1f5954063ba22f0fe60adc16ce7eed1` recovers the text; `git log
--find-object=785e89eea1f5954063ba22f0fe60adc16ce7eed1 --all` names the commit

## History
- 2026-09-06T17:32:37Z compacted by 8f55d4f0 from `done` (record-sig 0b752061)
