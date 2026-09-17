# PLAN: narrow the `scripts/` harness rule in the CI scope map
Status: compacted
Full-Text: f7a5351a9 agent/PLAN-scope-gates-split.md
Full-Text-Blob: d1a4acd100bbcc1fbbace2d22f4d59663f7c2687
Record-Sig: 896eb492

## Why
The single `scripts/` rule in the CI scope map forced the full infra matrix for any change under `scripts/`, so an Apache-2.0 attribution-string check could schedule a ceph fork test. Worse, the comment defending the rule gave the WRONG reason: it cited gate-immunity, which the workflow already guarantees independently. A comment that misstates why a conservative rule exists is how
that rule later gets removed for bad reasons.

## Outcome
SHIPPED, AND THE HEADER IS WRONG. Its bolded "Not started." is false: deliverables D and F landed together in 18a41aa79, the same day the operator approved them. Measured 2026-09-06: `.ci/scripts/ci/scope-map.cjs:46` carries the zero-job `gates` module with the plan's verbatim rationale; the three ordered carve-out rules exist with the gates rule last at `:267`, ahead of the eslint
and compose harness rules that were deliberately left alone; the old single harness rule is gone; and the comment now argues from "no gated job executes it". All six test rows are in the scope-engine gate test, including the M4 row that pins the ZERO-JOB property. The rule block has since been extended twice more, which is evidence it is live and maintained rather than dormant.

## Lessons
- "Approved, not started" aged into a false claim within a single day, and
nothing in the file ever corrected it. The tree is the evidence.
- M4 was called non-negotiable for the right reason. Without a row pinning the
zero-job property, adding `gates` to a job-surface entry would silently undo the change while every existing row still read `reduced`.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: approved
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:08:54Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: run.sh, .ci/scripts/test/gates/test-positional-detector.sh, .ci/scripts/quality/check-command-tree.sh, .ci/scripts/build/prepare-cli-assets.sh, packages/cli/src/config/__tests__/plane-leaf-rule.test.ts, packages/www/src/utils/solution-video.ts
Gates: check:ci-account-scope-audit
Why-Source: author
Read-History: `git show d1a4acd100bbcc1fbbace2d22f4d59663f7c2687` recovers the text; `git log --find-object=d1a4acd100bbcc1fbbace2d22f4d59663f7c2687 --all` names the commit

## History
- 2026-09-06T17:08:54Z compacted by 8f55d4f0 from `approved` (record-sig 896eb492)
