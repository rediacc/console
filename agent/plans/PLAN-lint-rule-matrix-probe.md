# PLAN: Lint-rule liveness as a config-derived probe matrix
Status: compacted
First-Seen: 2026-09-17
Owner: 97604f47
Full-Text: f7a5351a9 agent/PLAN-lint-rule-matrix-probe.md
Full-Text-Blob: 4470daee93042f1278a0e5a0589ff1c612a2e896
Record-Sig: 5fb8d870

## Why
`check_lint_rule_liveness.py` planted a violation per rule and asserted the rule reported it, which is a genuine control and was fenced into near-uselessness by three constants: one probe path (`packages/www/src/i18n/translations/tr.json`), a `key.startswith("i18n/")` namespace filter that dropped `custom/` and `i18n-source/` entirely, and a hand-listed five-entry SPECIMENS table.
Measured at that probe it proved 3 rules and was silent about the other 27. The plan replaces the hard-coded probe with a matrix whose universe is derived from `eslint.config.js` itself, so no enabled custom rule can sit outside the gate's view without the gate saying so.

## Outcome
SHIPPED, and verified by RUNNING it on 2026-09-06 rather than by reading the header. `npm run check:ci-lint-rule-liveness` exits 0 and prints:

    30 enabled custom/i18n rule(s) each fired on a planted violation (35
    registered, 5 off by documented decision, 0 enabled-but-unreachable and
    recorded); 3 negative controls stayed silent; 11.0s
      JSX reachability over 30 directory representative(s): require-testid=27,
      no-hardcoded-text=18, require-data-track=3, seo-no-vague-anchor-text=3,
      seo-require-img-alt=3

That is the matrix this plan asked for, with its own negative controls holding, and the 3-of-30 blind spot closed. The engine is `.ci/scripts/quality/lint-rule-liveness.mjs` (42,030 bytes), added by commit 120cd9e73, "feat(backup): chunk-store cold path, rclone decommission, stop-hook cadence"; the Python entry point `check_lint_rule_liveness.py` survived as the registered
`check:ci-lint-rule-liveness` script and now carries the 2026-08-15 note about the 3-of-30 scope in its own docstring. Runtime measured 11.0s.

## Lessons
- "Does the rule have findings" cannot separate a healthy rule on a clean tree from
a rule that is structurally unable to fire. Both report zero. Planting the violation is the only test that distinguishes them, which is why this gate is itself a control run per rule.
- A control with a hard-coded specimen list is a control whose SCOPE is the thing
nobody checks. Three constants held this one to 3 rules of 30 while every individual assertion in it stayed true.
- The engine landed inside an unrelated-sounding commit (a backup cold-path
commit), so searching commit subjects for "lint" would have concluded the work never shipped. `git log --diff-filter=A -- <path>` answered it in one call.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:02:33Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: e87fa3ce
Touched: eslint-rules/i18n/index.js, eslint.config.js, eslint-rules/e2e-test-naming-convention.js, eslint-rules/require-testid.js, eslint-rules/i18n/shared/require-path-option.js, package.json, scripts/ci-runner/manifest.ts, .github/workflows/ci-quality.yml, .ci/scripts/test/gates/test-gate-anti-vacuity.sh, eslint-rules/i18n/interpolation-match.js
Gates: check:ci-lint-rule-liveness, check:lint
Why-Source: auto
Read-History: `git show 4470daee93042f1278a0e5a0589ff1c612a2e896` recovers the text; `git log --find-object=4470daee93042f1278a0e5a0589ff1c612a2e896 --all` names the commit

## History
- 2026-09-06T17:02:33Z compacted by 8f55d4f0 from `done` (record-sig 5fb8d870)
