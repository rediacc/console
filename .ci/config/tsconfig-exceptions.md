# tsconfig strict-flag exceptions

Every tsconfig in this repo with a disabled safety/strict flag must appear in
this document with a substantive BLOCKER reason. The companion validator
`scripts/check-tsconfig-exceptions.ts` enforces:

1. Every real suppression (e.g. `"skipLibCheck": true`) in a committed
   `tsconfig*.json` has a matching row below.
2. Every row below still points at a real suppression (drift detection).
3. Every row's BLOCKER reason passes the shared quality gate
   (`scripts/lib/blocker-validator.ts` — >= 30 chars, no banned phrases).

Format for each row (the validator parses the HTML-comment blocks so markdown
tables stay readable while still giving the validator exact strings to match):

```
<!-- tsconfig-exception:
path: <relative path to tsconfig>
flag: <the disabled flag, e.g. skipLibCheck>
blocker: <reason >= 30 chars>
-->
```

Rows follow. Keep them sorted by path.

<!-- tsconfig-exception:
path: packages/bridge-tests/tsconfig.json
flag: skipLibCheck
blocker: BLOCKER: skipLibCheck is a repo-wide convention across every tsconfig in this monorepo; compiling node_modules .d.ts would add 10+ seconds per tsc pass and surfaces only third-party type errors that are not actionable for us. Our own code still runs under strict: true, so type safety on source is preserved. Shared reason across all 15 tsconfigs (this row documents the contract, not a per-file exception).
-->

<!-- tsconfig-exception:
path: packages/cli/tests/tsconfig.json
flag: skipLibCheck
blocker: BLOCKER: skipLibCheck is a repo-wide convention across every tsconfig in this monorepo; compiling node_modules .d.ts would add 10+ seconds per tsc pass and surfaces only third-party type errors that are not actionable for us. Our own code still runs under strict: true, so type safety on source is preserved.
-->

<!-- tsconfig-exception:
path: packages/cli/tsconfig.json
flag: skipLibCheck
blocker: BLOCKER: skipLibCheck is a repo-wide convention across every tsconfig in this monorepo; compiling node_modules .d.ts would add 10+ seconds per tsc pass and surfaces only third-party type errors that are not actionable for us. Our own code still runs under strict: true, so type safety on source is preserved.
-->

<!-- tsconfig-exception:
path: packages/desktop/tsconfig.json
flag: skipLibCheck
blocker: BLOCKER: skipLibCheck is a repo-wide convention across every tsconfig in this monorepo; compiling node_modules .d.ts would add 10+ seconds per tsc pass and surfaces only third-party type errors that are not actionable for us. Electron's ambient .d.ts ships with known cross-version quirks that aren't ours to fix.
-->

<!-- tsconfig-exception:
path: packages/desktop/tsconfig.node.json
flag: skipLibCheck
blocker: BLOCKER: skipLibCheck is a repo-wide convention across every tsconfig in this monorepo; compiling node_modules .d.ts would add 10+ seconds per tsc pass and surfaces only third-party type errors that are not actionable for us. Our own code still runs under strict: true, so type safety on source is preserved.
-->

<!-- tsconfig-exception:
path: packages/e2e/tsconfig.json
flag: skipLibCheck
blocker: BLOCKER: skipLibCheck is a repo-wide convention across every tsconfig in this monorepo; compiling node_modules .d.ts would add 10+ seconds per tsc pass and surfaces only third-party type errors that are not actionable for us. Playwright's ambient types have historically triggered false positives with generic mixin patterns.
-->

<!-- tsconfig-exception:
path: packages/web/tsconfig.json
flag: skipLibCheck
blocker: BLOCKER: skipLibCheck is a repo-wide convention across every tsconfig in this monorepo; compiling node_modules .d.ts would add 10+ seconds per tsc pass and surfaces only third-party type errors that are not actionable for us. Our own code still runs under strict: true plus noUnusedLocals/noUnusedParameters so source-level safety is preserved.
-->

<!-- tsconfig-exception:
path: packages/web/tsconfig.node.json
flag: skipLibCheck
blocker: BLOCKER: skipLibCheck is a repo-wide convention across every tsconfig in this monorepo; compiling node_modules .d.ts would add 10+ seconds per tsc pass and surfaces only third-party type errors that are not actionable for us. Our own code still runs under strict: true, so type safety on source is preserved.
-->

<!-- tsconfig-exception:
path: private/account/e2e/tsconfig.json
flag: skipLibCheck
blocker: BLOCKER: skipLibCheck is a repo-wide convention across every tsconfig in this monorepo; compiling node_modules .d.ts would add 10+ seconds per tsc pass and surfaces only third-party type errors that are not actionable for us. Our own code still runs under strict: true, so type safety on source is preserved.
-->

<!-- tsconfig-exception:
path: private/account/tsconfig.json
flag: skipLibCheck
blocker: BLOCKER: skipLibCheck is a repo-wide convention across every tsconfig in this monorepo; compiling node_modules .d.ts would add 10+ seconds per tsc pass and surfaces only third-party type errors that are not actionable for us. Hono, Drizzle, and Cloudflare Workers types all ship with ambient declarations that aren't ours to fix.
-->

<!-- tsconfig-exception:
path: private/account/web/tsconfig.json
flag: skipLibCheck
blocker: BLOCKER: skipLibCheck is a repo-wide convention across every tsconfig in this monorepo; compiling node_modules .d.ts would add 10+ seconds per tsc pass and surfaces only third-party type errors that are not actionable for us. Our own code still runs under strict: true, so type safety on source is preserved.
-->

<!-- tsconfig-exception:
path: private/sql/coordinator/tsconfig.json
flag: skipLibCheck
blocker: BLOCKER: skipLibCheck is a repo-wide convention across every tsconfig in this monorepo; compiling node_modules .d.ts would add 10+ seconds per tsc pass and surfaces only third-party type errors that are not actionable for us. Our own code still runs under strict: true, so type safety on source is preserved.
-->

<!-- tsconfig-exception:
path: tsconfig.json
flag: skipLibCheck
blocker: BLOCKER: skipLibCheck is the repo-wide root setting; compiling node_modules .d.ts would add 10+ seconds per tsc pass and surfaces only third-party type errors that are not actionable for us. Per-package tsconfigs inherit. Our own code still runs under strict: true, so type safety on source is preserved.
-->

<!-- tsconfig-exception:
path: workers/account/tsconfig.json
flag: skipLibCheck
blocker: BLOCKER: skipLibCheck is a repo-wide convention across every tsconfig in this monorepo; compiling node_modules .d.ts would add 10+ seconds per tsc pass and surfaces only third-party type errors that are not actionable for us. Cloudflare Workers runtime types ship ambient declarations that aren't ours to fix.
-->

<!-- tsconfig-exception:
path: workers/www/tsconfig.json
flag: skipLibCheck
blocker: BLOCKER: skipLibCheck is a repo-wide convention across every tsconfig in this monorepo; compiling node_modules .d.ts would add 10+ seconds per tsc pass and surfaces only third-party type errors that are not actionable for us. Cloudflare Workers runtime types ship ambient declarations that aren't ours to fix.
-->
