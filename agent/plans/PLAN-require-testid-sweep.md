# PLAN: enable custom/require-testid across private/account/web
Status: compacted
First-Seen: 2026-09-17
Owner: 97604f47
Full-Text: f7a5351a9 agent/PLAN-require-testid-sweep.md
Full-Text-Blob: d9c09956f72585468cd1af419f11a2077981748c
Record-Sig: 4b99cd88

## Why
`custom/require-testid` was configured at error level but switched `off` for `private/account/**/*.{ts,tsx}`, the one tree with 287 outstanding findings. Neither half proves the rule on its own: enabled-but-unlinted is a dead rule, lint-clean-but-disabled is a vacuous pass. The operator decided to ENABLE it rather than record it or delete it.

## Outcome
SHIPPED. Measured directly on 2026-09-06 rather than inferred from history: `npx eslint --print-config private/account/web/src/App.tsx` resolves `custom/require-testid` to severity 2 with the full element config, and the only surviving `'off'` is the test-files block at `eslint.config/tests.js:72`, exactly the scope the plan intended. The rule config now lives at
`eslint.config/typescript.js:257`, the monolithic eslint config having been split since. The sweep itself is a submodule commit adding 292 `data-testid` lines with zero removals, matching the plan's own "additions only, no e2e selector moved" accounting; the console-side switch and the submodule pointer bump landed together in 120cd9e73, so the tree never went red between them. The
follow-through the plan did not ask for is there too: `.ci/scripts/quality/lint-rule-liveness.mjs:113` pins a reach floor of 20 for this rule under `check:ci-lint-rule-liveness`, so it cannot quietly go dead.

## Lessons
- Proving a lint rule is live takes two measurements, not one: that it resolves
to error for a real file in the target tree, and that the tree lints clean.
- A reach floor is what stops an enabled rule from silently covering nothing
after a refactor moves its config, which is exactly what happened here when `eslint.config.js` became `eslint.config/`.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: done
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:08:53Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: eslint.config.js
Gates: check:ci-lint-rule-liveness, check:lint
Why-Source: author
Read-History: `git show d9c09956f72585468cd1af419f11a2077981748c` recovers the text; `git log --find-object=d9c09956f72585468cd1af419f11a2077981748c --all` names the commit

## History
- 2026-09-06T17:08:53Z compacted by 8f55d4f0 from `done` (record-sig 4b99cd88)
