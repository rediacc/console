# STATE — branch 0807-2 (session d136ac61) — 2026-08-07 09:35Z

**BOTH WRITERS ARE DONE AND REAPED. Nothing is in flight on this branch.** The
wave is committed and every gate is green. What remains is pushing, one
operator decision, and a submodule fix.

## v1.2.17 SHIPPED — and the guard worked for the first time ever

Release 31164075754: success, 17 success / 2 skipped. The Initialize log now
says:

    ##[notice]Artifact version v1.2.17 matches promotion target v1.2.17.

That line has never existed before today. Every previous release printed
"cli-manifest artifact not found; skipping artifact-version assertion" instead,
because nothing produced that artifact. `main` is at fb53d0480 plus CD's own
two commits.

## Committed here, 4 commits, UNPUSHED, no PR yet

  e3407af36  verify_version could not fail (base, also on local main)
  f380dff61  install-method tests that verified nothing now verify
  0af285dab  the six remaining release-path guards
  dac02d3fc  register all 11 gate tests + delete a comment that now lies

Verified by me, not accepted on report: `check-ci-parity` green in BOTH
directions, 192 gates / 81 battery tests. The writers' claim of 81 passed /
0 failed / 889 assertions is corroborated by parity independently counting 81
battery tests. Shell lint/format/commands green.

The 11 manifest registrations were mine — the writers correctly stopped at the
boundary rather than editing a file they did not own. One of those 11,
test-verify-version.sh, was ALREADY unregistered before this wave.

A writer overrode one of my instructions and was RIGHT. I asked for a host-side
version comparison; that would have rebuilt a check that cannot fail, because
apt, npm and brew each PRINT the expected version while installing, so
"Setting up rediacc-cli (1.2.17) ..." satisfies a transcript grep while the
binary reports 1.2.16. It fences the container's own output and compares only
what is inside, asserting both directions.

## THE ONE THING THAT MUST NOT BE FORGOTTEN

This wave introduces a REGRESSION, which I verified myself in both halves:
`compareVersions` now THROWS on a malformed version, and
`private/account/src/app.ts:548` awaits `checkCliVersionPolicy` with NO
try/catch, feeding it the client-controlled `x-cli-version` header (read at
:546, used at :90). So a malformed header goes from SILENTLY BYPASSING the
minimum-version gate to a 500 on attacker-controlled input. Both behaviours are
wrong.

Proposed two-line fix: re-export `isValidVersion` from
`packages/shared/src/utils/index.ts` (it exports only `compareVersions` today),
then guard at `app.ts:87` — reject rather than return null, preferably.
`private/account` is a SEPARATE SUBMODULE, so this is its own PR. Awaiting an
operator decision; do NOT ship 0807-2 to production without settling it.

## Operator decisions already given (do not re-ask)

Push 0807-1 as a BRANCH + PR (not straight to main). Push e3407af36 to main
only after the release settled — it has now, so this is unblocked. Leave the
orphaned 1.2.17 R2 objects alone. Keep assert-artifact-version.sh's hard fail.
This wave: all 10 findings, new branch + PR, harden both fail-open guards —
all done.

## Next action
Ask the operator about the x-cli-version regression. Then push `e3407af36` to
main; push branch 0807-1 and open its PR; push 0807-2 and open its PR. Watch
whatever release the main push dispatches.
