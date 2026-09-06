# 08. Driver contract for the tooling transformation

This file is the authority for the twelve-workstream tooling transformation. It exists
because the twelve workstream plans were drafted independently, and a completeness pass
found twenty places where two of them plan incompatible things in the same file. Those
resolutions are recorded here ONCE, so no sub-driver re-decides them and no two agents
land opposite designs.

Read this before launching any sub-driver. Its three tables are the ones that actually
prevent damage: the W-key map (because four plans schedule against wrong keys), the
single-writer lock table (because the hot files are hot across every track), and the
machine mutex (because a git worktree does not isolate a docker daemon).

Related records: [04-decisions.md](04-decisions.md) carries the operator rulings,
including ruling 7 which re-opens the bash-coverage ruling out loud under A6.
[06-progress.md](06-progress.md) remains the running log.

---

## 1. The W-key map (authoritative)

Four plans schedule against keys they invented. Every `serial_after` string must be
re-mapped to this table before a sub-driver is launched, or two tracks will each believe
the other is unblocking them.

| Key | Workstream |
|---|---|
| W0 | Pre-work, hygiene, known bugs, this contract |
| W1 | Python foundation (bootstrap, package, core modules, language policy) |
| W2 | Gate registry (headers, `gates.lock.json`, isolation, paths, shadow mode) |
| W3 | CI-quick and parallelism (dedupe, packing, proxies, shard matrix) |
| W4 | Policy folder and duplicate collapse |
| W5 | `.claude` hooks to Python |
| W6 | Bootstrap, `run.sh` router, cross-OS |
| W7 | `.ci` port (quality gates, gate tests, wrappers, deploy and release) |
| W8 | Environment manifest and Bitwarden |
| W9 | `scripts/` and `eslint-rules` reorganization |
| W10 | Media pipeline separation (stays bash) |
| W11 | Docs, records and the generator |
| W12 | `agent/` history as attested records |

Known mis-references to correct on sight: W11 called W8 the media pipeline and W10 the
test split; W3 attributed the hook port to W2 and the harness edits to W4; W7 called
bootstrap W5. Hooks are W5, bootstrap is W6, media is W10, env is W8.

---

## 2. Program arbitrations

Each row is a conflict found between two or more drafts, and the resolution that holds.

| Conflict | Resolution |
|---|---|
| Python package path (four proposals) | `.ci/rediacc_ci`, importable as `rediacc_ci`. `test-gate-anti-vacuity.sh` copies only `scripts`, `.ci/scripts` and `.ci/config` into its fixture, so W1's first phase must add `.ci/rediacc_ci` to that copy list in the same change, or every gate importing the package fails inside the vacuity fixture. |
| Python config home (three proposals) | One `pyproject.toml` at the repo root holding the ruff and pytest tables. `ruff.toml` is deleted and the `--config` arguments in `check-python-lint.sh` are removed, because both tools discover a root `pyproject.toml`. `.ci/ruff.toml` is dropped. |
| Test runner and test roots (three proposals) | pytest, provisioned by the uv shim. Tests live beside their package: `.ci/rediacc_ci/tests`, `.ci/tests/gates`, `.claude/rediacc_hooks/tests`. ONE edit adds all three to `check_test_file_orphans` SEARCH_DIRS. |
| `run-all.sh` fate (four futures) | Re-key in place first (W2 reads isolation from the lock, W3 adds its selection seam), then W7 replaces it with `battery.py` at the end. Never concurrent. |
| Registry write model | Hand-appending a manifest entry is legal UNTIL W2 lands the generated region plus `gates.lock.json`. After that, registration is a `---- gate ----` header, and only the root driver runs `gate:bind --write`. |
| `test-hooks.sh` split owner | W5 owns the file. W3's hook-split boxes are delegated to the hooks sub-driver, with one agreed set of wrapper names. |
| `run.ps1` design | W6's WSL launcher. W1's docker-run launcher is dropped. One launcher, one test file, one `ROOT_MANIFESTS` entry. |
| Node floor and `constants.sh` | W0 owns `NODE_VERSION_MIN` in wave 1. W6 must not touch it. |
| The five unpinned go installs | W0 writes the `ARG` lines by hand in wave 1. W6 later generates the region and must ADOPT the existing names, asserting no value change. |
| `toolchain.env` writers | Append-only and sequenced: W0 (Node floor, go pins), then W1 (uv and pytest), then W6 (adoption). |
| `local-common.sh` lifetime | W8's `env_file_load` lands in `rediacc_ci/core/env.py` with a bash shim. W7 deletes the file only after W6's quality lane and W8's retarget. |
| `scripts/dev` ownership | Sequence: W8 deletes its dead script, W0 and W8 make their edits at the current path, THEN W9 moves the directory. |
| Language policy gate | ONE gate covering both `.ci` and `.claude`, one exemption list. W5's second gate is dropped. |
| Bitwarden token schema | W0 owns the `tokens[]` restructure once; W8 consumes it. The existing `warn_days` value is preserved unless the operator changes it. No CI expiry gate is added: an expired token already fails loudly everywhere, and a clock-driven gate that reds on a quiet day is the worse trade. |

---

## 3. Single-writer lock table

These files have exactly ONE writer in flight across the entire program. A sub-driver
hands the root driver a branch; the root driver rebases and merges them one at a time.
A gate file and its registry entry must be in the SAME commit, because the parity gate
fires in both directions and reads the battery from disk, so a half-landed pair is red
in any worktree.

| File | Owner and rule |
|---|---|
| `package.json` | Root driver merge queue. Measured: 132 gate-path references today. |
| `scripts/ci-runner/manifest.ts` | Root driver merge queue. Measured: 139 gate-path references, 391 `id:` literals, 388 `gate: true`. |
| `.github/workflows/ci-quality.yml` | Root driver only. Never hand-merged. Only the root driver runs `gate:bind --write`, once per merged wave, and pastes the reported `dropped` list into the wave record. A `--write` on 2026-09-05 silently deleted four hand-added steps. |
| `scripts/gate-bind.ts`, `scripts/lib/gate-header.ts` | W2 is sole owner. W1's pytest ACQUIRE row and W3's shard emitter arrive as one-line contributions, never as concurrent edits. |
| `.ci/scripts/test/run-all.sh` | W2, then W3, then W7 deletes it. Serial, in that order. |
| `.claude/hooks/test-hooks.sh` | W5 is sole owner. W0's jq-absent cases land first, in wave 1, before W5 opens the file. |
| `.claude/settings.json` | W0 (require-jq position) in wave 1, then W5 for the rest. |
| `.ci/scripts/quality/check-hook-integrity.sh` | W11 widens the seam as a proven no-op FIRST, then W5 re-keys. |
| `docs/agent-reference/TRAPS.md` | W11 is sole owner. Every other track hands W11 the text. Measured: 75 headings, exactly on the floor of 75, so a heading may never be deleted. |
| `CLAUDE.md`, `ci-gates.md`, `suppressions.md` | W11 is sole owner. Session Defaults in CLAUDE.md stays byte-identical throughout. |
| `.ci/scripts/ci/scope-map.cjs` | Rule ORDER is semantics (first match wins). One writer at a time; every mover states where its rule sits. |
| `.ci/config/bws-token-expiry.json` | W0 restructures, W8 consumes. |
| `run.sh` | W10 removes the media lines FIRST, then W6 moves the remainder to the legacy file. Never concurrent: W6's move is the largest revert boundary in the program. |

---

## 4. Machine mutex

A git worktree isolates files. It does not isolate any of these, so at most ONE box
touching each may be in flight across all tracks:

- the docker daemon, and the traefik router namespace (a detached worktree yields the
  literal slug `HEAD`, so every detached worktree collides on one router name)
- `~/.rediacc` account state and `private/account/account.db`
- the dev gateway port (4800)
- the Bitwarden store, during any seeding or retarget box
- **the checkout itself.** Other Claude sessions work in this same working tree and commit
  to `main` from it. Measured on 2026-09-06: three release-signing commits and a rebase
  landed between a baseline measurement and the branch taken from it, moving the branch
  point from `7343ae9dc` to `c6d3af163`. Before starting a wave, record `git rev-parse HEAD`
  and re-measure; before merging one, check the reflog for commits nobody in this program
  made. A sub-driver must never assume the tree it measured is the tree it is editing.

---

## 5. Timing baseline

`.ci/cache/` is gitignored and per-worktree, so a fresh worktree starts blind and the
scheduler loses longest-first ordering. A 4.5 second gate has been measured at 21 seconds
under two concurrent writers. Therefore:

**No timing number from a feature worktree is admissible.** Every box's acceptance is
structural: set equality, PASS counts, planted-defect controls. Timings come from ONE
quiesced reference worktree, and each phase ends with a single serial measure-and-retier
box that owns every `slow:` edit.

Baseline recorded at branch point `c6d3af163`, 2026-09-06:

| Measurement | Value |
|---|---|
| `ci:quick` wall | 58,029 ms |
| `ci:quick` selection | what `npm run ci -- --quick --list` prints; do not quote a number |
| Local full-run floor | 785 s, set by `gate-test:claude-hooks` |
| Manifest | 390 `gate: true`, 393 `id:` literals, and rising |
| Gate test files | 131 |
| Bash quality gates | 74 `check-*.sh` plus 5 wrappers |
| Files with a `---- gate ----` header | 19 tracked, 14 parsing |

Four drafts asserted different figures for these. Cite the COMMAND, not the number: the
manifest gained two gates during the planning session itself, between the baseline
measurement and the first implementation branch, so any box that pins a count is wrong
before it lands.

---

## 5b. Verifying work that is not committed yet

This program keeps work uncommitted until the operator asks for a commit, and that rule
collides with a whole class of gates. Many of them enumerate through `git ls-files`, so
they read the INDEX, not the working tree. A deletion that is real on disk but absent
from the index makes them either crash with ENOENT or, worse, pass while still counting
the file they were meant to notice.

Measured on 2026-09-06: `check-shell-declared-commands.ts` crashed on six unstaged
deletions and only reported the truth once the deletions were visible to a git index.

The technique that works, and does not touch the real index:

1. Copy the index to the scratchpad and point `GIT_INDEX_FILE` at the copy.
2. `git update-index --force-remove` each deleted path in the copy.
3. Run the affected gates with that variable set.
4. Delete the copy. The repository index and refs are never written.

Two cautions learned the same day. Gates that build their own fixture trees must run
WITHOUT that variable, or it leaks into the fixture and they fail for the wrong reason
(`test-scope-gate-outputs.sh` is one). And a gate that reads the working tree rather than
the index needs none of this, so check which kind you have before reaching for the
workaround.

Corollary for reviewers: a green gate run over unstaged deletions is not evidence until
you know which side of that line the gate sits on.

## 6. Floor policy

The accepted recommendation "retire file-count floors" is SUPERSEDED, out loud, here.
Three workstreams raise floors and none retires one, because a floor is the only thing
standing between a collapsed glob and a green report.

The rule that replaces it: **a floor must be set-based or corpus-derived, never a
hand-typed count.** A floor that names a number a human typed is re-keyed to a
`git ls-files` derived corpus, a recorded row SET, or a ratio. This keeps the
anti-vacuity property while removing the class of failure where a correct rename turns
a gate red for the wrong reason.

---

## 7. What "modular and dynamic" means

The requirement is otherwise uncheckable, so it gets an acceptance test:

**Adding a gate, an allowlist entry, or a hook guard requires no edit to any workflow
file, any runner file, or any dispatcher file.** The gate declares itself in its own
header; the allowlist declares itself by existing in `.ci/policy/` under a validated
name; the guard declares itself as a module in the hook registry. Anything that still
requires a second edit somewhere central is not yet modular, whatever else it is.

---

## 8. Wave shape

Wave 1, in parallel worktrees: W0 in full, W6's two prerequisite defect fixes (the
missing `py` alternative in the dead-bash textual regex, and the receipt field that
currently lets a `--changed` run authorise a push), W11's generator and seam widening,
W4's decisions plus W8's first passthrough box, W10's preflight.

Wave 2: W1's bootstrap and skeleton, W2's binder and loader, W9's prep, W5's skeleton
through pre-keying, W10's module extraction.

Waves 3 to 5, independent of each other once the infra-only checkpoint holds: the hooks
cutover, the quality cutover, the Bitwarden cutover, and the registry then `.ci` port.

Final wave: the language gate flip, which needs all four cutovers plus the media handoff,
and the records close-out.

Sustained ceiling is 10 to 12 concurrent worktrees, 14 at the fan-out bursts, each with
`CI_JOBS=2` and `CI_PROFILE=off`. Above 14 the registry merge queue, not the CPU, is the
bottleneck, and the duration cache the tier oracle judges stops being meaningful.
