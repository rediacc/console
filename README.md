# Rediacc Console

Self-hosted infrastructure platform. Each machine runs Docker-based repositories
with encrypted, isolated environments. This monorepo holds the `rdc` CLI, the
marketing and docs site, and the shared packages they build on.

For what the platform does, see [rediacc.com](https://www.rediacc.com).
For how the codebase is organised and how to work in it, see `CLAUDE.md`.

## Clone it blobless

```bash
git clone --filter=blob:none --recurse-submodules https://github.com/rediacc/console.git
```

Measured 2026-08-23: a full working tree with a **54 MB** `.git`, in **11.4
seconds**. Cloning unfiltered instead transfers gigabytes of historical media
blobs that no build, test, or gate ever opens. This is not a shallow clone and
does not truncate history: git fetches an individual blob on demand if some
command genuinely needs one. CI does the same thing, on every `fetch-depth: 0`
checkout.

Two things will not be there afterwards, both on purpose:

- **The private submodules.** `private/renet`, `private/account` and
  `private/elite` are private repositories. Without access the clone still
  succeeds and those directories are simply empty.
- **The tutorial and solution media.** Videos and narration audio live in
  Cloudflare R2, not git. The site fetches them from `media.rediacc.com` at
  runtime, so a normal `npm run dev` needs nothing extra. Restoring them locally
  is only needed for pipeline or offline ffmpeg work: see
  [`.ci/docs/r2-media-setup.md`](.ci/docs/r2-media-setup.md) section 7.

## Build

This monorepo uses **npm, not pnpm**, and `.npmrc` sets `ignore-scripts=true`
for supply-chain hardening, so the native rebuild is a separate explicit step:

```bash
npm install && npm run install:natives
cd packages/shared && npm run build     # required before www or cli
```

`npm run ci` runs the checks CI runs. See `CLAUDE.md` for the full gate list and
[`docs/agent-reference/ci-gates.md`](docs/agent-reference/ci-gates.md) for what
to do when one fails.

## Contributing

There is one operator and no external contributors; forks are not supported.
See [`.github/CONTRIBUTING.md`](.github/CONTRIBUTING.md) for the branch and PR
conventions used here.
