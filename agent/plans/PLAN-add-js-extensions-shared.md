# PLAN: Make @rediacc/shared loadable as the ESM package it declares itself to be
Status: compacted
First-Seen: 2026-09-17
Owner: 97604f47
Full-Text: f7a5351a9 agent/PLAN-add-js-extensions-shared.md
Full-Text-Blob: 014f64c12a0ed8b7f90fef4df76be6e03b8ebeb2
Record-Sig: 486e34da

## Why
`packages/shared` declared itself an ESM package (`"type": "module"`, a 48-key `exports` map, `main` pointing at `./dist/index.js`) and Node could not load it. The build was a plain `tsc -p tsconfig.json`, and tsc emits relative specifiers verbatim, so every extensionless `export * from './defaults'` reached the emit unchanged and Node's ESM resolver refused it with
ERR_MODULE_NOT_FOUND on `dist/config/defaults`. Nothing caught it because no test loaded the real build the way Node would; the package was only ever consumed through bundlers and tsx, which resolve extensionless specifiers themselves. The plan's three legs were: fix the source specifiers, switch the compiler to the mode that ENFORCES them, and add a gate that imports the actual
built output.

## Outcome
SHIPPED, all three legs, measured on 2026-09-06.

- Source specifiers carry `.js`: `packages/shared/src/config/index.ts:1` now reads
`export * from './defaults.js';`. Across `packages/shared/src/**/*.ts` the only relative specifiers without a `.js` suffix are the 14 JSON imports that carry `with { type: 'json' }` (13 locale catalogues in `packages/shared/src/i18n/index.ts:15-27` and `packages/shared/src/regions/index.ts:24`), which is the correct spelling rather than a leftover.
- The enforcing compiler mode is on: `packages/shared/tsconfig.json:9-10` sets
`"module": "NodeNext"` and `"moduleResolution": "NodeNext"`.
- The gate exists and PASSES. `npm run check:ci-shared-esm-resolvable` exits 0 and
prints: "shared is importable as declared (134 built modules imported by Node, 27 concrete export targets present; 3-arm control fired)". Its script is `scripts/gates/check-shared-esm-resolvable.ts`.

THE HEADER SAID `Status: draft`, AND THE TREE DISAGREES. The work is in the tree and the gate that proves it runs. The header was simply never updated after the plan was executed; nothing about the draft status is true of the code today.

## Lessons
- A package can declare itself ESM, typecheck, pass every unit test, and still be
unloadable by Node, because bundlers and tsx resolve extensionless specifiers and Node does not. The only instrument that catches it is importing the real `dist/` the way Node would, which is what the gate now does.
- `tsc` emits relative specifiers verbatim, so the fix belongs in the SOURCE, not in
a post-build rewrite step. Switching `moduleResolution` to NodeNext is what turns the rule into something the compiler enforces instead of something a reviewer remembers.
- JSON imports are the exception that reads like a violation: they end in `.json`
with a `with { type: 'json' }` attribute and are correct as they stand, so a grep for "relative specifier without `.js`" reports 14 false positives in this package.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: draft
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:06:09Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: packages/shared/package.json, packages/shared/src/config/index.ts, packages/shared/src/services/machine/index.ts, private/account/tsconfig.json, private/account/web/tsconfig.json, private/account/e2e/tsconfig.json, packages/cli/tsconfig.json, packages/e2e-tests/package.json, packages/shared/src/regions/index.ts, packages/shared/src/i18n/index.ts, packages/cli/src/services/provision/region-discovery.ts, packages/shared/tsconfig.json, .claude/hooks/pre-bash/block-cli-bundle.sh, tsconfig.json, package.json, scripts/ci-runner/manifest.ts, .gitignore, packages/shared/src/subscription/__tests__/crypto.test.ts, packages/shared/src/renet-contract/index.ts
Gates: check:ci-parity, check:ci-shared-constant-duplication, check:ci-shared-esm-resolvable, check:types
Why-Source: auto
Read-History: `git show 014f64c12a0ed8b7f90fef4df76be6e03b8ebeb2` recovers the text; `git log --find-object=014f64c12a0ed8b7f90fef4df76be6e03b8ebeb2 --all` names the commit

## History
- 2026-09-06T17:06:09Z compacted by 8f55d4f0 from `draft` (record-sig 486e34da)
