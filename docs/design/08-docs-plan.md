# 08 — Docs Plan (rewrite for the new architecture)

User decision 2026-07-10: with the redesign implemented in the same program, the public
docs are REWRITTEN for the new architecture (the interim "falsehood patch" of current docs
is skipped as dead work). Docs land in the program's final phase, AFTER code passes the
examples suite, so every claim is backed by something that ran.

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
cluster fork), which is the cleanest fix of all.

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
