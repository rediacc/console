# edit line 46: 'SFTPClient' -> 'SFTPClientZZZ'
Status: compacted
Owner: 97604f47
Full-Text: f7a5351a9 agent/PLAN-lint-rule-matrix-probe.md
Full-Text-Blob: 4470daee93042f1278a0e5a0589ff1c612a2e896
Record-Sig: 5fb8d870

## Why
The linting gate `check_lint_rule_liveness.py` proved only 3 of 30 enabled custom-namespace rules by spawning `npx eslint` once per rule (~90s), leaving 27 rules silent and invisible. It could not detect rules that were structurally deaf to the linted text, filename-only, or unreachable across the whole tree.

## Outcome
Completed 2026-08-15. Config-derived matrix now proves all 30 enabled rules fire (27 in-config, 2 via option-override temp fixtures, 1 via isolated instance) plus 3 negative controls and JSX reachability sweep. Single Node process runs in 11–13s. Replaces dead wiring (`custom/no-raw-api-calls`) and documents unreachable scope (`require-testid`). Landed at commit b9033101a.

## Lessons
- One rule was registered-then-off-ed twice with no enable block — dead wiring, not a dead rule. Delete the import, plugin registration, and two `off` lines; do not add it to `KNOWN_OFF`.
- Rules that enumerate directories by listing a path (cross-language-consistency, translation-coverage) need temp fixtures outside the repo — never inside a locales tree or they become a spurious language to every locale-set gate.
- Probing with `lintText` + virtual filePath avoids fixture files and `git status` noise, except filename-only rules (e2e-test-naming-convention) which need isolation because typed-linting rejects non-existent paths.
- Specimens that depend on live values (keys in en/cli.json, command-tree leaves, flag names) must carry precondition closures that fire BEFORE the lint. A stale specimen going silent reads exactly like a dead rule without the distinction.
- Reachability is structural, not textual — a rule can be enabled at `**/*.{js,jsx,ts,tsx}` and protect zero files if it only reports on JSX and is off in every .tsx/.jsx path. Requires deduped directory sweep, ~0.7s for 30 rules.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T15:30:34Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: eslint-rules/i18n/index.js, eslint.config.js, eslint-rules/e2e-test-naming-convention.js, eslint-rules/require-testid.js, eslint-rules/i18n/shared/require-path-option.js, package.json, scripts/ci-runner/manifest.ts, .github/workflows/ci-quality.yml, .ci/scripts/test/gates/test-gate-anti-vacuity.sh, eslint-rules/i18n/interpolation-match.js
Gates: check:ci-lint-rule-liveness, check:lint
Why-Source: model
Read-History: `git show 4470daee93042f1278a0e5a0589ff1c612a2e896` recovers the text; `git log --find-object=4470daee93042f1278a0e5a0589ff1c612a2e896 --all` names the commit

## History
- 2026-09-06T15:30:34Z compacted by 8f55d4f0 from `done` (record-sig 5fb8d870)
