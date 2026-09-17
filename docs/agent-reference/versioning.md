# Versioning

Source of truth: **git tags** (e.g. `v0.8.3`). No version bump commits — every `package.json` carries the `0.0.0-dev` placeholder permanently and none is published to npm; the real version is injected at build time only.

## Resolving the version

`.ci/scripts/version/resolve-version.sh` (Python port: `.ci/rediacc_ci/...`) reads the latest `v*` tag via `git tag -l --sort=-v:refname`, not `git describe` — `describe` requires the tag to be reachable from `HEAD`, which fails in a shallow CI clone.

```
resolve-version.sh --current              # 0.8.2
resolve-version.sh --bump-type patch      # 0.8.3
resolve-version.sh --bump-type minor      # 0.9.0
resolve-version.sh --bump-type major      # 1.0.0
```

## Injection per component, verified against the real build

| Component | Injection method | Verified at |
|-----------|-------------------|-------------|
| CLI binary | `CLI_VERSION` env → esbuild `--define:__CLI_VERSION__` | `packages/cli/bundle.mjs:94` |
| CLI Docker | Same as CLI binary (bundle built with the env set) | same |
| www footer | `APP_VERSION` env → `__APP_VERSION__`, falls back to `0.0.0-dev` | `packages/www/astro.config.mjs:5-8,184` |
| renet (Go) | `-ldflags="-s -w -X main.Version=$VERSION ..."` | `.ci/scripts/build/build-renet.sh:215,224` (Python port: `.ci/rediacc_ci/build/build_renet.py:318-327`) |

renet's ldflags also bakes in the server's public key (`$KEY_LDFLAGS`) in the same `-ldflags` word — Go 1.18+ records `-ldflags` in `.go.buildinfo`, which is why the two values travel together rather than as separate flags.

## `bump.sh`

`.ci/scripts/version/bump.sh --version <v>` updates version strings across package files independently (bash + `jq`, no Python). Two real call sites today, both gated to `github.event_name == 'push' && github.ref == 'refs/heads/main'` — never on a PR:

- `.github/workflows/ci-build-docker.yml` (before `build-cli.sh`, for the CLI's npm pack
tarball name)
- `.github/workflows/ci-quality.yml` (a separate job in the same release path)

## Why this is a separate file

`CLAUDE.md`'s rule is to cut what already has a home (`agent/PLAN-tooling-transformation.md`, box W11 P5b). `__CLI_VERSION__`'s injection table had no home before this file — the only prior mentions of `resolve-version.sh` in `docs/` are scattered, incidental references inside `docs/ci-overhaul/06-progress.md`'s running investigation log, not a stable description of how versioning
works. Verified against the four real injection sites directly, not copied from `CLAUDE.md`'s prior wording.
