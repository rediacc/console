# PLAN: judge gate-worthiness scoring and surface scope beyond Quality
Status: compacted
Owner: 9d92d9b6
Full-Text-Blob: 9fd5358ec06422c99edfb94e4c9473dfbf2fbc2a
Record-Sig: 940f9b95

## Why
The Stop hook's regression-gate judge exhibited three structural failures: it could not weigh defect severity or scope (no proportionality), it verified gate names existed but not that they covered the changed code (rubber-stamp effect), and it routed 99% of findings to the Quality lane while ignoring 26 other ci.yml jobs whose logic could be tested offline (surface monoculture).
The incident was a three-line ruff-format fix flagged as unprotected when an existing Python linter gate already covered it — the judge could not see it because it never examined the changed code.

## Outcome
Finished design for two-stage judge refactor: Stage A verifies coverage using linters on pre/post-fix blobs without model calls; Stage B scores on deterministic factors (diff scope, severity, recurrence) routing to MANDATE, REBUT-AND-VERIFY, or PROPORTIONATE-NO-GATE. Expanded surface routing from gates-only to cover pipeline, workflow, runtime-only, unit, e2e, ops, and hooks, with
generated ci.yml inventory. Preserves prior lessons (security/data-loss hard overrides, by-construction blind spots) while fixing proportionality and monoculture. Draft status as of 2026-09-20; never implemented.

## Lessons
- Empirical observation (running the real tool on the real blob) outranks citation (checking gate-name existence). Verification against artifacts, not registries, is the reliability model the repo enforces.
- Proportionality is a prerequisite, not a feature. Without visible defect-severity and scope factors, a one-line format fix is treated identically to a security bypass; the judge becomes worse than useless.
- The routing question must ask 'which ci.yml job catches this' first, then map to surface. Generating the inventory from source prevents rot; hand-typed lists diverge.
- The mechanism closes a rubber stamp (58 prior settles took an unverified gate-existence path) while preserving earned paranoia from prior incidents (i18n blindness, security rules).
- Three missing test cases in the existing offline battery are a wiring gap in an otherwise complete harness (117 gate-test entries already exist for other jobs).

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: draft
Compacted-By: d778be9d
Compacted-At: 2026-09-20T17:57:19Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce, f2757830
Touched: package.json, scripts/ci-runner/manifest.ts, .claude/skills/testing/SKILL.md, .claude/skills/testing/gates.md, .claude/hooks/stop/wl_classsweep.py
Gates: check:ci-actionlint, check:ci-python-lint, check:ci-shell-format, check:ci-shell-lint, check:ci-test-gate-wiring, check:ci-test-scripts-reachable, check:ci-workflow-gates, check:ci-workflow-invariants, check:lint
Why-Source: model
Read-History: `git show 9fd5358ec06422c99edfb94e4c9473dfbf2fbc2a` recovers the text; `git log --find-object=9fd5358ec06422c99edfb94e4c9473dfbf2fbc2a --all` names the commit

## History
- 2026-09-20T17:57:19Z compacted by d778be9d from `draft` (record-sig 940f9b95)
