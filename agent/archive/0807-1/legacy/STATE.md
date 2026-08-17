# STATE — branch 0807-1 (session d136ac61) — 2026-08-07 07:10Z — HANDED BACK

**RELEASE PATH IS CLOSED. Nothing is in flight. No crons, no watches.**

## Shipped

Wave 0804-1 is live as **v1.2.16** (published 05:58:35Z): renet #98 ->
e8dd8318a, account #74 -> 1da0377c2, console #551 -> 9012b2251. Edge deployed
to Marketing and to Account in eu, us AND asia; smoke test green; install
validation green on all six platforms. Verified against the LIVE endpoints:
releases.rediacc.com/cli/edge/{latest,manifest}.json both read `1.2.16`.
`main` is re-synced and clean at **9290c6d45**.

## The second Release failed, and it harmed nothing

Run 31154305287 failed on `Validate Install (post-publish)` for Linux
x64/arm64 and macOS x64/ARM64: "Version mismatch: expected 1.2.17, got 1.2.16".
Edge deploys, smoke test and both Windows platforms succeeded.

My fault: I pushed the validate-promote timeout fix and its documentation as
TWO commits, so a second Console CI staged artifacts built as 1.2.16 while the
second Release computed the next version as 1.2.17 and published those
artifacts under that number.

**The pipeline behaved correctly.** `tag-and-release` needs
`validate-install-published`, so it was SKIPPED; the channel pointers were
never advanced; no v1.2.17 tag or GitHub release exists; and the failed run
pushed nothing back to main. Users see 1.2.16 consistently.

LATENT DEFECT, recorded not fixed: the release computes its version
independently of the version baked into the staged artifacts it consumes, so
any back-to-back release mismatches, and the mismatch surfaces only AFTER edge
has been deployed. A guard comparing staged-artifact version to computed
release version in `init` would fail fast. Deliberately not fixed unattended -
it is a cd-v2.yml change no PR can exercise, and re-dispatching a release is
the operator's call.

## Branch 0807-1: 11 commits, UNPUSHED, no PR — awaiting an operator decision

Post-release cleanup, all verified by running the real thing:

- **timeout-headroom gate** (`check:ci-timeout-headroom`) + a 45-minute ceiling
  for `Stage Artifacts`, which had NO ceiling anywhere. Mutation-proven.
  Vindicated twice live: validate-promote ran 31m54s and 33m04s, both past the
  old 30-minute ceiling.
- **js-yaml HIGH** GHSA-5p4m-2wfm-xmqj: 4.x fixed via override `>=4.3.1`, 3.x
  allowlisted with a verified BLOCKER. Audit -> "No production vulnerabilities".
- **missing i18n key** `pages.partners.form.fields.howHeardPlaceholder`, absent
  from ALL 13 locales, blank in production. Added everywhere.
- **key-usage gate was blind to 3 of 5 namespace names** (`NS`, `ctaNamespace`,
  `metaPath`). Now derives names from source; guarded by a control that reads
  the in-use set from the tree, so it cannot go stale.
- **block-git-amend.sh false positive** on documentation heredocs. Fixed with a
  10-case control; interpreter heredocs still blocked.

## Next action
None automated. The operator decides whether to push branch 0807-1 / open a PR.
If they want the release-version guard above, that is a fresh cd-v2.yml task.
