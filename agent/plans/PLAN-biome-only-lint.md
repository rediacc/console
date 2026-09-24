# PLAN: biome-only linting and TypeScript 7

Status: draft
Owner: d778be9d
Updated: 2026-09-24

## Finding

The operator ruled on 2026-09-24 (worklist `#ecb07ba6`, which replaces `#28be556a`). What stands in the way, measured on this tree:

1. **The ESLint surface.** It is one root, `eslint.config.js:29-36`, which pulls in six modules in last-match-wins order: `eslint.config/{ignores,typescript,i18n,tests,packages,tooling}.js`. There are no package-level config files. The only package-level entry points are the scripts at `packages/cli/package.json:15` and `packages/e2e-tests/package.json:8-9`.
   - About 75 core and plugin rule settings.
   - 30 enabled repo rules: 18 `custom/*` rules, 1 `i18n-source/interpolation-match`, and 11 `i18n/*` JSON rules. This matches the "30 enabled" count in `eslint-rules/__tests__/harness.js:12`.
   - 5 i18n rules deliberately off (`eslint.config/i18n.js:100-120`).
2. **Biome is installed but barely used.** `node_modules/@biomejs/biome` is 2.5.14, but its linter is off globally (`biome.json:10-12`) and on only for `private/account` (`biome.json:110-135`). The `$schema` still says 2.3.8 (`biome.json:2`).
   - 2.5.14 has most of the ESLint equivalents, many of them in `nursery`.
   - It supports GritQL plugins, including per-override `plugins` with `includes`, as `configuration_schema.json` confirms (`OverridePattern.plugins`, `PluginWithOptions`).
3. **TypeScript 7.0.2 has no classic compiler API.** Its package root export is only `./lib/version.cjs` (`npm view typescript@7.0.2 exports`). Two files use `import ts from 'typescript'` and will break. The ruling doesn't mention them:
   - `scripts/gates/check-control-in-string.ts:40`
   - `packages/cli/src/__tests__/renet-access-ledger.test.ts:4`

   No other TS peer blocks 7 once typescript-eslint is gone:
   - astro keeps its own nested `typescript@5.9.3`.
   - `i18next` and `cosmiconfig` peers are optional and satisfied.
   - knip 6 has no TS peer.
4. **The repo rules don't need type information.** None of them use `parserServices`. Only two use a scope API: `eslint-rules/require-translation.js:83` and `eslint-rules/i18n/interpolation-match.js:241`. Only one uses `getAncestors` (`eslint-rules/no-unawaited-drizzle-terminator.js:199`). None use esquery selectors or `:exit` handlers. The only enabled rule with a fixer is `prefer-const-arrays`.
   - Every JSON rule is a single `Document(node)` visitor over the momoa AST.
   - Both parsers the rules need are already in the lockfile at pinned versions: `oxc-parser@0.148.0` (via knip) and `@humanwhocodes/momoa@3.3.10` (via `@eslint/json`).
   - So the rules can run unchanged under a small scripts-side host, without ESLint.
5. **Biome can't express all of the policy:**
   - `noExcessiveLinesPerFile` has no `skipComments`, so `max-lines` at 512 would change meaning in this heavily commented tree (`eslint.config/typescript.js:184`).
   - `noUnusedVariables` always exempts `_`-prefixed names, and this repo bans them (`eslint.config/typescript.js:172-176`).
   - `useExpect` has no `assertFunctionPatterns` (`eslint.config/tests.js:36-47`).
   - `noMisusedPromises` has no `checksVoidReturn`.
6. **Suppression comments will stop working.** There are 176 `eslint-disable`/`-enable` lines in console and 6 in account (line 1 of `private/account/web/src/pages/*.tsx`). Nothing will honour them after the cut.
   - The console ones break down as: `no-console` 140, `@typescript-eslint/require-await` 17, `no-restricted-syntax` 6, `max-lines` 2, `no-control-regex` 2, `no-deprecated` 3.
   - The hook blocks writing `biome-ignore` (`.claude/rediacc_hooks/guards/block_suppressions.py:59`). So the replacements must be listed per file in config, not added as inline comments.
7. **Things only ESLint kept alive:**
   - The override `brace-expansion@^1.1.7` (`package.json:474`, reason at `:503`). Its six consumers are all eslint/minimatch@3 edges, so check:ci-suppression-liveness will condemn it.
   - Four blocklist entries: `.ci/policy/.deps-upgrade-blocklist:19`, `:33`, `:39` and `:42` (the typescript BLOCKER).
   - Two tests that use `eslint` as the "still declared" control: `.ci/rediacc_ci/tests/gates/test_gate_suppression_liveness.py:217-224` and `.ci/rediacc_ci/tests/gates/test_gate_policy_liveness_floors.py:95-98`.
8. **Lockfile tooling.** The npm pin is `NPM_VERSION=11.20.0` (`.devcontainer/toolchain.env:54`), but local npm is 11.17.0, so use `npx -y npm@11.20.0`.
   - The release-age window is 1440 minutes (`.ci/config/release-age.json`), so `--before=2026-09-23T00:00:00Z`.
   - `typescript@7.0.2` was published 2026-07-08, well outside the window.
   - `workers/proxy/package.json:15` also pins `typescript ^6.0.3` and has its own lockfile. It isn't on the operator's list but belongs in "everywhere".
9. **No git-side hooks run ESLint.** There is no husky, no lint-staged and no `core.hooksPath`. `scripts/pre-commit-check.sh:128` is a manual script and only prints text.

Rejected alternative: keep ESLint core with a non-typescript-eslint parser, just for the repo rules. It contradicts the ruling, still needs an ESTree-TS parser, and keeps the plugin and minimatch@3 tree. The host in step 3 does the same work with two direct devDependencies that are already in the lockfile.

## Rule map

Key: **B** means a Biome rule, with overrides mirroring the ESLint file scope. **H** means the `ci-source-rules` (proposed gate) host gate, which runs the rule module unchanged. **G** means a GritQL plugin under `biome-plugins/`. **S** means a new scripts/gates check. **Drop** means no replacement, with the reason given.

| ESLint rule (file:line) | Replacement |
|---|---|
| `js.configs.recommended` (eslint.config/typescript.js:49) | B: `recommended` set for `**/*.{js,mjs,cjs}` plus `correctness/noUndeclaredVariables` (the old `no-undef`). tsc covers `.ts`. |
| `tseslint.configs.recommended` (:52) | B: recommended TS rules (`suspicious/noTsIgnore`, `noNonNullAssertedOptionalChain`, `noUnsafeDeclarationMerging`, `style/noNamespace`, `noCommonJs`, `suspicious/noUnusedExpressions`, …) |
| `@typescript-eslint/no-explicit-any` (:167) | B: `suspicious/noExplicitAny` |
| `no-inferrable-types` (:168) | B: `style/noInferrableTypes` |
| `no-unused-vars` args `^_`, vars `^$` (:173) | B: `correctness/noUnusedVariables`, `noUnusedImports`, `noUnusedFunctionParameters`. Plus G: `no-underscore-var.grit`, because Biome always exempts `_x` locals. |
| `no-empty-interface`, `no-empty-object-type` off (:177-178) | B: `suspicious/noEmptyInterface` off, `complexity/noBannedTypes` off |
| `no-deprecated` (:179) | Partial. B: `suspicious/noDeprecatedImports`. Member-level use of deprecated APIs: **Drop**, because it needs the TS checker and TS 7 has no plugin API. |
| `no-console` allow warn/error (:182) | B: `suspicious/noConsole {allow:["warn","error"]}` |
| `no-debugger` (:183) | B: `suspicious/noDebugger` |
| `max-lines` 512, skip blanks and comments (:184) | S: `check-max-lines.ts` (oxc comment ranges). Carries the exemptions from eslint.config/tooling.js:37-44, eslint.config/i18n.js:370-376, eslint.config/tests.js:50 and eslint.config/packages.js:52, plus the two file-level disables in `packages/cli/src/services/account/license.ts:1` and `packages/cli/src/services/executor/local-executor.ts:1`. |
| `no-floating-promises` (:187) | B: `nursery/noFloatingPromises` (Biome's own inference, weaker than tsc) |
| `await-thenable` (:188) | B: `nursery/useAwaitThenable` |
| `no-misused-promises` checksVoidReturn:false (:189) | B: `nursery/noMisusedPromises`. There is no option for this, so measure it; turn it off per glob if it floods. |
| `no-unnecessary-type-assertion` (:190) | **Drop**: needs the TS checker, and TS 7 has no plugin API. A redundant assertion is not wrong code. |
| `no-unnecessary-condition` (:191) | B: `suspicious/noUnnecessaryConditions` |
| `require-await` (:192) | B: `suspicious/useAwait` |
| `use-unknown-in-catch-callback-variable` (:193) | **Drop**: needs types. `noExplicitAny` still rejects `(e: any)`, and `strict` already gives `useUnknownInCatchVariables` for try/catch. |
| `prefer-nullish-coalescing` (:196; eslint.config/tests.js:63 ignorePrimitives) | B: `nursery/useNullishCoalescing`. There is no ignorePrimitives option: turn it off for the eslint.config/tests.js:18-23 globs if findings appear. |
| `prefer-optional-chain` (:197) | B: `complexity/useOptionalChain` |
| `prefer-includes` (:198) | B: `nursery/useIncludes` |
| `prefer-for-of` (:199) | B: `style/useForOf` |
| `prefer-string-starts-ends-with` (:200) | B: `nursery/useStringStartsEndsWith` |
| `array-type` array (:201) | B: `style/useConsistentArrayType {syntax:"shorthand"}` |
| `consistent-type-assertions` (:202) | The `as` style needs nothing (TSX can't use angle brackets, and .ts files have none today). The object-literal part: G `no-object-literal-assertion.grit` if measured findings are 0, otherwise **Drop**. |
| `require-array-sort-compare` (:298) | B: `suspicious/useArraySortCompare` |
| `prefer-readonly` (:301) | B: `style/useReadonlyClassProperties` |
| `prefer-regexp-exec` (:317) | B: `nursery/useRegexpExec` |
| `no-redundant-type-constituents` (:318) | **Drop**: needs types. It is a style check. |
| `react` recommended (:159), `react-in-jsx-scope`/`prop-types` off (:160-161) | B: `correctness/useJsxKeyInIterable`, `noChildrenProp`, `noRenderReturnValue`, `suspicious/noDuplicateJsxProps`, `noCommentText`, `security/noBlankTarget`, `noDangerouslySetInnerHtmlWithChildren`, `nursery/noReactStringRefs`. `display-name`, `no-deprecated` and `no-unescaped-entities`: **Drop** (no equivalent and low risk under React 19). |
| `react-hooks` recommended v7 (:164) | B: `correctness/useHookAtTopLevel`, `useExhaustiveDependencies`, `noNestedComponentDefinitions`, `nursery/noComponentHookFactories`. The compiler rules (purity, refs, set-state-in-effect, …): **Drop**, because the repo does not run React Compiler (no `babel-plugin-react-compiler` in www or account/web). |
| `react/hook-use-state` (:267) | **Drop**: naming only. Check `nursery/useReactNamingConvention` first and adopt it if it covers `[x, setX]`. |
| `react/button-has-type` (:268) | B: `a11y/useButtonType` |
| `react/jsx-no-useless-fragment` (:269) | B: `complexity/noUselessFragments` |
| `react/self-closing-comp` (:270) | B: `style/useSelfClosingElements` |
| `react/jsx-boolean-value` never (:271) | **Drop**: cosmetic. Biome's `noImplicitBoolean` enforces the opposite. |
| `react/jsx-curly-brace-presence` (:272) | B: `style/useConsistentCurlyBraces` |
| `react/forbid-elements` (:344) | B: `correctness/noRestrictedElements {elements:{div,span,button,input,select}}` with the same messages |
| `eqeqeq` null:ignore (:279) | B: `suspicious/noDoubleEquals {ignoreNull:true}` |
| `prefer-const`, `no-var` (:280-281) | B: `style/useConst`, `suspicious/noVar` |
| `object-shorthand` (:282) | B: `style/useConsistentObjectDefinitions {syntax:"shorthand"}` |
| `prefer-template` (:283) | B: `style/useTemplate` |
| `prefer-arrow-callback` (:284) | B: `complexity/useArrowFunction` |
| `no-else-return`, `no-lonely-if` (:285-286) | B: `style/noUselessElse`, `style/useCollapsedElseIf` |
| `no-implicit-coercion` allow `!!` (:287) | B: `complexity/noImplicitCoercions {allowDoubleNegation:true}` |
| `sonarjs/cognitive-complexity` 10 (:292; exemptions eslint.config/tooling.js:51-61) | B: `complexity/noExcessiveCognitiveComplexity {maxAllowedComplexity:10}`, with a per-file override for the six listed files |
| `max-nested-callbacks` 3 (:295; eslint.config/tests.js:51 → 5) | B: `nursery/noExcessiveNestedCallbacks {max:3}`, and `{max:5}` in the tests override |
| `no-nested-ternary` (:304) | B: `style/noNestedTernary` |
| `regexp/strict` (:307) | Partial. B: `complexity/noUselessEscapeInRegex`, `correctness/noEmptyCharacterClassInRegex`. Annex-B ambiguity: **Drop**, because Biome parses regexes strictly. |
| `unicorn/prefer-node-protocol` (:310) | B: `style/useNodejsImportProtocol` |
| `unicorn/prefer-number-properties` (:311) | B: `style/useNumberNamespace`, `suspicious/noGlobalIsNan`, `noGlobalIsFinite` |
| `unicorn/prefer-string-replace-all` (:312) | **Drop**: modernisation only, no equivalent |
| `unicorn/no-array-push-push` (:313) | **Drop**: modernisation only, no equivalent |
| `unicorn/no-negated-condition` (:314) | B: `style/noNegationElse` |
| `no-restricted-imports` (:323-341) | B: `style/noRestrictedImports` (`paths` with `importNames`, and `patterns` with `group`) |
| `no-restricted-syntax` constant alias (:357) | G: `no-constant-alias.grit`. Replaces the 6 disables: exclude `packages/e2e-tests/src/constants.ts`. |
| `no-restricted-syntax` `var(--ant-` (:361) | G: `no-ant-css-var.grit` |
| `no-restricted-syntax` t() defaultValue (:365) | G: `no-t-default-value.grit` |
| `no-restricted-syntax` `style`/`styles` JSX attribute (:369) | G: `no-inline-style-prop.grit` (`nursery/noInlineStyles` covers only `style`) |
| `no-restricted-syntax` exported type alias (:373) | G: `no-exported-type-alias.grit` |
| `no-restricted-syntax` db.transaction (eslint.config/packages.js:81, :101) | G: `no-d1-transaction.grit`, scoped to `private/account/**` |
| `no-restricted-imports` routes to db/drizzle (eslint.config/packages.js:94) | B: `style/noRestrictedImports` override for `private/account/src/routes/**`, excluding `test.ts` |
| `no-restricted-syntax` routes dynamic import (eslint.config/packages.js:105-112) | G: `no-route-db-dynamic-import.grit` |
| `no-restricted-syntax` sendEmail literal copy (eslint.config/i18n.js:350-363) | G: `no-email-literal-copy.grit`, scoped to `email.service.ts` |
| `no-restricted-syntax` it/test/describe.skip (eslint.config/tests.js:94-114) | B: `suspicious/noSkippedTests`, scoped to `packages/shared/src/**/__tests__/**` |
| `no-regex-spaces` off (scripts) | B: `complexity/noAdjacentSpacesInRegex` off in the same overrides |
| `no-control-regex` (2 disables) | B: `suspicious/noControlCharactersInRegex`, off for `packages/shared/src/utils/progress.ts` and `packages/www/scripts/lib/dev-server-ready.js` |
| `@typescript-eslint/no-require-imports` off for .cjs (eslint.config/tooling.js:133) | B: `style/noCommonJs` off for `**/*.cjs` |
| `jsx-a11y/alt-text` (eslint.config/packages.js:159) | B: `a11y/useAltText` |
| `playwright/no-wait-for-timeout` (eslint.config/tests.js:32) | B: `nursery/noPlaywrightWaitForTimeout` |
| `playwright/no-focused-test` (eslint.config/tests.js:33) | B: `suspicious/noFocusedTests` |
| `playwright/valid-expect` (eslint.config/tests.js:35) | Partial. B: `nursery/noPlaywrightMissingAwait`. Remainder: **Drop**. |
| `playwright/expect-expect` with patterns (eslint.config/tests.js:36-47; stubs :77-88) | B: `nursery/useExpect` if it's clean with the three stub files excluded. Otherwise H: port as `e2e-expect-expect` (about 40 lines, same `assertFunctionPatterns`). |
| `json/no-duplicate-keys` (eslint.config/i18n.js:88, eslint.config/packages.js:199, :228) | B: `suspicious/noDuplicateObjectKeys` on JSON. Add the `private/account/**/i18n/locales/**/*.json` includes with the formatter off for them. |
| `import` plugin and resolver settings (eslint.config/typescript.js:89, :146-155) | **Drop**: no `import/*` rule is enabled. knip already owns unresolved and unused imports. |
| `reportUnusedDisableDirectives` (eslint.config/ignores.js:68-72) | B: unused `biome-ignore` is reported natively. H: refuses any `eslint-disable`/`-enable` token left in scope. |
| Generated-file relaxations (eslint.config/i18n.js:369-387) | B: already excluded (`biome.json:90-91`). Add `!**/api-schema.zod.ts` to the lint scope. |
| JSON-file JS rule disables (eslint.config/i18n.js:334-344) | Not needed: Biome JS rules don't run on JSON. |
| scripts and tooling relaxations (eslint.config/typescript.js:58-80, eslint.config/packages.js:243-262, eslint.config/tooling.js:76-123) | B: overrides with the same rules off (`noConsole`, cognitive, `useNumberNamespace`, `noNegationElse`, `noNestedTernary`, `useTemplate`, `noAdjacentSpacesInRegex`, `noFloatingPromises`, `useAwait`) |
| Account "all off" block (eslint.config/packages.js:22-87) | B: the parity override uses `includes: ["**","!private/account/**"]`. The existing account override keeps `recommended` and `noFloatingPromises`. |
| www disables (eslint.config/packages.js:147-155) | B: `noRestrictedElements` and `noRestrictedImports` off in the `packages/www/src/**` override |
| `custom/require-translation` (eslint.config/i18n.js:170 CLI, :204 account web) | H |
| `custom/require-translation-key-arg` (eslint.config/i18n.js:174) | H |
| `i18n-source/interpolation-match` (eslint.config/i18n.js:180, :208) | H |
| `translation-helpers.js` (not a rule; imported by the three above) | Kept as-is and imported by the H rules |
| `custom/no-hardcoded-cli-text`, `require-command-summary`, `no-positional-cli-syntax-source`, `no-direct-sftp-client` (eslint.config/i18n.js:167-188) | H |
| `custom/no-hardcoded-text` (eslint.config/i18n.js:207). The 6 file-level disables in account web: | H. The disables become explicit `ignores` in the host config, each with its reason. |
| `custom/no-duplicate-translation-props`, `prefer-const-arrays`, `no-hardcoded-nullish-defaults`, `require-testid` (eslint.config/typescript.js:209-265; js off eslint.config/tooling.js:22-27) | H. The prefer-const-arrays fixer is not ported, only reported; the text is unchanged. |
| `custom/no-unawaited-drizzle-terminator` (eslint.config/packages.js:132) | H |
| `custom/seo-*` ×4, `require-data-track` (eslint.config/packages.js:157-182) | H |
| `custom/e2e-test-naming-convention` (eslint.config/tests.js:29) | H |
| `i18n/no-positional-cli-syntax`, `cli-flag-consistency`, `cross-language-consistency`, `translation-coverage`, `no-undefined-cli-flags`, `no-untranslated-values`, `interpolation-consistency` (eslint.config/i18n.js:106-138) | H (momoa `Document`). Deduplicating against check-i18n-placeholders and check-translation-completeness is a follow-up; it is out of scope here. |
| `i18n/seo-title-length`, `seo-description-length`, `seo-no-duplicate-h1-title`, `no-untranslated-tutorial-transcript-values` (eslint.config/packages.js:203-233) | H |
| 5 rules off (`no-empty-translations`, `sorted-keys`, `key-naming-convention`, `translation-staleness`, `no-unused-keys`) | Stay off. Their specs keep running under the H tester (check:ci-lint-rule-units). |

## Boxes

**Phase 0: baseline while ESLint still exists**

- [ ] Record a green `npm run check:lint` on HEAD. Snapshot ESLint's resolved config for every tracked path, filtered to the `custom/*`, `i18n/*` and `i18n-source/*` rule ids plus `max-lines`, using `eslint-rules/__tests__/config-resolution-differential.mjs`. Keep this as the parity oracle.
- [ ] Run ESLint with only the custom, i18n and `max-lines` rules on HEAD plus one planted defect per rule (reuse the probes in `.ci/scripts/quality/lint-rule-liveness.mjs`). Save the normalised `(file, line, col, ruleId)` tuples.

**Phase 1: build the replacements (ESLint still present, so differentials can run)**

- [ ] Add exact root devDependencies `oxc-parser@0.148.0` and `@humanwhocodes/momoa@3.3.10`. Both are already locked, so no new tarballs.
- [ ] Write `scripts/lib/rule-host.ts`:
  - Parse with oxc-parser (ESTree, `range`, tsx/ts/js by extension) and momoa (`ranges`).
  - Set `parent` on each node, walk in ESTree order, and dispatch `Type(node)` and `Document(node)` visitors.
  - Provide `context.{options, report, filename, physicalFilename, cwd}` and `sourceCode.{getText, getAncestors, getScope}`. The scope shim only needs Program, function, arrow, non-body block, for, switch, catch and class scopes, with `block`, `variables[].defs[].node` and `upper`.
- [ ] Write `scripts/data/source-rules.ts`. It is a flat per-rule `{files, ignores, options}` table translated from i18n.js :146-331 (including the `i18nLocaleConfigs` generator), packages.js :128-235, tests.js :17-71 and tooling.js :22-27. There is no cascade, so order stops being a contract. Replace the 6 account `eslint-disable custom/no-hardcoded-text` comments with `ignores` entries, each with a reason.
- [ ] Add `scripts/gates/check-source-rules.ts` with a `---- gate ----` header and `--selftest` (planted-defect controls). It fails on any `eslint-disable`/`eslint-enable` token in its scope.
- [ ] Differential:
  - Host config resolution must equal the Phase 0 ESLint snapshot for every path.
  - Host findings must be byte-identical to the Phase 0 tuples, both on HEAD and on the planted tree.
  - Record both results in this plan.
- [ ] Port `eslint-rules/__tests__/harness.js:40-41` (`RuleTester` and `@eslint/json`) to a host-backed tester, and move `scripts/gates/check-lint-rule-units.ts` onto it. The 5 off-rule specs still run.
- [ ] Port `.ci/scripts/quality/lint-rule-liveness.mjs:480-716` and `check_lint_rule_liveness.py` :52-57. Derive the universe from `scripts/data/source-rules.ts` instead of `eslint.config.js`, and add a Biome half: every `.grit` plugin must fire on a planted violation.
- [ ] Add `scripts/gates/check-max-lines.ts`. It counts lines that are not blank and not comments, with a 512 cap and the exemptions listed in the Rule map. Check it against ESLint `max-lines` on HEAD (0 findings on both) and on a planted 513-line file.
- [ ] Write the 9 GritQL plugins in `biome-plugins/`, each scoped with `includes`. Add `biome-plugins/` to `.ci/policy/tree-shape.json` in place of `eslint.config.js` and `eslint.config` (`:59`, `:86`). Add `.grit` to `.ci/policy/.language-policy-allowlist` if `check:ci-language-policy` rejects it.
- [ ] Rewrite `biome.json`:
  - Set `$schema` to 2.5.14 and `linter.enabled: true`.
  - Add a console-parity override with `includes: ["**","!private/account/**"]` and `recommended: false` plus the mapped B rules.
  - Add overrides for tests, scripts/tooling, `.cjs`, www, and account routes.
  - Add per-file overrides replacing the 140 `no-console`, 17 `require-await` (the four `packages/e2e-tests/tests/{16,20,21,22}-*.test.ts` files) and 2 `no-control-regex` disables. List files explicitly; no globs.
  - Add the account locale JSON includes.
- [ ] Run `npx biome lint . --max-diagnostics=none` and record per-rule counts. For each rule with findings, record fix or scoped-off with a reason. Expect differences in cognitive complexity, nullish coalescing and misused promises.
- [ ] Delete every `eslint-disable`/`-enable` line: 176 in console, 6 in `private/account/web/src/pages/*.tsx :1`. Use Edit, or a Bash-scripted edit. A full-file Write that still contains another token is refused by `block_suppressions.py`.

**Phase 2: cut over**

- [ ] `package.json`:
  - `:321` `check:lint` becomes `biome lint . --error-on-warnings`. Delete the shards at `:322-325`.
  - `:352` `fix:lint` becomes `biome lint --write .`.
  - `:365` `lint` becomes `biome lint .`.
  - `:255` `check:ci-account-layer-isolation` becomes `biome lint private/account/src/routes/ --error-on-warnings`.
  - Add `ci-source-rules` (proposed gate) and `ci-max-lines` (proposed gate).
- [ ] `packages/cli/package.json:15` becomes `biome lint src`. `packages/e2e-tests/package.json:8-9` becomes `biome lint src tests` (and `--write`).
- [ ] `scripts/ci-runner/manifest.ts`:
  - Collapse `:78-158` (check:lint plus 4 shards) into one `gate: true` entry with `leaves: ['biome']`. Delete the `gate:false` sharding comment block.
  - `:3382` leaves becomes `['biome']`.
  - Update `:2067` paths and `:2597-2606` (drop `eslint.config.js`, add `biome-plugins/**` and `scripts/data/source-rules.ts`).
  - Register the two new gates.
- [ ] Regenerate `scripts/ci-runner/gates.lock.json` (`:40-110`, `:2146`, `:2733`, `:3608`) and `.github/workflows/ci-quality.yml`: the Lint step `:1067-1070`, the lock map `:1198`, and the new steps via `gate-bind --write`. Reword the comment at `:917-922`; the worker-deps install stays for knip.
- [ ] Rewrite `.ci/scripts/quality/check_lint_scope_coverage.py` onto Biome. `:104-110` `LINT_ROOT_SCRIPTS`/`ESLINT_RUNNER` and `:154-157` `npx eslint` go. The oracle becomes Biome's own "Checked N files" plus a probe per candidate path, the same pattern as `.ci/scripts/quality/check_format_scope.py:48-60`. `ESLINT_EXEMPT` (`:66-100`) becomes `BIOME_EXEMPT`. Add any missing roots it reports (for example `packages/locales/*.js`) to `biome.json` `files.includes`.
- [ ] Delete `eslint.config.js`, `eslint.config/`, `scripts/eslint-heap.sh` and `eslint-rules/__tests__/config-resolution-differential.mjs`. Update the references:
  - `scripts/data/domains.json:155-160`
  - `.ci/scripts/ci/scope-map.cjs:56` (use `biome.json`) and `:184`
  - `knip.jsonc:62-71`
  - `.devcontainer/devcontainer.json:69` and `.devcontainer/download-extensions.sh:18` (drop the eslint extension; the biome one is already at `:68`/`:17`)
  - `.github/pull_request_template.md:64`
  - `.ci/legacy/run-legacy.sh:329`, `scripts/pre-commit-check.sh:128`, `.ci/rediacc_ci/proc.py:32`
  - `docs/agent-reference/{TRAPS,ci-gates}.md`
- [ ] Fix the tests pinned to the old shape:
  - `.ci/rediacc_ci/tests/gates/test_gate_gate_lanes.py:570-606`: the heavy-count floors lose four check:lint ids.
  - `.ci/rediacc_ci/tests/gates/test_gate_suppression_liveness.py:217-224` and `.ci/rediacc_ci/tests/gates/test_gate_policy_liveness_floors.py:95-98`: swap the `eslint` control for a still-declared root dependency (`@biomejs/biome`).
  - Update the prose in `.ci/rediacc_ci/tests/gates/test_gate_greenlight_closure_trace.py:17` and `.ci/rediacc_ci/tests/gates/test_gate_paths_exist.py:48-54`.

**Phase 3: dependencies and TypeScript 7**

- [ ] Root `package.json`:
  - Remove `:413` `@eslint/js`, `:414` `@eslint/json`, `:417-428` (both `@typescript-eslint/*`, `eslint`, `eslint-import-resolver-typescript`, and the 8 `eslint-plugin-*`), `:430` `globals` and `:436` `typescript-eslint`.
  - Change `:435` typescript to `^7.0.2`.
  - Remove override `:474` `brace-expansion@^1.1.7` and reason `:503`, once `npm ls brace-expansion` shows no `^1` edge left. Reword the eslint mention in the `:479` `glob` reason.
- [ ] Set typescript to `^7.0.2` in `packages/cli/package.json:65`, `packages/e2e-tests/package.json:59`, `packages/provisioning/package.json:16`, `packages/shared/package.json:20` and `workers/proxy/package.json:15`.
- [ ] Submodule, which lands first: typescript `^7.0.2` in `private/account/package.json:64` and `private/account/web/package.json:47`. This reverses `f7d460a`.
- [ ] `.ci/policy/.deps-upgrade-blocklist`: delete `:18-19` (`@eslint/js`), `:32-33` (`eslint-plugin-unicorn`), `:38-39` (`eslint`) and `:41-42` (the typescript BLOCKER).
- [ ] Regenerate lockfiles with the pinned npm, inside the window, in order: `private/account`, `private/account/web`, `workers/proxy`, root.
  `npx -y npm@11.20.0 install --package-lock-only --ignore-scripts --before=2026-09-23T00:00:00Z`
  Then `npx -y npm@11.20.0 ci --ignore-scripts && npm run install:natives`.
- [ ] Port the two TS-API users to oxc-parser: `scripts/gates/check-control-in-string.ts:40` and `packages/cli/src/__tests__/renet-access-ledger.test.ts:4`. Declare oxc-parser in `packages/cli` devDependencies if `check:ci-runtime-imports-are-deps` asks for it.
- [ ] Run `npm run typecheck` on 7.0.2 and fix whatever TS 7 reports (count not measured yet). Confirm `tsc -b packages/shared packages/provisioning packages/cli` works under TS 7's build mode.
- [ ] Follow-up, not in this wave: `tsconfig.json:32-39` justifies having no `files` only because of ESLint's `projectService`. Revisit `"files": []` together with `check:ci-typecheck-scope-coverage`. Renaming `eslint-rules/` is also deferred: `scripts/gates/check-seo.ts:23` and `scripts/lib/positional-cli-detector.ts:25` import from it.

## Critical files

- `eslint.config/typescript.js:47-379`, `eslint.config/i18n.js:146-389`, `eslint.config/packages.js:15-263`, `eslint.config/tests.js:11-115`, `eslint.config/tooling.js:14-135`, `eslint.config/ignores.js:10-73`: the source of the rule map.
- `biome.json:1-171`: the target config.
- `eslint-rules/require-translation.js:68-203`, `eslint-rules/require-translation-key-arg.js:67-105`, `eslint-rules/i18n/interpolation-match.js:241`, `eslint-rules/translation-helpers.js:1-87`: the four named rules. Scope API is used at `eslint-rules/require-translation.js:83` and `eslint-rules/i18n/interpolation-match.js:241`.
- `package.json:255`, `:321-325`, `:352`, `:365`, `:413-436`, `:474`, `:503`.
- `scripts/ci-runner/manifest.ts:78-158`, `:2062-2076`, `:2443-2455`, `:2587-2610`, `:3376-3389`.
- `.github/workflows/ci-quality.yml:1012-1014`, `:1067-1070`, `:1198`, `:1274-1276`, `:1426-1428`, `:1435-1437`.
- `.ci/scripts/quality/check_lint_scope_coverage.py:66-157`, `.ci/scripts/quality/lint-rule-liveness.mjs:480-716`, `eslint-rules/__tests__/harness.js:40-41`, `scripts/gates/check-lint-rule-units.ts:57-65`.
- `.ci/policy/.deps-upgrade-blocklist:18-42`.
- `scripts/gates/check-control-in-string.ts:40`, `packages/cli/src/__tests__/renet-access-ledger.test.ts:4`.

## Verification

1. **TypeScript 7:**
   - `npx tsc -v` prints `Version 7.0.2`.
   - `npm run typecheck` exits 0; this covers shared, provisioning, cli, account, scripts, test tsconfigs, e2e, www and workers.
   - In account: `npm run typecheck` and `npm run typecheck:web` exit 0.
   - The `Dockerfile:49` `account-builder` stage builds; the TS 7 native package has os/cpu fields but no libc field.
2. **Biome on the linted scope:**
   - `npx biome lint . --error-on-warnings` exits 0, and `npx biome format .` is unchanged.
   - `check:ci-format-scope` passes.
   - The rewritten `check:ci-lint-scope-coverage` reports every tracked js/ts file reached. Its control: a new file under an unlisted root turns it red.
3. **Every replacement gate, each with a planted-defect control that turns it red and then green once reverted:**
   - `ci-source-rules` (proposed gate): the Phase 1 differential shows identical tuples to ESLint. Controls include `t('no.such.key')` in `packages/cli/src` (require-translation), `errorResult('no.such.key')` (require-translation-key-arg), a missing `{{var}}` option (interpolation-match), and an `eslint-disable` token (stale-directive refusal).
   - `check:ci-lint-rule-liveness`: all 30 host rules and all 9 Grit plugins fire.
   - `check:ci-lint-rule-units`: the specs pass on the host tester, including the 5 off rules.
   - `ci-max-lines` (proposed gate): a 513-code-line file turns it red.
   - `check:ci-account-layer-isolation`: `import { db } from '../db'` in `private/account/src/routes/x.ts` turns it red.
   - Spot controls on mapped Biome rules: a `styled-components` import (`noRestrictedImports`), `console.log` in `packages/cli/src` (`noConsole`), `it.skip` in `packages/shared/src/**/__tests__` (`noSkippedTests`), `test.only` in e2e (`noFocusedTests`), and an unawaited promise in the CLI (`noFloatingPromises`).
4. **Dependency and CI hygiene:**
   - `check:version`, `check:deps` (typescript no longer blocked, nothing stale), `check:ci-lockfile` (canonical under npm 11.20.0), `check:ci-peer-deps`, `check:ci-suppression-liveness` (no dead override or blocklist entry), `check:ci-runtime-imports-are-deps`, `lint:unused` (knip), `check:ci-gates-lock`, `check:ci-gate-bind`, `check:ci-parity`, `check:ci-domain-partition`, `check:ci-language-policy`, `check:ci-control-in-string`.
   - The quality-gate battery, including `test_gate_gate_lanes`, `test_gate_suppression_liveness` and `test_gate_policy_liveness_floors`.
5. **Tests:** `npm run check:test-cli`, `npm run check:test-shared`, `npm run check:test-www`, account `npm test`, and account web `npm test` all exit 0. Then run `npm run ci` in full, and `ci-watch` shows green on the PR head.

### Critical Files for Implementation
- /home/developer/console/eslint.config/typescript.js
- /home/developer/console/eslint.config/i18n.js
- /home/developer/console/biome.json
- /home/developer/console/package.json
- /home/developer/console/scripts/ci-runner/manifest.ts
