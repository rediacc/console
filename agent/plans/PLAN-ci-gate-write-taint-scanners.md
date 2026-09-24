# PLAN: Gates that write the real tree must declare it (gate-module write-target scanners)
Status: active
First-Seen: 2026-09-24
Owner: d778be9d
Worklist: deb0b82d

## Why

`check:ci-pool-writer-safety` has one job: if something writes into the real tree, it must hold an exclusive `tree:` claim, so the pool cannot run it beside readers of the same paths. Today it enforces that only for gate tests. The gates themselves are the TS/JS/Python/bash leaves listed in `scripts/ci-runner/gates.lock.json`, and the scanner never looks at them. So a gate that plants files in the tree, with no `mutex: ['tree:repo']`, passes.

Concrete instance, found and fixed 2026-09-24. The first cut of the Biome half of `.ci/scripts/quality/lint-rule-liveness.mjs` created 7 files in the tree, 2 of them in `private/account`. It also appended to the tracked `private/account/src/services/email.service.ts` and only restored it in a `finally`. A hard kill skips `finally`, so the append stayed behind. The fix is recorded at `.ci/scripts/quality/lint-rule-liveness.mjs:525` ("WHY NOT THE REAL TREE"): the fixtures now go into an OS temp mirror (`:653`, `:699`). The manifest entry at `scripts/ci-runner/manifest.ts:2443-2455` never had a mutex, and no gate could have noticed. There is a second blind spot: that entry's only leaf is the Python wrapper (`scripts/ci-runner/manifest.ts:2448`). The `.mjs` that did the writing is reached through `subprocess.run(["node", .../DRIVER])` (`.ci/scripts/quality/check_lint_rule_liveness.py:43`, `:69-73`), and the wrapper's docstring (`:24`) forbids listing the `.mjs` as a leaf. A scanner that reads only declared leaves would miss the exact file that did the damage.

## 1. Current state (facts, file:line)

### 1.1 What `check:ci-pool-writer-safety` scans and how
- Registration:
  - `package.json:156` points to `.ci/scripts/quality/check_pool_writer_safety.py`, a 2-import entry point (`:41-47`) whose header is `step: Pool-registered tests do not write the real tree`, `needs: none` (`:34-38`).
  - Manifest entry: `scripts/ci-runner/manifest.ts:2692-2703`, CI step in `quality-static` (`.github/workflows/ci-quality.yml:395-397`, inside the gate-bind region `:275-487`).
- The logic is in `.ci/rediacc_ci/quality/pool_writer_safety.py`. It covers two corpora and nothing else:
  1. **Bash gate tests.**
     - Files: `GATES_DIR_REL = .ci/scripts/test/gates` (`:140`), globbed `test-*.sh` (`:576`).
     - Scanner: a two-pass awk transliteration (`scan_text`, `:278-354`). Pass 1 marks variables as REPO-rooted (seed `$(cd … pwd)` / `rev-parse --show-toplevel` / `get_repo_root`, `:179`) or TEMP-rooted (seed `mktemp|TMPDIR|get_temp_dir|/tmp/`, `:178`). TEMP beats REPO (`_reftype`, `:228-245`).
     - Pass 2 flags redirects, `cp/mv/install/ln` last arguments, `sed -i`, and `rm/mkdir/chmod/touch/truncate` arguments when they are REPO-rooted (`:330-349`).
  2. **Pytest ports.** Found by declaration, not by scanning. A module-level `XDIST_GROUP = … REAL_TREE_GROUP|"real-tree"` (`PORT_GROUP_RE`, `:159-161`; `port_writers`, `:416-433`) requires `check:ci-pytest` to hold an exclusive `tree:` claim (`lane_claims_tree_exclusively`, `:436-454`; enforced at `:557-572`). The docstring at `:422-423` explains why Python got a declaration instead of a scanner: shell redirect syntax does not exist in `pathlib`/`shutil`/`os.replace`.
- How registration is read: `registered_writers` (`:371-413`) takes `mutex` entries (`reads` is rejected, `:150-151`, `:815-820`) and keeps only entries whose `run` names a file under `GATES_RUN_PREFIX = .ci/scripts/test/gates/` (`:148`). Non-gate-test entries are excluded on purpose, and the selftest pins that exclusion (`:828-832`: "a NON-gate-test entry with mutex tree: is not a gate test"). **Nothing in this gate ever looks at a gate module.**
- Controls and refusals:
  - Planted writer and planted temp-writer are checked before any verdict (`:519-539`).
  - Anti-vacuity refusals: lock missing, zero writers, empty gates dir (`:541-581`).
  - The rule is one-directional (`:46`): over-declaring is never reported.
- Blind spots measured today:
  - The lock has 356 entries. File-extension leaves: 172 `.ts`, 166 `.py`, 21 `.js`, 20 `.sh`; the rest are bare tools.
  - The 20 `.sh` leaves outside `.ci/scripts/test/gates/` (for example `.ci/breakpoint/scripts/check-breakpoint-drift.sh`, `.ci/scripts/test/proxies/*.sh`) are not scanned either, even though `scan_text` would accept them.

### 1.2 `mutex` / `reads` semantics
- `scripts/ci-runner/gate-spec.ts:44-45`: `mutex?: string[]` means mutual-exclusion groups. `:46-60`: `reads?: string[]` is a shared claim, and `tree:<x>` in `reads` may not overlap `tree:<x>` in `mutex`.
- `scripts/ci-runner/pool.ts:17-24` states the contract (exclusive vs shared, one namespace, a multiple-readers/single-writer lock keyed on strings).
  - `:206-209` `sharedClaims`.
  - `:238-240` `blockedByClaim`: exclusive conflicts with any claim; shared conflicts only with exclusive.
  - `:264-265` claims are taken at launch; `:324` releases them.
  - `.ci/rediacc_ci/battery.py:105` `classify_from_lock` implements the same contract for the battery.
- Resource names are opaque strings (`scripts/ci-runner/pool.ts:51-53` "PATH-SCOPED (`tree:<dir>`)"). `tree:repo` does not conflict with `www-src-probe` or `tree:packages/www`.
- **Who holds `tree:` claims today (lock):** only `check:ci-pytest` with `mutex: ['tree:repo']` (`scripts/ci-runner/manifest.ts:4820`) and `gate-test:runner-advice` with `reads: ['tree:repo']` (`scripts/ci-runner/manifest.ts:4909-4911`).
- **Consequence the plan has to own:** adding `mutex: ['tree:repo']` to a tree-writing gate serialises it only against those two entries. Every other reader of the tree (hundreds of scanners) declares nothing and still overlaps it. The mutex is the weak fallback; writing to a copy (what lint-rule-liveness did) is the real fix. The mutex also cannot help with the hard-kill residue that made lint-rule-liveness dangerous.
- `mutex` is a HAND-ONLY field. `scripts/gen/gen-manifest.ts:64-72` lists it in `HAND_ONLY`, so an entry that carries it drops out of the generated regions and is written by hand. `gen-gates-lock.ts` serialises the whole spec, so a new GateSpec field reaches the lock without code changes (scripts/ci-runner/gate-spec.ts:73-75 says this about `env`).
- The runner's cwd is the repo root (`scripts/ci-runner/run.ts:271`, `:291`, `:302`, `:325`, `:330`: `cwd: REPO_ROOT`). A relative-path write, or a subprocess with no `cwd`, therefore lands in the tree.
- In GitHub Actions, steps within a job run sequentially. The concurrency hazard is in `npm run ci` (pool.ts) and the battery. The kill-residue hazard applies everywhere, including a developer's tree.

### 1.3 Findings from a read-only prototype (in-memory `ast` pass, 2026-09-24, nothing written)

Python, over the import closure of every `gate: true` `.py` leaf (following `rediacc_ci.*` imports, excluding `tests/`):
- 279 files, 999 write sites.
- Name-regex classification: 677 TEMP. Scope-aware tracking (with/for/assign bindings and enclosing scopes) plus module-local call-site parameter propagation: 890 TEMP, 41 TREE, 35 PARAM, 33 UNK. So **68 sites stay unresolved** after one level of interprocedural propagation.
- Parameter propagation is load-bearing, not optional. Without it, 272 sites were PARAM. The real violator `.ci/rediacc_ci/quality/proxy_image_smoke.py:281` (`shutil.copyfile(prebuilt, staged)` inside `_stage_renet(root)`, called with `paths.repo_root()` at `:414-415`) only resolves to TREE through a call site.
- Name heuristics alone are unusable. `.ci/rediacc_ci/quality/actions_vars.py:454`, `.ci/rediacc_ci/quality/ci_job_aggregation.py:603`, `.ci/rediacc_ci/quality/account_portal.py:269`, `.ci/rediacc_ci/quality/audit_coverage.py:399` and `.ci/rediacc_ci/quality/battery_clean_tree.py:432` all name a variable `root` that is bound to `pathlib.Path(tmp)`. This is the same "TEMP beats name" lesson as `.ci/rediacc_ci/quality/pool_writer_safety.py:57-59`.

TS/JS, regex-only over relative-import closures of `.ts/.js/.mjs` leaves: 251 non-temp-named sites. Every one of the 45 "TREE-named" sites opened was either a real tree writer (below), mode-gated, temp in disguise, or unreachable. Three false-positive shapes the real scanner must handle:
- `import type` edges. `packages/www/scripts/check-solution-video-engine.ts:37` imports only a type from `update-video-manifest.ts`, whose `saveManifest` (`:131-134`) writes the tracked `packages/www/src/data/video-manifest.json`.
- Product code pulled in by relative imports. `packages/cli/src/services/account/subscription-auth.ts:70` and `packages/cli/src/services/core/audit-log.ts:178` write under the user config dir.
- Callback parameters. In `scripts/__tests__/check-docs-render-parity.control.ts:114-125`, `plant: (root) => …` receives `root` from `c.plant(root)` at `:195`, and that root is a `mkdtempSync` at `:91`.

## 2. Existing violators (unguarded tree writes reached by a registered gate)

| # | Gate (manifest line) | Write site | Target | Ignored? | Disposition |
|---|---|---|---|---|---|
| V1 | `check:ci-python-lint` (`scripts/ci-runner/manifest.ts:1542`, no mutex, quality-static) | `.ci/rediacc_ci/quality/python_lint.py:357-365` | `enum_probe_<pid>_<ts>.py` at the repo ROOT (CONTROL 3: "enumeration must reach an untracked file") | NOT ignored (`git check-ignore` exit 1) | **Refactor.** Run CONTROL 3 against a temp `git init` fixture carrying a copy of the real `.gitignore`. The control proves `enumerate_py` includes untracked files, which needs a work tree, not the real one. |
| V2 | `check:ci-config-migrations` (`scripts/ci-runner/manifest.ts:3133`, no mutex) | `.ci/rediacc_ci/quality/config_migrations.py:250-276` | `packages/cli/.config-migrations-check.tmp.ts` (`TMP_SCRIPT_NAME`, `:102`) | NOT ignored | **Refactor.** Feed `TSX_SOURCE` (`:105`) to `npx tsx` on stdin or with `--eval`, `cwd=packages/cli`, so `@rediacc/shared/config-schema` (`:107`) still resolves and no file is written. Measure first; fallback is mutex plus declaration. |
| V3 | `check:ci-proxy-image-smoke` (`scripts/ci-runner/manifest.ts:5196`, local-only, heavy, no mutex; file is new and uncommitted) | `.ci/rediacc_ci/quality/proxy_image_smoke.py:274-283` (copyfile, chmod), `go build -o <staged>` in the same function, `:446-448` unlink | `workers/proxy/renet/renet-linux-amd64` | ignored (`workers/proxy/renet/.gitignore:3`) | **Mutex plus `writesTree`.** The Dockerfile `COPY workers/proxy/renet/` (`workers/proxy/Dockerfile:54`) fixes the build context to the tree. Refactoring needs `docker build --build-context`, which is a Dockerfile change outside this plan. Local-only and heavy, so serialising costs ~nothing. |
| V4 | `check:i18n:key-usage` (`scripts/ci-runner/manifest.ts:252-262`, `mutex: ['www-src-probe']` only) | `scripts/__tests__/check-translation-key-usage.control.ts:156-179`, `:200-212` | `packages/www/src/components/__control_probe__.tsx` | NOT ignored | **Refactor.** Add a root seam to `scripts/gates/check-translation-key-usage.ts`, as `DOCS_RENDER_PARITY_ROOT` does for its sibling (`scripts/__tests__/check-docs-render-parity.control.ts:27`, `:57`), and plant the probe in a temp mirror of the scanned `WWW_SRC`. The in-file justification (`:146-150`, "MUST be written into the real www source tree") holds only because no seam exists. Interim: add `tree:repo` to its mutex plus `writesTree`. |
| V5 (bash leaf) | `check:ci-breakpoint-drift` (`package.json:246`) | `.ci/breakpoint/scripts/check-breakpoint-drift.sh:207` `} >"$MANIFEST"` | `.ci/breakpoint/MANIFEST.sha256` | tracked | **Mode-gated.** Reached only under `--write` (`:148-151`), and the registered command passes no flag. Annotate with the mode pragma (§3.5). No mutex. |
| (fixed) | `check:ci-lint-rule-liveness` (`scripts/ci-runner/manifest.ts:2443`) | first cut: `path.join(ROOT, fx.file)` plus append to `email.service.ts` | tracked `private/account` source | tracked | Already refactored to a temp mirror (`.ci/scripts/quality/lint-rule-liveness.mjs:653`, `:699`). It becomes the **regression fixture pair** (§4). |

Mode-gated baseline/refresh writers that the scanner must classify as not run by the gate. Confirmed by reading the guard:
- `.ci/rediacc_ci/quality/account_env_retired.py:236` via `--write-baseline` (`:250`)
- `.ci/rediacc_ci/quality/plant_proofs.py:1063` (`:1142`)
- `.ci/rediacc_ci/quality/python_env_registry.py:517` (`:549`)
- `.ci/scripts/quality/check_language_policy.py:463` (`:842`)
- `.ci/scripts/quality/check_plan_boxes.py:1160` via alias `update = "--update" in argv` (`:1146`)
- `.ci/scripts/quality/check_resprofile.py:205` via `--seed` (`:334`)
- `.ci/rediacc_ci/quality/prose_style.py:1923` via `if write:`
- `scripts/gate-bind.ts:2139/2216/2445` via `--write`/`--extract-all` (`:2087-2117`)

Prototype TREE hits whose guard was NOT verified (task 2.3 confirms each):
- `.ci/rediacc_ci/quality/python_types.py:814`
- `.ci/scripts/quality/check_job_timeout_headroom.py:228`
- `.ci/scripts/quality/check_runner_advice.py:754`
- `.ci/scripts/quality/check_secret_reachability.py:222`
- `.ci/scripts/quality/check_tree_shape.py:449`
- `.ci/scripts/quality/check_plan_folders.py:456-546`
- `.ci/scripts/quality/check_plan_record.py:800`
- `.ci/scripts/quality/check_actions_allowlist.py:106`
- `.ci/scripts/quality/check_agent_session_archival.py:436`
- `.ci/rediacc_ci/quality/prose_style.py:1299`
- `.ci/rediacc_ci/security/actionlint.py:301`, which is probably a prototype false positive: its comment says the cache lives under a temp root.

Scratch writes (allowed, §3.4): `.ci/rediacc_ci/quality/python_lint.py:429-437` and `:544-553` (`.ci/cache/ruff-control-*`).

## 3. Design

### 3.1 Shape: a new sibling gate
New gate `check :ci-gate-tree-writes`, step "Gates that write the real tree declare it". Widening `check:ci-pool-writer-safety` was considered and rejected, for three reasons:
- That gate's output contract is pinned byte-for-byte by its shadow history (`.ci/rediacc_ci/quality/pool_writer_safety.py:17-32`, `:114-115`).
- It needs no node, and this gate needs `oxc-parser`.
- Its corpus is "gate tests", and changing what a green means under the same step name is the silent-widening pattern the repo keeps flagging.

The two gates cross-reference each other in their docstrings. Implementation files:
- `.ci/rediacc_ci/quality/gate_tree_writes.py`: orchestrator, Python AST scanner, policy, `--selftest`.
- `.ci/scripts/quality/check_gate_tree_writes.py`: entry point, same 2-import shape as `.ci/scripts/quality/check_pool_writer_safety.py:41-47`.
- `scripts/lib/tree-write-sites.ts`: JS/TS extractor on `oxc-parser` (already an exact devDep, `package.json:440`, used by `scripts/gates/check-control-in-string.ts:40` and `scripts/lib/rule-host.ts:40`). CLI `--json <files…>` prints `[{file,line,sink,target,origin,guard}]`. It also has `--selftest`.
- `.sh` leaves reuse `pool_writer_safety.scan_text` unchanged, imported rather than copied.

### 3.2 Corpus: what counts as a gate module
1. **Entries.** Every lock entry the pool can schedule: `gate: true`, plus `gate: false` entries that some scheduled entry `needs`. `build:*` already hold `build-artifacts`/`www-dist` and write only gitignored outputs through bare tools, so they are reported as `bare-leaf, not scanned`, never silently skipped.
2. **Invocations.** For each entry, resolve `run` through package.json to `(leaf, argv)` pairs. Factor the resolver out of `scripts/gates/check-ci-parity.ts:154` (`resolveLeaves`, not exported today) into an exported `resolveInvocations` that keeps argv. `resolveLeaves` becomes a projection of it, so check-ci-parity's behaviour must stay byte-identical (test for that). The argv matters for mode gating (§3.5): `check:ci-lint-rule-units` runs its leaf twice, once with `--selftest` and once bare (`package.json:195`).
3. **Closure**, per language:
   - Python: `from rediacc_ci… import` / `import rediacc_ci…`, resolved to `.ci/rediacc_ci/**`, skipping `tests/`.
   - TS/JS: relative `import`/`export … from`/`require()`/dynamic `import()` with a literal specifier, with `.js→.ts` mapping. `import type` / `export type` edges are skipped (they are erased at runtime; update-video-manifest shape). Workspace product sources `packages/*/src/**` are not entered. That is a declared boundary: product code writes user config, not the repo. The selftest pins the boundary (a planted write in a product file reached from a gate is *not* reported, and the report counts "N product modules not entered" so the boundary is visible).
   - **Cross-language spawn edges** (the lint-rule-liveness hole): a string literal, or a module constant resolved one hop, ending in `.py/.mjs/.cjs/.js/.ts/.sh` that appears inside the argument subtree of a subprocess/spawn/exec call, or inside a `Path(__file__).parent / X` expression that flows into one. It is resolved relative to the module's directory, then the repo root. If the file exists, it joins the closure. `.ci/scripts/quality/check_lint_rule_liveness.py:43` + `:70` must resolve to `lint-rule-liveness.mjs`, and a REAL control pins that.
4. **Reachability.** Every top-level statement of a closure module is reachable, because it runs at import. A function is reachable if an identifier or attribute reference to it occurs in reachable code of its own module, or in a module that imports that binding by name, namespace attribute or default. That rule is what drops `saveManifest` when only a type was imported.

### 3.3 Sinks
- **Python.** Mode detection for `open`/`io.open`/`Path.open` uses mode `w|a|x|+`. `os.open` counts when its flags include `O_WRONLY|O_RDWR|O_CREAT|O_TRUNC|O_APPEND`. Write methods: `Path.write_text/write_bytes/touch/mkdir/unlink/rmdir/rename/replace/symlink_to/hardlink_to/chmod`. For `rename`/`replace`, both source and destination are targets, since the source disappears. Other sinks:
  - `shutil.copy/copy2/copyfile/copytree/move` (destination; `move` also the source) and `shutil.rmtree`.
  - `os.remove/unlink/rename/replace/renames/makedirs/mkdir/rmdir/removedirs/symlink/link/chmod/truncate/utime`.
  - `tarfile`/`zipfile` `.extractall(path)`.
  - Subprocess (`subprocess.run/call/check_call/check_output/Popen`, `os.system`, `os.exec*/spawn*`) whose argv[0] (literal, or a Name resolving to one) is in the mutator table below.
- **TS/JS.** `fs.*` and named imports from `node:fs`, `fs`, `node:fs/promises`, `fs/promises`, plus `fs.promises.*`. Covered calls: `writeFile/appendFile/mkdir/mkdtemp/rm/rmdir/unlink/rename/copyFile/cp/symlink/link/truncate/chmod/utimes/createWriteStream`. Each has Sync, callback and promise forms, and `open` counts with a write flag. `mkdtemp` is a sink too, because `mkdtemp(path.join(ROOT,'x-'))` is a tree write. Also `child_process.execSync/execFileSync/spawnSync/spawn/exec/execFile` with a literal command string or argv in the mutator table, and `process.chdir`, which is recorded only to say relative paths are TREE.
- **Mutator table** (one shared JSON, `.ci/policy/tree-write-mutators.json`, read by both scanners so they cannot drift):
  - `git {add, commit, checkout, switch, restore, reset, stash, clean, apply, am, rm, mv, merge, rebase, cherry-pick, update-index, worktree}`. The target is `-C <x>`, else the `cwd` option, else the process cwd.
  - `sed` with `-i`, `perl -i`: last argument.
  - `cp/mv/install/ln`: last argument, like `.ci/rediacc_ci/quality/pool_writer_safety.py:182` + `:332`.
  - `rm/mkdir/touch/chmod/truncate/tee`: every non-flag argument (`:184`, `:335`).
  - `go build -o <x>`.
  - `npm/npx install|ci|i`.
  - `biome|prettier … --write`, `eslint … --fix`: target is `cwd`.
  - `tar -x … -C <x>`.

### 3.4 Target resolution: the origin lattice
Each expression gets one origin: `TEMP`, `SCRATCH`, `TREE`, `UNRESOLVED`. Combining origins is ordered **TEMP > SCRATCH > TREE > UNRESOLVED**: any TEMP component makes the path TEMP. That is the bash scanner's rule (`.ci/rediacc_ci/quality/pool_writer_safety.py:228-245`), which cut an earlier draft's false positives from 21 lines to 6.

- **TEMP seeds.**
  - Python: `tempfile.mkdtemp/mkstemp/TemporaryDirectory/NamedTemporaryFile/TemporaryFile/gettempdir`, `rediacc_ci.runtmp.run_dir/shared/shell_mktemp` (`runtmp.py` `__all__`), `os.environ["TMPDIR"]`/`.get`, a `"/tmp/"` literal prefix.
  - TS: `os.tmpdir()`, the result of `fs.mkdtemp*`, `process.env.TMPDIR`.
- **SCRATCH seeds.** A TREE expression whose literal path segments place it under `.ci/cache/`, which is gitignored (`.gitignore:137`) and pruned by `paths.walk_tree` (`.ci/rediacc_ci/paths.py:175-179`). The allowlist is a one-entry constant with that justification. It is deliberately not "anything gitignored": `packages/*/dist` are ignored and still need `build-artifacts`/`www-dist`, and V3's staging path is ignored and still collides.
- **TREE seeds.**
  - Python: `paths.repo_root/from_root/ci_dir/quality_dir/hooks_stop_dir/find_repo_root`, `get_repo_root()`, any `__file__` chain, `os.getcwd()`, `Path.cwd()`, `Path(".")`, the stdout of `git rev-parse --show-toplevel`, **and any relative string-literal path** used as a target. Relative paths are TREE because scripts/ci-runner/run.ts:271 runs every gate from `REPO_ROOT`.
  - TS: `process.cwd()`, `__dirname`, `import.meta.dirname`, `fileURLToPath(import.meta.url)`, `path.resolve(<relative literals only>)`, relative literals.
  - A subprocess mutator with no `cwd`/`-C` has target = process cwd = TREE.
- **Propagation (how much taint tracking).** Measured to be the minimum that works:
  1. **Intra-procedural** through `=`, annotated assignment, `with … as`, `for … in`, walrus, `path.join/resolve`, `/`, `joinpath`, `.parent`, `.resolve()`, `str()`, f-strings and template literals, with enclosing-scope lookup for nested functions and closures (the `.ci/rediacc_ci/quality/ci_job_aggregation.py:603-608` shape).
  2. **Module-local interprocedural**, to a fixpoint. A parameter's origin is the combination of its argument origins over every call site in the module. Any TREE argument makes the parameter TREE. All-TEMP makes it TEMP. Arguments omitted from a call take the default's origin, so `root = pathlib.Path(root or paths.repo_root())` (`.ci/rediacc_ci/quality/account_env_retired.py:193`) is TREE when a call site omits it. Callbacks follow property name: a parameter of `k: (p) => …` takes origins from `x.k(args)` in the same module.
  3. **Module constants** across one import hop (`import { ROOT } from …`). The only cross-module case measured is `eslint-rules/lib/paths.js`; 76 gate files define ROOT locally.
  4. Nothing deeper: no cross-module parameter flow, no container or field sensitivity. Anything else is `UNRESOLVED`. In the prototype that is 68 Python sites in 74 files.
- **Why not a conservative rule alone?** "Every write site whose target is not provably TEMP must be declared" would make ~109 Python sites (PARAM + UNK + TREE) plus an unmeasured TS count need a declaration before the first run. That is the cry-wolf outcome `.ci/rediacc_ci/quality/pool_writer_safety.py:31-44` warns about. Why not full taint instead? The measured gain from propagation stops at the module boundary: steps 1-2 took unresolved sites from 305 to 68, and the remaining 68 are mostly `for x in <list>` and container-derived paths that no cheap analysis settles. **Hybrid:** mechanical propagation 1-3, and explicit declarations for what is left (§3.5).

### 3.5 Declarations and verdicts
Every scanned site ends as exactly one of:
- **SAFE** (TEMP or SCRATCH): silent, counted.
- **TREE**: the entry must hold an exclusive `tree:` claim in the lock (`mutex`, `reads` rejected, the same rule as `.ci/rediacc_ci/quality/pool_writer_safety.py:150-151`) **and** carry `writesTree: '<reason>'`.
  - The new hand-only GateSpec field sits beside `mutex` (`scripts/ci-runner/gate-spec.ts:45`) and is added to `HAND_ONLY` (`scripts/gen/gen-manifest.ts:64-72`). It is declared in the manifest, not the leaf header, because the claim it justifies lives there and the lock (what this gate reads) serialises it for free.
  - Consistency is enforced both ways in this gate: `writesTree` without a `tree:` mutex is red, and a `tree:` mutex without `writesTree` is red. `check:ci-pytest` gets `writesTree` naming its two real-tree ports.
  - A `writesTree` entry with zero TREE sites is **not** red (one-directional, `.ci/rediacc_ci/quality/pool_writer_safety.py:46`). It is listed as `declared, no site found` so over-declaration stays visible without being pushed.
- **MODE-GATED**: the site is dominated by a truthy test of a flag literal that no registered invocation of that leaf passes (§3.2.2). Recognised guards:
  - Python: `"--x" in argv|sys.argv|args`, `argv[0] == "--x"`, argparse `args.x` where `add_argument("--x", action="store_true")`, and one alias hop (`update = "--update" in argv; if update:`, `.ci/scripts/quality/check_plan_boxes.py:1146`).
  - TS: `argv.includes('--x')`, `process.argv.includes`, and one alias hop (`const write = argv.includes('--write')`, `scripts/gate-bind.ts:2088`).
  - A function whose every module-local call site is mode-gated is mode-gated. A write-flag parameter (`if write:` in prose_style) is gated when every call site passes a mode-gated value.
  - The verdict names the flag. A MODE-GATED site becomes TREE the moment any registered invocation passes that flag.
- **UNRESOLVED**: red unless the line, or the line above it, carries a pragma: `# tree-write: safe <reason>` / `// tree-write: safe <reason>`, or for bash-scanner hits and unrecognised guards `# tree-write: mode --flag <reason>`.
  - Pragma rules, all enforced: the reason is at least 20 characters. A `safe` pragma on a site the scanner resolves as TEMP or SCRATCH is red as **stale**. A `safe` pragma on a resolved TREE site is ignored and reported, because a pragma cannot overrule a proven write. A `mode` pragma is honoured only if the named flag is absent from every registered invocation.
  - Pragma count per file is printed, not baselined. Reason: adding one is a reviewed diff with a reason, and a shrink-only baseline for an already-explicit declaration would be a second copy of the same fact.

### 3.6 Anti-vacuity refusals (exit 1, each named)
- The lock is missing or unparseable.
- Zero entries resolved to a scannable leaf.
- The closure of `check:ci-lint-rule-liveness` does not contain `lint-rule-liveness.mjs` (the spawn edge broke).
- The TS extractor exits non-zero or prints non-JSON. It must never read as "no sites".
- Total sites seen < floor. Set the floor from the first measured run at roughly 80% of the Python and TS counts, as `Controls(..., floor=…)` does in `.ci/rediacc_ci/quality/pool_writer_safety.py:632`.
- Zero TEMP sites (the resolver died).
- Zero TREE-or-MODE-GATED sites (the TREE seeds died; the live tree has at least 8 confirmed mode-gated writers).

## 4. Controls (both directions, on every run, before the real verdict)

Controls are planted into a `tempfile.TemporaryDirectory()` and reached through seams `GATE_TREE_WRITES_LOCK`, `GATE_TREE_WRITES_PKG`, `GATE_TREE_WRITES_ROOT`. They are copied, never symlinked, for the reason at `.ci/rediacc_ci/quality/pool_writer_safety.py:28-29`.

| Control | Fixture | Must |
|---|---|---|
| C1 TS tree writer | The lint-rule-liveness wave-2 shape: `const ROOT = path.resolve(HERE,'../../..'); fs.appendFileSync(path.join(ROOT, fx.file), code)` plus `writeFileSync(path.join(ROOT,'private/account/src/__x.ts'))`, no mutex | red, both sites named with file:line |
| C1' mirror | The current shape: `mkdtemp(path.join(os.tmpdir(),'biome-plugin-liveness-'))` → `path.join(mirrorRoot, fx.file)`, with a decoy `const ROOT` also referenced in the same `path.join` | green (TEMP beats TREE) |
| C2 Python tree writer | `probe = pathlib.Path(paths.repo_root()) / "enum_probe.py"; probe.write_text(...)` (V1 shape) | red |
| C2' mirror | `with tempfile.TemporaryDirectory() as tmp: root = pathlib.Path(tmp); (root/".github").mkdir(...)` (the `.ci/rediacc_ci/quality/actions_vars.py:454` shape, the name that fooled the prototype) | green |
| C3 parameter flow | `def stage(root): shutil.copyfile(a, root / "x")` called with `paths.repo_root()` (V3 shape) | red. Mirror: same body, only called with a `mkdtemp` → green |
| C4 spawn edge | Python entry with `DRIVER = "d.mjs"` and `subprocess.run(["node", str(Path(__file__).parent / DRIVER)])`, where `d.mjs` writes `path.join(ROOT,'f')` | red on `d.mjs`. Mirror: `DRIVER` names a missing file → closure refusal, not green |
| C5 mode gate | `if "--write-baseline" in argv: (root/BASE).write_text(...)` with registered argv `[]` | green, reported MODE-GATED. Mirror: registered argv contains `--write-baseline` → red |
| C6 registration | C1 fixture plus lock `mutex:['tree:repo'], writesTree:'…'` | green. `reads:['tree:repo']` → red. `mutex` without `writesTree` → red. `writesTree` without `mutex` → red |
| C7 type-only import | Gate `import type {T} from './lib'`, where `lib` has an exported writer to TREE | green. Mirror: value import that calls it → red |
| C8 pragma | UNRESOLVED site with a `safe` pragma → green. Same pragma on a TEMP site → red (stale). On a TREE site → still red |
| C9 subprocess | `subprocess.run(["git","add","-A"])` with no cwd → red. With `cwd=tmp` → green. `execSync('sed -i s/a/b/ ' + path.join(ROOT,'f'))` → red |
| C10 scratch | `(repo_root()/".ci"/"cache"/"x").mkdir()` → green. `(repo_root()/"packages"/"www"/"dist")` → red |
| REAL | Live lock: the lint-rule-liveness closure contains the `.mjs`. At least one TEMP and one MODE-GATED site. `check:ci-pytest` carries both `tree:repo` and `writesTree` | all true |

## 5. Wiring
- **package.json:** `"check :ci-gate-tree-writes": ".ci/scripts/quality/check_gate_tree_writes.py"`. Bare path, not `python3 …`, because check-ci-parity resolves a `python3` prefix to the leaf `[python3]` (`.ci/scripts/quality/check_pool_writer_safety.py:8`).
- **Entry header:**
  ```
  ---- gate ----
  step: Gates that write the real tree declare it
  needs: node
  lane: quality-code
  selftest: true
  why: A gate that writes the shared tree without an exclusive tree: claim runs beside its readers and leaves residue on a hard kill; check:ci-pool-writer-safety only sees gate tests
  ---- end gate ----
  ```
  `quality-code` is where the oxc-parser gate `check-control-in-string.ts` already runs.
- **Manifest:**
  - `gate-bind --extract` produces the entry.
  - Add `writesTree?: string` to `GateSpec` (`gate-spec.ts`, after `:60`) and to `HAND_ONLY` (`scripts/gen/gen-manifest.ts:64-72`).
  - Add `writesTree` to `check:ci-pytest` (`scripts/ci-runner/manifest.ts:4820`), plus V3, plus V4 if the seam refactor slips.
  - `paths:` = `.ci/rediacc_ci/**`, `.ci/scripts/**`, `scripts/**`, `packages/*/scripts/**`, `eslint-rules/**`, `.ci/breakpoint/scripts/**`, `package.json`, `scripts/ci-runner/gates.lock.json`, `.ci/policy/tree-write-mutators.json`, with `pathsOrigin: 'declared'`.
- **Workflow:** `npx tsx scripts/gate-bind.ts --write` emits the step into the quality-code gate-bind region of `.github/workflows/ci-quality.yml`. Do not hand-write it. The file must be `git add`-ed first, because gate-bind scans tracked files only (PLAN-ci-vacuity-baseline-registry box 54).
- **Lock:** `npm run gen:gates-lock`, then `npm run check:ci-gates-lock`. The `writesTree` field appears in the lock without generator changes.
- **Anti-vacuity registry:** add a row to `.ci/rediacc_ci/tests/gates/test_gate_gate_anti_vacuity.py` (next to `:92`), `(".ci/scripts/quality/check_gate_tree_writes.py", "VACUOUS")`.
- **Pytest:** `.ci/rediacc_ci/tests/test_quality_gate_tree_writes.py`, collected by `check:ci-pytest`, drives `scan_python`, the policy and `main()` through the seams in both directions. Add `scripts/lib/__tests__/tree-write-sites.test.ts` if the TS helper has a vitest home. Otherwise its `--selftest` is called from the gate's selftest.
- **Docs:**
  - `docs/agent-reference/ci-gates.md:69` (isolation paragraph): tree writers declare `mutex: ['tree:repo']` + `writesTree`, the preferred fix is to write to a temp copy, and the pragmas are listed.
  - `docs/agent-reference/TRAPS.md:631` `concurrency-artifact-not-a-flake`: update `Enforced-By`/`Residue`, since gate modules are now scanned.
  - Cross-reference paragraphs in `pool_writer_safety.py` (docstring, after `:46`) and the `pool.ts` header (`:51-53`).
  - `gate-spec.ts` field doc for `writesTree`.

## Tasks

- [ ] 1.1 Export `resolveInvocations(cmd) → {leaf, argv}[]` from `scripts/gates/check-ci-parity.ts` (around `:154`) and make `resolveLeaves` its projection. Prove check-ci-parity's output is byte-identical before and after on the live tree.
- [ ] 1.2 Add `.ci/policy/tree-write-mutators.json` (git/sed/cp/rm/…/`--write`/`--fix` table, §3.3), read by both scanners.
- [ ] 1.3 Write `scripts/lib/tree-write-sites.ts` on `oxc-parser`: closure (relative imports, `.js→.ts`, skip `import type`, stop at `packages/*/src`), sinks (§3.3), origin lattice (§3.4, steps 1-3 plus property-name callbacks), mode guards (§3.5), pragmas, and `--json`/`--selftest`.
- [ ] 1.4 Write `.ci/rediacc_ci/quality/gate_tree_writes.py`: Python closure (imports plus spawn edges, §3.2.3), reachability (§3.2.4), sinks, origin lattice with module-local fixpoint, mode guards, pragmas, `.sh` leaves via `pool_writer_safety.scan_text`, lock policy (§3.5), refusals (§3.6), and controls C1-C10 plus REAL (§4).
- [ ] 1.5 Add `writesTree?: string` to `scripts/ci-runner/gate-spec.ts` and `HAND_ONLY` in `scripts/gen/gen-manifest.ts:64-72`. Add `writesTree` to `check:ci-pytest` (`scripts/ci-runner/manifest.ts:4820`) naming `test_gate_gate_anti_vacuity.py` and `test_gate_generate_tag_inputs.py`.
- [ ] 2.1 Run the gate in report-only mode (`--report`, exit 0, full listing) on the live tree. Record per-bucket counts (SAFE/TREE/MODE-GATED/UNRESOLVED, Python and TS separately) in this plan. Set the §3.6 floors from those counts.
- [ ] 2.2 Triage every UNRESOLVED site. Improve the resolver where a shape recurs 3 or more times; otherwise add a `tree-write: safe <reason>` pragma. Record the final pragma count.
- [ ] 2.3 Confirm or refute each unverified prototype TREE hit in §2 (.ci/rediacc_ci/quality/python_types.py:814, .ci/scripts/quality/check_job_timeout_headroom.py:228, .ci/scripts/quality/check_runner_advice.py:754, .ci/scripts/quality/check_secret_reachability.py:222, .ci/scripts/quality/check_tree_shape.py:449, .ci/scripts/quality/check_plan_folders.py:456-546, .ci/scripts/quality/check_plan_record.py:800, .ci/scripts/quality/check_actions_allowlist.py:106, .ci/scripts/quality/check_agent_session_archival.py:436, .ci/rediacc_ci/quality/prose_style.py:1299, .ci/rediacc_ci/security/actionlint.py:301). Any that is a real unguarded write becomes a new V-row.
- [ ] 3.1 V1: move `.ci/rediacc_ci/quality/python_lint.py:357-365` CONTROL 3 onto a temp `git init` fixture carrying the real `.gitignore`. The control must still red when `enumerate_py` drops untracked files (plant that and show it).
- [ ] 3.2 V2: replace the `packages/cli/.config-migrations-check.tmp.ts` write (`.ci/rediacc_ci/quality/config_migrations.py:250-276`) with stdin or `--eval` to `npx tsx` under `cwd=packages/cli`. Measure that `@rediacc/shared/config-schema` resolves. If it does not, fall back to `mutex: ['tree:repo']` + `writesTree` and record why.
- [ ] 3.3 V3: add `mutex: ['tree:repo']` + `writesTree: 'stages workers/proxy/renet/renet-linux-amd64 into the docker build context (Dockerfile:54 COPY)'` to `check:ci-proxy-image-smoke` (`scripts/ci-runner/manifest.ts:5196`).
- [ ] 3.4 V4: add a WWW_SRC root seam to `scripts/gates/check-translation-key-usage.ts` and move `scripts/__tests__/check-translation-key-usage.control.ts:156-212` onto a temp mirror. Then drop `www-src-probe` from both `check:i18n:key-usage` (`scripts/ci-runner/manifest.ts:259`) and `lint:unused` (`scripts/ci-runner/manifest.ts:169`) if nothing else claims it, and rewrite the "MUST be written into the real tree" comment (`:146-150`). If the seam slips, add `tree:repo` + `writesTree` as the interim fix.
- [ ] 3.5 V5: add `# tree-write: mode --write regenerates the vendored manifest; the registered gate runs verify` at `.ci/breakpoint/scripts/check-breakpoint-drift.sh:207`.
- [ ] 4.1 Register: package.json key, entry header, `gate-bind --extract`/`--write` (step emitted into quality-code), `gen:gates-lock`, `check:ci-gates-lock`, `check:ci-gate-bind`, `check:ci-parity`, `check:ci-gate-manifest` green.
- [ ] 4.2 Add the anti-vacuity row to `test_gate_gate_anti_vacuity.py` and the pytest module `test_quality_gate_tree_writes.py`. Run `npm run check:ci-pytest` green.
- [ ] 4.3 Differential proof on the live tree: re-plant the lint-rule-liveness wave-2 shape (append to a copy of the real `lint-rule-liveness.mjs` in a temp fixture tree reached through the seams, never the real tree) → gate red naming the `.mjs` line. Remove the plant → green with byte-identical other output.
- [ ] 4.4 Flip from report-only to enforcing. Confirm `npm run ci` is green and that `check :ci-gate-tree-writes` appears in the pool run.
- [ ] 5.1 Docs: `docs/agent-reference/ci-gates.md:69`, `docs/agent-reference/TRAPS.md:631` (Enforced-By/Residue), `pool_writer_safety.py` docstring cross-ref, `pool.ts` header, `gate-spec.ts` `writesTree` doc.
- [ ] 5.2 Close worklist #deb0b82d with the measured bucket counts and the V1-V5 dispositions.

## 6. Risks
- **Performance.** Parsing ~280 Python files plus the TS closures once per run should cost a few seconds, since oxc is fast. If the tier oracle asks for it, mark the entry `slow: true` rather than narrowing the closure.
- **The mutex is weak** (§1.2). The gate's red message must say "prefer writing to a temp copy; the mutex only serialises against declared `tree:` claimants (today check:ci-pytest and gate-test:runner-advice)", so nobody treats the mutex as the fix.
- **Bare-tool leaves** (tsc, astro, biome, knip, vitest) and product code are declared out of scope and counted in the report. They are not silently skipped.

### Critical Files for Implementation
- /home/developer/console/.ci/rediacc_ci/quality/pool_writer_safety.py
- /home/developer/console/scripts/ci-runner/manifest.ts
- /home/developer/console/scripts/ci-runner/gate-spec.ts
- /home/developer/console/scripts/gates/check-ci-parity.ts
- /home/developer/console/.ci/scripts/quality/lint-rule-liveness.mjs
