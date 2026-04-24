# biome.json suppression reasons

Every `off` / `enabled: false` policy in `biome.json` must appear here with a
substantive BLOCKER reason (>= 30 chars, no banned phrases). The companion
validator `scripts/check-biome-reasons.ts` enforces presence + quality +
drift (rows without a matching suppression fail).

Biome 2.4.13+ rejects unknown top-level keys in `biome.json` (unlike
`package.json`'s `_overridesReasons`), so we keep rationale in this sibling
doc. Format: HTML-comment blocks, same pattern as
`.ci/config/tsconfig-exceptions.md`.

Schema for each row:

```
<!-- biome-suppression:
key: <canonical suppression key, e.g. linter.enabled=false>
blocker: <reason >= 30 chars>
-->
```

Rows follow. Keep them sorted by key.

<!-- biome-suppression:
key: linter.enabled=false
blocker: BLOCKER: ESLint (eslint.config.js, 20+ custom rules) is the canonical lint engine for packages/ and scripts/. Biome runs format-only on those paths. Re-enabling would duplicate diagnostics and conflict with our custom rules like no-hardcoded-text, require-translation, no-raw-api-calls. The per-override below scopes biome's linter to private/account/ where ESLint does not run.
-->

<!-- biome-suppression:
key: overrides[packages/cli/tests/**/*.ts].assist.source.organizeImports=off
blocker: BLOCKER: CLI integration tests hand-group imports by origin (type-only, fixtures, subject-under-test) for readability in 200+ line files; organizeImports alphabetises them and destroys that layout on every save.
-->

<!-- biome-suppression:
key: overrides[packages/e2e/**/*.ts].assist.source.organizeImports=off
blocker: BLOCKER: Playwright e2e tests import page objects grouped by feature (auth POMs, repo POMs, etc.) to keep spec files readable; organizeImports reshuffles those groups into a flat alphabetical list that obscures the test's module-level dependencies.
-->

<!-- biome-suppression:
key: overrides[private/account/web/src/hooks/**/*.ts].linter.rules.correctness.useExhaustiveDependencies=off
blocker: BLOCKER: TanStack Query hooks and useEffectEvent patterns in this directory generate high-cardinality false positives that React 19 idioms make intentional. Keeping the rule on would block every hook edit with manual override comments.
-->
