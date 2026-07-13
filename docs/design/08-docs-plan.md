# 08 — Docs Plan (rewrite for the new architecture)

**Status: forward-looking (P7).** The plan below is unchanged, but the ground under it has
moved: the claims the current docs make falsely are now TRUE and PROVEN, so P7 is a rewrite
against measured evidence rather than against a design.

User decision 2026-07-10: with the redesign implemented in the same program, the public
docs are REWRITTEN for the new architecture (the interim "falsehood patch" of current docs
is skipped as dead work). Docs land in the program's final phase, AFTER code passes the
examples suite, so every claim is backed by something that ran.

## 0. What P7 must use for numbers

**Use the measured figures from the README's "What is proven live" table, and nothing else.**
Do not recycle the pre-program numbers in 01 §6 (namespace fork 1-5s, 2-node cluster fork
~46s, migrate ~16s cutover): those measured the OLD architecture and are not comparable. Do
not estimate. The hard rule from 05 §5 stands: **all numbers measured live, no fabricated
benchmarks.**

The honest framings available to P7, each with a transcript behind it: whole-cluster fork at
roughly 85 seconds (single-node dest) or 125 to 161 seconds (multinode, including a fresh
agent rejoin); in-Ceph migrate cutover at 21.6 seconds by the orchestrator's own clock, or 53
to 56 seconds when the node-side teardown is counted inside the window (quote the larger one
and say why); group snapshot in 1.2 to 8.7 seconds; datastore fork in 0.3 to 10.5 seconds; and
the parent serving 4941 of 4943 liveness samples across an 82-minute window during which it
was forked repeatedly.

The storage half of a fork is constant-time in the size of the data. The PKI re-mint (roughly
120 seconds) dominates the wall clock, and that is worth saying plainly rather than hiding: a
fork is slow because it is being made **safe**, not because it is copying anything.

## 1. Current falsehoods (why the rewrite is also an honesty fix)

The pages being rewritten currently overstate the implementation. For the record (exact
spots verified 2026-07-10):
- `packages/www/src/content/docs/en/kubernetes.md` lines 21, 23, 30 (table), 124, 145:
  whole-cluster fork "copy-on-write of the cluster images plus every repo PV image" — the
  code clones only the cluster images; PVs are NOT carried (see 01 §5.1).
- `packages/www/src/content/blog/en/fork-a-running-kubernetes-cluster.md` lines 16
  ("data included"), 26 ("the node images plus every persistent volume"), restated at
  3, 34, 44-46, 59. The blog has NO locale twins (whitelisted as pending translation in
  validate-translation-freshness.js).
- `private/renet/docs/datastore/README.md` line 116: stale `--source/--target` flags
  (real: `--name/--tag`). Check lines 181-193 (backup flags) against the current CLI while
  in there.
Under the new architecture these claims become TRUE by construction (data included in
cluster fork), which is the cleanest fix of all. **As of P3 they are also PROVEN**: e2e suite
17 forks a running multinode cluster and the fork's app data marker is present in the clone,
because the data never left the datastore that was snapshotted. The page that overstated the
old implementation can now understate the new one.

Two things the rewrite must ADD, because they are new true claims rather than corrected false
ones:
- **A fork is not a parent-admin credential.** Every fork re-mints the cluster PKI, so the
  parent's admin certificate is rejected by the fork (401) while remaining valid on the parent
  (200), and injected plus third-party Secrets are scrubbed from the fork. This is the F1 fix
  and it is the single most important security property of the feature.
- **The parent never stops.** The group snapshot is hot. Measured: zero gaps at the API across
  hundreds of samples, and 4941 of 4943 across an 82-minute window.

## 2. Target docs structure

```
docs (www content)
  getting-started/      ← Track 0 examples embedded
  guides/docker/        ← Track 1 (fork, branching, secrets, backup, migrate, replicate)
  guides/datastores/    ← Track 2 + mobility/failover/tiering (the new middle layer)
  guides/kubernetes/    ← Track 3 (rewrites kubernetes.md into example-backed pages)
  guides/operations/    ← Track 4 (+ asciinema for interactive flows)
  concepts/storage-and-forking  ← the comparison material from this design suite (01-03),
                                   written ONCE, post-implementation
  reference/            ← generated CLI docs (never hand-edit; regenerate after reshape)
```

The contract: **every code block a user sees passed CI (or the local harness) recently** —
guide pages EMBED the example files rather than paraphrasing them.

## 3. The embed plugin (must be built — verified none exists)

All four existing remark plugins (`remark-video-embed`, `remark-tutorial-embed`,
`remark-docs-cli-links`, `remark-resolve-translations`) embed videos/casts/links, NOT code
files. New plugin, following the established pattern:
- Trigger: image syntax + extension test (e.g. `![embed](/../../examples/10-real-app/run.sh)`)
  or a fenced-code convention; resolve relative to repo root; `fs.readFileSync`;
- Emit a mdast `code` node (keeps syntax highlighting);
- Register in `packages/www/astro.config.mjs` remarkPlugins (ORDER MATTERS: before
  `remarkDocsCliLinks` so embedded `rdc` commands get CLI reference links).
- Caveat: search-index and translation-freshness hash the RAW .md body, not the resolved
  embed — an embedded file changing does not stale the page. Acceptable: the examples
  themselves are CI-validated; note it in the plugin header.

## 4. i18n mechanics (verified; two independent systems — do not conflate)

- **JSON manifests** (`scripts/generate-translation-hashes.ts`, `.translation-hashes.json`):
  covers en.json-style trees (www translations, CLI locales, account). The CLI reshape's
  new/renamed command strings flow HERE → re-naturalize via `private/growth/i18n_pipeline`
  (ledger-driven delta; Sonnet).
  **P7 owns a deferred debt here**: 12 locales x 58 untranslated CLI-surface strings, carried
  since P1 by standing ruling because P4 reshapes exactly that surface and naturalizing before
  the reshape would be throwaway work. P4 must NOT try to clear it. P7 must. Re-check the
  count after P4 lands, since the reshape will change which keys exist.
- **Docs/blog frontmatter `sourceHash`+`sourceCommit`**
  (`packages/www/scripts/validate-translation-freshness.js`): en docs change → all 12 locale
  twins must be updated + `sourceHash` restamped (16-hex sha256 of
  title/description/category/body). NEW en page → all 12 twins must exist OR the en path
  goes on the pending/EXCLUDED list (the sanctioned deferral; the fork blog already uses it).
  `check-i18n-naturalization` is JSON-only (does not scan docs .md).
- **Search index**: ANY docs/blog add/edit → regenerate
  `packages/www/public/search-index*.json` (`cd packages/www && node
  scripts/generate-search-index.js`) or `check:ci-search-index` reds.
- Other gates: `check-locale-tutorial-assets` only fires for pages embedding `.cast`;
  `check-solution-videos` is solutions-pages-only; docs frontmatter schema requires
  title/description/category (blog category is a strict enum).

## 5. Translation strategy (user decision: full re-naturalization)

- kubernetes.md and every rewritten page: 12 locale twins fully re-naturalized (Sonnet
  agents, per-language batches), sourceHash+sourceCommit restamped.
- Brand-new pages: either translate in the same wave (preferred for guides that embed
  code — embedded code is NOT translated, making these the cheapest pages) or park on the
  pending-exclusion list with user approval.
- Batch per track, never page-by-page drip (each en wave = one hash regen + one
  delta-naturalization pass per language).
- English readability rules apply (grade 5-7 marketing / technical docs register; see
  `docs/i18n/CONVENTIONS.md`; no em dashes).

## 6. Sequencing

1. During implementation phases: docs untouched (no dead work).
2. After examples pass (P5 gate): rewrite en pages track-by-track, embedding example files.
3. Regenerate search index + cli reference docs.
4. Sonnet re-naturalization batches per language.
5. Final: `check:i18n` + `check:ci-search-index` + `check:cli-examples` green locally.
