# 08. Driver contract for the tooling transformation

This file is the authority for the twelve-workstream tooling transformation. It exists because the twelve workstream plans were drafted independently, and a completeness pass found twenty places where two of them plan incompatible things in the same file. Those resolutions are recorded here ONCE, so no sub-driver re-decides them and no two agents land opposite designs.

Read this before launching any sub-driver. Its three tables are the ones that actually prevent damage: the W-key map (because four plans schedule against wrong keys), the single-writer lock table (because the hot files are hot across every track), and the machine mutex (because a git worktree does not isolate a docker daemon).

Related records: [04-decisions.md](04-decisions.md) carries the operator rulings, including ruling 7 which re-opens the bash-coverage ruling out loud under A6. [06-progress.md](06-progress.md) remains the running log.

---

## 1. The W-key map (authoritative)

Four plans schedule against keys they invented. Every `serial_after` string must be re-mapped to this table before a sub-driver is launched, or two tracks will each believe the other is unblocking them.

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

Known mis-references to correct on sight: W11 called W8 the media pipeline and W10 the test split; W3 attributed the hook port to W2 and the harness edits to W4; W7 called bootstrap W5. Hooks are W5, bootstrap is W6, media is W10, env is W8.

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

These files have exactly ONE writer in flight across the entire program. A sub-driver hands the root driver a branch; the root driver rebases and merges them one at a time. A gate file and its registry entry must be in the SAME commit, because the parity gate fires in both directions and reads the battery from disk, so a half-landed pair is red in any worktree.

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

A git worktree isolates files. It does not isolate any of these, so at most ONE box touching each may be in flight across all tracks:

- the docker daemon, and the traefik router namespace (a detached worktree yields the
literal slug `HEAD`, so every detached worktree collides on one router name)
- `~/.rediacc` account state and `private/account/account.db`
- the dev gateway port (4800)
- the Bitwarden store, during any seeding or retarget box
- **the checkout itself.** Other Claude sessions work in this same working tree and commit
to `main` from it. Measured on 2026-09-06: three release-signing commits and a rebase landed between a baseline measurement and the branch taken from it, moving the branch point from `7343ae9dc` to `c6d3af163`. Before starting a wave, record `git rev-parse HEAD` and re-measure; before merging one, check the reflog for commits nobody in this program made. A sub-driver must never
assume the tree it measured is the tree it is editing.

---

## 5. Timing baseline

`.ci/cache/` is gitignored and per-worktree, so a fresh worktree starts blind and the scheduler loses longest-first ordering. A 4.5 second gate has been measured at 21 seconds under two concurrent writers. Therefore:

**No timing number from a feature worktree is admissible.** Every box's acceptance is structural: set equality, PASS counts, planted-defect controls. Timings come from ONE quiesced reference worktree, and each phase ends with a single serial measure-and-retier box that owns every `slow:` edit.

Baseline recorded at branch point `c6d3af163`, 2026-09-06:

| Measurement | Value |
|---|---|
| `ci:quick` wall | 58,029 ms |
| `ci:quick` selection | what `npm run ci -- --quick --list` prints; do not quote a number |
| Local full-run floor | 785 s, set by `gate-test:claude-hooks` |
| Manifest | 406 `gate: true`, 409 `id:` literals as of 2026-09-06, and RISING FAST. It read 390/393 when this table was written and 409 a few hours later, with peers adding entries mid-session. Run `npx tsx scripts/gen/gen-docs.ts --list` rather than quoting this row. |
| Gate test files | 131 |
| Bash quality gates | 74 `check-*.sh` plus 5 wrappers |
| Files with a `---- gate ----` header | 19 tracked, 14 parsing |

Four drafts asserted different figures for these. Cite the COMMAND, not the number: the manifest gained two gates during the planning session itself, between the baseline measurement and the first implementation branch, so any box that pins a count is wrong before it lands.

---

## 5b. Verifying work that is not committed yet

This program keeps work uncommitted until the operator asks for a commit, and that rule collides with a whole class of gates. Many of them enumerate through `git ls-files`, so they read the INDEX, not the working tree. A deletion that is real on disk but absent from the index makes them either crash with ENOENT or, worse, pass while still counting the file they were meant to
notice.

Measured on 2026-09-06: `check-shell-declared-commands.ts` crashed on six unstaged deletions and only reported the truth once the deletions were visible to a git index.

The technique that works, and does not touch the real index:

1. Copy the index to the scratchpad and point `GIT_INDEX_FILE` at the copy.
2. `git update-index --force-remove` each deleted path in the copy.
3. Run the affected gates with that variable set.
4. Delete the copy. The repository index and refs are never written.

A THIRD CAUTION, and it cost a full false alarm on 2026-09-06. `cp .git/index` is not atomic against a concurrent writer. A copy taken while another session was writing the index came out with 12 entries instead of 4,720. Running `ci:quick` under that `GIT_INDEX_FILE` turned 45 gates red, with `check:ci-tracked-credentials` reporting `git ls-files returned 2 path(s), floor is 500`,
and a reviewer could reasonably have read that as the change breaking the tree. VALIDATE THE COPY BEFORE USING IT: compare `git ls-files | wc -l` under the copy against the same count under the real index, and refuse the copy if they differ by more than the paths you deliberately added. A truncated index does not announce itself; it just makes every enumerating gate look
catastrophically red at once, which is the shape of a tree-wide regression rather than of a broken instrument.

Two cautions learned the same day. Gates that build their own fixture trees must run WITHOUT that variable, or it leaks into the fixture and they fail for the wrong reason (`test-scope-gate-outputs.sh` is one). And a gate that reads the working tree rather than the index needs none of this, so check which kind you have before reaching for the workaround.

Corollary for reviewers: a green gate run over unstaged deletions is not evidence until you know which side of that line the gate sits on.

## 5c. Comment archaeology is a port acceptance criterion

The comments in this tree are not decoration and they are not redundant with the code. `.claude`'s guards are 52 percent comment bytes, `command-scan.sh` records six separate rounds of bypass findings, and several gates carry the exact run id and date of the incident that produced them. A port that keeps the behaviour and summarises the prose has destroyed the only copy of why the
behaviour is that shape. The next session then "simplifies" the line the comment was guarding, which is the failure TRAPS.md exists for.

Three workstreams already carry a preservation assertion: the registry keeps a `why:` field per gate, the hooks port pins a comment-byte ratio against a committed baseline, and the media move asserts moved bodies byte-for-byte against their origin. The `.ci` port carried none, and it is the LARGEST body in the program: 74 quality gates plus 131 gate tests. That asymmetry was found
by the completeness critic during planning, and it is closed here rather than left to each agent's judgement.

THE RULE. Every ported file records, in the differential artifact its twin already produces, the comment-byte count of the bash original and of the Python port. A port whose comment bytes fall below 90 percent of the original's is refused. Docstrings count as comments; a module docstring is the natural home for a file-header block.

**"REFUSED" NOW MEANS A GATE, AND UNTIL 2026-09-06 IT DID NOT.** This paragraph was written as though the floor were enforced, and the box tracking it was marked closed on that reading. It was not: `shadow-gate.ts` computed the ratio, stored it on every ledger row, and PRINTED `below the 0.90 floor` on the record path, but `assertEquivalent` -- the only function that rules -- never
read `row.comments`, so `--assert` returned 0 with every row under the floor. The word "refused" described a human noticing a number, which is exactly the kind of criterion this contract exists to stop relying on. An adversarial survey found it by asking what would happen if nobody looked.

It is now enforced in code, keyed on the exported `COMMENT_RATIO_FLOOR` so the number the record path prints and the number the assert rules on cannot drift apart. Only rows against COUNTED trees are judged, because a row on a disqualified tree is already refused and failing it twice makes the first message harder to act on; rows carrying no `comments` field are untouched, so
ledgers written before this stay readable.

Worth stating plainly because it is the reason this went unnoticed for so long: the floor was never masking a live violation. The worst ratio across all 100 recorded rows is 2.95, comfortably clear of 0.90. A criterion that nothing checks looks identical to a criterion everything passes, right up until the first port that would have failed it.

WHY A RATIO AND NOT A DIFF. The prose must be allowed to change: `set -euo pipefail` needs explaining in bash and says nothing in Python, and a comment about an argument-splitting bug is meaningless once the arguments are a list. Demanding identical text would force agents to carry dead prose, which teaches the next reader a wrong model just as surely as deleting it. The ratio
permits rewriting and refuses wholesale loss, which is the actual failure mode.

WHAT THE RATIO CANNOT SEE, stated so a green is not read as more than it is: an agent can satisfy it by padding with generic prose while dropping the one paragraph that names a dated incident. So the artifact also lists every line of the original matching a date, a run id, a commit sha, or an issue number, and the reviewer confirms each survives somewhere. That list is short,
mechanical to produce, and is the part worth a human's eye.

## 5d. Cross-wave obligations

Four things that belong to no single workstream and are therefore the ones most likely to be lost between them. Each was found by the completeness pass and is recorded here with the measurement that makes it actionable, so the wave that owns it does not have to rediscover it.

### pytest belongs in the one install table

W6 builds `setup/tools.py` and declares it the ONE install table. Its enumeration as drafted covers cc, make, jq, python3, git, curl, zstd, tmux, xz, node, go, gh, docker, ruff, shfmt, shellcheck, actionlint, uv, gitleaks, bws and PyYAML, and carries no pytest row. But W1, W5 and W7 each make a Python test runner the PRIMARY local proof of their port. A table that installs
everything except the thing the ports are judged by fails the operator requirement it exists to satisfy. W1 phase 1 already pins `PYTEST_VERSION` in `.devcontainer/toolchain.env` and provisions it through `.ci/bootstrap.sh`, so W6 adopts that pin rather than inventing one.

### W9's layout gate must admit what W7 relocates

These two collide by construction and the collision is invisible until both land. Measured 2026-09-06:

- W7 phase 1 relocates **23 JS and TS files** out of `.ci` so that tree becomes single
language. Their natural home is `scripts/`, which is exactly where W9 is installing a TypeScript-only set-equality gate. Nine are `.cjs` under `.ci/scripts/ci`, seven are the `sea-inject` `.mjs` family, and the rest are docs and quality helpers plus one `.ts`.
- `scripts/` today already holds **55 tracked files that are not TypeScript**: 25 JSON, 19
shell scripts, 7 `.txt` files that are 2.16 MB of vendored EU directive text and are content rather than tooling, 2 Python and 2 Markdown. The figure here read **28** until 2026-09-06 and was wrong in the direction that matters: it counted only the shell, Python and text families and silently omitted the 25 JSON and 2 Markdown files, which the partition has to classify exactly like
the rest. Re-derive rather than trust: `git ls-files scripts | grep -vE '\.ts$' | sed 's/.*\.//' | sort | uniq -c`.

So W9 cannot simply assert TypeScript-only, and W7 cannot simply move JS into `scripts/`. The ordering that works: W9 publishes `scripts/data/domains.json` FIRST (the path here said `scripts/domains.json`, which the contract's own `.json` predicate would have moved), with a declared home for each relocated family and the content files moved out to `data/`; W7 then relocates into
those declared homes; and W9's gate flips strict only after both. Whichever lands second extends the partition in the SAME change, never afterwards.

### Cross-repo submodule pull requests need one owner and an order

Three workstreams depend on changes in repositories this one cannot commit to, and all three hand the work off rather than doing it, which is how it reaches nobody. The repository has four submodules: `private/renet`, `private/account`, `private/elite`, `private/homebrew-tap`. The outstanding set is W8's `private/growth` publish retarget without which the `.env` truncation breaks a
live pipeline, W9's three stale path strings in `private/account`, and a `private/renet` pointer bump that W9, W11 and W3 each separately require. One owner takes all of them, submodule PRs merge before the console pointer bump, and the console change that consumes them rides the same wave.

### A gate's ENTRY POINT lives where the binder can see it

`scripts/gate-bind.ts` enumerates its subjects with `git ls-files '.ci/scripts' 'scripts'` and its `inScope` test requires a path under one of those two prefixes. A gate whose file sits anywhere else can carry a perfectly well-formed `---- gate ----` header and the binder will neither register it nor complain that it is unregistered. It is invisible, which is worse than
unregistered, because nothing reports the absence.

That matters the moment the Python package exists: a gate placed at `.ci/rediacc_ci/check_pytest.py` cannot declare itself. So the rule is that a gate's ENTRY POINT lives in `.ci/scripts/quality/` (or `scripts/` for the TypeScript ones) even when all of its logic lives in the package and the entry point is three lines of import and dispatch. That is also where the 40 existing
`check_*.py` gates already are, so it is the convention rather than a new rule.

AMENDED 2026-09-06, same day, stated out loud rather than quietly reversed. W1 phase 2 landed the package's own test-runner gate and made the better argument: a gate that exists to run the package's suite belongs WITH the package, and forcing a shim into `.ci/scripts/quality` only to satisfy an enumeration is the tail wagging the dog. So the binder was widened to scan
`.ci/rediacc_ci` instead. The rule that survives is the one underneath: a gate must live where the binder can SEE it, and when that is false the fix is to widen the scan or move the file, never to leave a header that silently does nothing.

Second half of the same trap, measured 2026-09-06: a gate file that is NEW and not yet in a git index is invisible to the binder for the same reason, since `ls-files` reads the index. Two headers added this session appeared to do nothing until the files were made visible through the throwaway-index technique in section 5b. Before concluding a header does not work, check whether git
can see the file at all.

### The .json inventory has a shape, so give it a predicate

Requirement 15 asks for the `.json` files to be organised, which is unfalsifiable as written. Measured today: **9 at the repository root** (`package.json`, `package-lock.json`, `tsconfig.json`, `biome.json`, `knip.jsonc`, `regions.json`, `css-custom-data.json` and the two `.syncpackrc` files), **15 under `.ci/config`**, and **20 under `scripts/data`**.

The predicate that makes it checkable: a `.json` file stays at the root only when a tool discovers it there and offers no configurable path. That keeps `package.json`, `package-lock.json`, `tsconfig.json` and `biome.json`, and it is also why `css-custom-data.json` stays, since `.vscode/settings.json` names it. Everything else is policy (to `.ci/policy`), generated baseline (to a
baselines directory), or content. The gate asserts BOTH directions: nothing outside the discovered set at the root, and every policy file present in the policy directory, so a move that forgets a reader is red rather than quiet.

## 5e. A writer agent hands over its registration as a PATCH FRAGMENT

Added 2026-09-06, because two rules in this contract contradicted each other and the contradiction had already removed roughly six workstream phases from the parallel plan before anyone noticed.

Invariant 1 says an emitter and its parity gate land in the SAME change. The single-writer table above says `package.json`, `scripts/ci-runner/manifest.ts` and `.github/workflows/**` have exactly one writer, the driver. Read literally and together, NO box that registers a gate can be executed by an agent at all: the agent may write the gate but not the line that registers it, and
the driver may write the line but is not the one writing the gate. A survey found W3 P2, W4 P4, W5 P5, W10 P5, W1 P6, W12 P3.1b and half of both W2.3 and W2.5 stranded on exactly that reading.

THE RESOLUTION, which keeps both rules rather than weakening either. The agent writes the gate, its test, and its EXACT literal registration lines, quoted in its final report. The driver pastes those lines and commits the whole thing together. Invariant 1 holds, because gate and registration land in one commit; the single-writer rule holds, because only the driver ever writes the
registry files.

Proven in practice on 2026-09-06: ten concurrent writers handed over registrations this way and the registry files never had two writers. It costs the driver one paste per agent and it is the difference between a wave of eight and a wave of two.

A REGISTRATION FRAGMENT IS NOT A SUGGESTION. It is literal text: the npm key with its exact body, the manifest entry with its `id`, `run`, `gate`, `leaves` and `ci` block, and the workflow step with its guard. An agent that reports "register this gate in the usual way" has handed over nothing, and the driver then has to derive what the agent already knew.

## 6. Floor policy

The accepted recommendation "retire file-count floors" is SUPERSEDED, out loud, here. Three workstreams raise floors and none retires one, because a floor is the only thing standing between a collapsed glob and a green report.

The rule that replaces it: **a floor must be set-based or corpus-derived, never a hand-typed count.** A floor that names a number a human typed is re-keyed to a `git ls-files` derived corpus, a recorded row SET, or a ratio. This keeps the anti-vacuity property while removing the class of failure where a correct rename turns a gate red for the wrong reason.

---

## 7. What "modular and dynamic" means

The requirement is otherwise uncheckable, so it gets an acceptance test:

**Adding a gate, an allowlist entry, or a hook guard requires no edit to any workflow file, any runner file, or any dispatcher file.** The gate declares itself in its own header; the allowlist declares itself by existing in `.ci/policy/` under a validated name; the guard declares itself as a module in the hook registry. Anything that still requires a second edit somewhere central
is not yet modular, whatever else it is.

---

## 8. Wave shape

Wave 1, in parallel worktrees: W0 in full, W6's two prerequisite defect fixes (the missing `py` alternative in the dead-bash textual regex, and the receipt field that currently lets a `--changed` run authorise a push), W11's generator and seam widening, W4's decisions plus W8's first passthrough box, W10's preflight.

Wave 2: W1's bootstrap and skeleton, W2's binder and loader, W9's prep, W5's skeleton through pre-keying, W10's module extraction.

Waves 3 to 5, independent of each other once the infra-only checkpoint holds: the hooks cutover, the quality cutover, the Bitwarden cutover, and the registry then `.ci` port.

Final wave: the language gate flip, which needs all four cutovers plus the media handoff, and the records close-out.

Sustained ceiling is 10 to 12 concurrent worktrees, 14 at the fan-out bursts, each with `CI_JOBS=2` and `CI_PROFILE=off`. Above 14 the registry merge queue, not the CPU, is the bottleneck, and the duration cache the tier oracle judges stops being meaningful.
