/**
 * The gate INVENTORY's type shape, split out of manifest.ts on 2026-09-04.
 *
 * WHY SEPARATELY. manifest.ts is 5,654 lines and 192 KB. A binder that DERIVES entries
 * from per-gate declarations needs these types without importing 378 entries and 192 KB
 * to get them -- and so does anything else that only wants the shape. Splitting the types
 * is the non-behavioural half of that work: every existing importer keeps working, because
 * manifest.ts re-exports them.
 *
 * THE THREE TEXT PARSERS ARE GONE, and this paragraph used to give them as the reason
 * manifest.ts "has to keep containing every entry literally". wl_reggate.py, then
 * the gate-id-convention gate and check_test_file_orphans.py (both on 2026-09-06, W2.4a),
 * were each moved onto `scripts/ci-runner/gates.lock.json`, the committed JSON projection
 * of this literal. All three had been wrong in the same silent direction: the regex read
 * 259 of 261 entries in one case and 373 of 420 in another, always short, always green.
 * The literal is still the source of truth -- gen-gates-lock.ts projects it and
 * check:ci-gates-lock keeps the two faithful -- but no longer because anything parses it
 * as text, so do not cite a text parser as the constraint that keeps it in this shape.
 */

export interface GateSpec {
  /**
   * Skip the per-gate process-tree sampler for this gate. Only for gates that
   * PLANT structural defects on purpose: check:ci-resprofile's selftest spawns an
   * unreaping parent with four zombies, and the sampler caught it on the first
   * default-on run -- a correct finding on a fixture, which would have poisoned
   * the E6 fire rate in any seed. The profiler must not profile its own test.
   */
  noProfile?: boolean;
  /** npm script key, or a synthetic node id like 'build:packages'. */
  id: string;
  /** Exact command to run, and the exact rerun line printed on failure. */
  run: string;
  /**
   * false for prerequisite nodes (build:*) that validate nothing, and for
   * CI-side aggregates whose constituents are scheduled individually. A false
   * entry runs only when something that `needs` it is in the selected set, so an
   * aggregate with no dependents never runs locally.
   */
  gate: boolean;
  /** Ordering edges: ids that must succeed first. */
  needs?: string[];
  /** Mutual-exclusion groups: no two gates sharing a group overlap. */
  mutex?: string[];
  /**
   * Resources this gate READS but does not write. Paired with `mutex`, which
   * names what it WRITES; a `tree:<x>` in one may not overlap a `tree:<x>` in the
   * other concurrently.
   *
   * WHY THIS FIELD EXISTS AND WHY IT WAS MISSING. W2.4 declared isolation a
   * path-scoped contract and built BOTH readers -- `pool.ts` and the gate battery's
   * `classify_from_lock` (now `.ci/rediacc_ci/xdist_groups.py`'s) -- but the second claim it reads, `reads`, was never added
   * here. So the 21 scanner gate tests were UNDECLARABLE by construction, the lock
   * carried no `reads` key on any of 456 entries, and the battery ran on its loud
   * fallback ("no 'tree:' isolation declared ... falling back to the hand-maintained
   * W/S lists in this file") for the whole time the box read as done. A contract
   * implemented by two readers with no data to read is not a contract.
   */
  reads?: string[];
  /**
   * WHY this gate writes the real tree, in one sentence naming what it writes. Required beside an exclusive `tree:` claim in `mutex`, and refused without one: `check:ci-gate-tree-writes` enforces both directions on every lock entry, and requires the pair on any scheduled gate whose leaves (followed through imports and spawns) reach a proven tree write.
   *
   * THE PAIR IS THE WEAK FIX. The claim serialises this gate only against the other declared `tree:` claimants; the hundreds of scanners that read the tree declare nothing and still overlap it, and no claim helps with what a hard kill leaves behind. Writing to a temp copy is the real fix; this field is for the writers that cannot. Hand-only (`gen-manifest.ts` HAND_ONLY), because the claim it justifies lives here.
   */
  writesTree?: string;
  /**
   * ELASTIC WIDTH (agent/plans/PLAN-prepush-full-cpu.md part 1, operator ruling 2026-10-05: no static worker counts). A gate whose tool has a width knob declares the range here and passes `$CI_RUNNER_CORES` to that knob in its `run`; the pool grants a core count inside the range at the moment it admits the gate (pool.ts `elasticGrant`) and exports it to the gate's process. `min` is the floor below which parallelism is pointless, `max` a ceiling, `'all'` none. A gate with no knob declares nothing: the pool then budgets its measured cpu/wall, and still exports a grant, rounded, so a child tool sized by `granted_cores()` sees a number.
   *
   * It replaced `weight?: number`, a hand-typed slot count, which is refused on sight (`retiredFieldFindings` below): a weight said how wide a gate was believed to be, and the believed width was wrong in both directions (pytest fixed at 8 on a 24-core host, vitest gates budgeted at 2 while their tool took every core).
   */
  cores?: { min: number; max: number | 'all' };
  /** Memory-hungry (>=4 GB heap). Bounded by --heavy-limit. */
  heavy?: boolean;
  /**
   * Step-level `env:` for the emitted workflow step, declared in the gate header as
   * `env-<KEY>:` lines. `gen-gates-lock.ts` serialises the whole spec, so this reaches the
   * lock with no code change there -- which is the point of putting it HERE rather than
   * teaching a second file about it.
   *
   * WHY IT HAS TO BE DECLARED AT ALL: 17 registered steps carry `env:` in `ci-quality.yml`
   * and no lock entry records one, so a `gate-bind` rewrite that took ownership of such a
   * step would drop its env and report success. Measured receipt: strip `DOCKERHUB_TOKEN`
   * from `check:ci-docker-image-freshness` and the whole battery still runs green.
   */
  env?: Record<string, string>;
  /**
   * An extra condition ANDed onto the standard step guard, never replacing it.
   * `gate-bind.ts:emitStep` parenthesises it, so a `when` containing `||` cannot bind
   * looser than the `&&` and run the step on a failed setup. `steps.` is refused in the
   * header parser: a gate that can see step outcomes can contradict the guard, which is
   * invariant 11 re-opened through a side door.
   */
  when?: string;
  /** Repo-relative globs this gate validates; powers --changed. */
  paths?: string[];
  /**
   * Tracked directories whose LISTING this gate reads ('' is the root), not their content: each immediate tracked child enters the input hash as `list\t<dir>\t<child>\t<kind>` (scripts/ci-runner/input-hash.ts). A new, removed or renamed child moves the hash; an edit to a child does not. A gate declaring `lists` or `names` is not whole-tree even with no `paths`. Requires `pathsOrigin`, and each directory must hold a tracked file (`check:ci-paths-origin`).
   */
  lists?: string[];
  /**
   * Globs (the `paths` grammar) whose matching tracked NAMES this gate reads, not their bytes: each match enters the input hash as `name\t<mode>\t<path>`. The shape of a `git ls-files` scan. Requires `pathsOrigin`, and each glob must match a tracked file.
   */
  names?: string[];
  /**
   * Ref names (`HEAD`, `origin/main`) whose commit this gate's verdict depends on: each enters the input hash as `ref\t<name>\t<sha>`, and a ref resolving to nothing leaves the gate uncarriable (`ref-unresolved:<name>`). Does not scope the gate: a gate with only `refs` still reads the whole tree.
   */
  refs?: string[];
  /**
   * Required whenever `paths` is present; refused otherwise (cardinality
   * equality, both directions -- `check:ci-paths-origin`). `'declared'` means a
   * human enumerated the globs by hand, and each one is asserted to match at
   * least one tracked file -- a glob matching nothing is exactly as wrong as a
   * `paths` array with none, and just as invisible without this check.
   * `` `derived:${tool}` `` names an id (an npm script key, or another gate id)
   * that PRINTS the paths list, one per line, on a re-run; the check re-runs it
   * and asserts the output still equals the declared array, so a derivation
   * that has drifted from what it once produced is caught rather than trusted.
   * No entry uses `derived:` yet -- W2.5's tier 2 (traced paths) is separate,
   * later work -- so that branch is proven only by `--selftest`'s fixture.
   */
  pathsOrigin?: string;
  /**
   * Too expensive for the pre-push lane. ABSENT MEANS FAST, deliberately: a
   * new gate is enforced before a push until someone takes it out on purpose,
   * which is the fail-safe direction. Opting out is the one mechanism -- there
   * is no second exemption file -- so the reason lives in a comment beside it.
   *
   * The threshold is measured, not judged: `.ci/cache/gate-durations.json`
   * holds per-gate timings from real runs, and check:ci-gate-manifest's tier
   * oracle asserts this field against them in BOTH directions. (It named a
   * `check:ci-gate-tiers` until 2026-09-02; no such gate has ever existed, so
   * a reader looking for the guard found nothing and could conclude the field
   * was unasserted. The guard is real, it just lives in the manifest gate.) A gate marked slow that is in
   * fact cheap fails just as loudly as the converse, because the cheap-marked-
   * slow direction is the invisible one: the push stays fast and the coverage
   * quietly shrinks.
   */
  slow?: true;
  /**
   * CI-ONLY: never run by the local pre-push lane, even when the change set touches it, and so never recorded as `droppedTouched` for the push guard. CI still runs it in its own workflow step. The value is the reason, which must say why the gate cannot run reliably beside the rest of ci:quick and where CI runs it. Requires `slow`. Operator ruling 2026-10-06 (/ask) for check:test:tutorial-player.
   */
  ciOnly?: string;
  /** Leaf commands this gate ultimately executes. The parity oracle compares
   *  these, not the npm key, because CI frequently invokes the same underlying
   *  script under a different key or by bare path. */
  leaves: string[];
  /** How CI runs this gate. See section 6 for every variant and its rules. */
  ci: CiCoverage;
}

/**
 * Fields a spec may no longer carry, each with the replacement to name in the refusal. Clean break: there is no reading of a retired field, so a manifest still carrying one would be scheduled on a number the pool ignores.
 */
const RETIRED: Readonly<Record<string, string>> = {
  weight:
    "declare `cores: { min, max }` when the gate's tool has a width knob it is told through $CI_RUNNER_CORES, else nothing (the pool budgets its measured cpu/wall)",
};

/**
 * Every retired field and malformed `cores` range in a spec set, one sentence each naming the gate, the field and the fix. Empty when the set is clean. The runner refuses a manifest with any finding before it schedules anything (run.ts `main`), which is what makes the `weight` retirement a clean break for JSON manifests that no type checker reads.
 */
export function retiredFieldFindings(specs: readonly unknown[]): string[] {
  const out: string[] = [];
  for (const raw of specs) {
    if (raw === null || typeof raw !== 'object') continue;
    const spec = raw as Record<string, unknown>;
    const id = typeof spec.id === 'string' ? spec.id : '(no id)';
    for (const [field, fix] of Object.entries(RETIRED)) {
      if (field in spec) out.push(`${id}: \`${field}\` is retired; ${fix}`);
    }
    if (!('cores' in spec)) continue;
    const c = spec.cores as { min?: unknown; max?: unknown } | null;
    const min = c?.min;
    const max = c?.max;
    const minOk = typeof min === 'number' && Number.isInteger(min) && min >= 1;
    const maxOk = max === 'all' || (typeof max === 'number' && Number.isInteger(max) && max >= 1);
    if (!minOk || !maxOk) {
      out.push(
        `${id}: \`cores\` must be { min: <integer >= 1>, max: <integer >= 1> | 'all' }, got ${JSON.stringify(spec.cores)}`
      );
    } else if (typeof max === 'number' && max < (min as number)) {
      out.push(`${id}: \`cores.max\` ${max} is below \`cores.min\` ${min as number}`);
    }
  }
  return out;
}

export type CiCoverage =
  /** A workflow step runs it. Verified against the parsed workflow. */
  | { kind: 'step'; workflow: string; job: string; step: string }
  /** A gate test (a pytest module collected by check:ci-pytest) drives its REAL
   *  scan against the REAL tree. Requires `test` plus a BLOCKER reason naming
   *  the line that proves the real scan runs. Never inferred. */
  | { kind: 'test'; test: string; blocker: string }
  /** Deliberately local-only. Requires a BLOCKER reason. */
  | { kind: 'local-only'; blocker: string };

/**
 * THE HEADER HALF OF THE GRAMMAR: how a `---- gate ----` block (parsed below by `analyzeGateHeader`) becomes a `GateSpec`, so a gate declared ONLY by its header needs no package.json key, no hand-written manifest entry, no workflow step and no lock line (agent/plans/PLAN-tooling-code-reduction.md D2). `gen:gates --write` (scripts/gen/gen-manifest.ts) serialises these into the manifest's `gen-gates` region and then regenerates the lock, the workflow regions, the shard manifests and the doc regions from that one source.
 *
 *   header field            spec field
 *   `id:` (else derived)     id
 *   `run:` (else directRun)  run, executed as written: no `npm run` hop (directRun: scripts/gate-bind.ts)
 *   the file itself          leaves: [file]
 *   `slow: true`             slow
 *   `env-<KEY>:`             env
 *   `when:`                  when
 *   `kind:` + `step:`        ci: { kind: 'step', workflow, job, step } (`shared-step` rides a step it does not own)
 *   `kind: test` + `test:`   ci: { kind: 'test', test, blocker }
 *   `kind: local-only`       ci: { kind: 'local-only', blocker }
 *   `lane:` (else placed)    ci.job
 *
 * Hand-only fields (`paths`, `reads`, `heavy`, `mutex`, `writesTree`, `cores`, `ciOnly`, `noProfile`, `needs` ordering edges) have no header spelling on purpose: a gate needing one stays a hand entry in manifest.ts, which is the "overrides" half of D2.
 */

/** A header reduced to the fields the spec reads; `GateHeader` below satisfies it. */
export interface HeaderFields {
  kind: 'step' | 'shared-step' | 'test' | 'local-only';
  step?: string;
  /** The resolved run: the header's `run:`, else `directRun` in scripts/gate-bind.ts. Resolved by the caller so this module imports nothing: the runner loads it at run time, and its test fixtures copy a tree without scripts/lib. */
  run: string;
  selftest?: boolean;
  slow?: boolean;
  env?: Record<string, string>;
  when?: string;
  test?: string;
  blocker?: string;
}

/** The manifest's BLOCKER convention: the reason reads `BLOCKER: ...`, prefixed here when the header wrote the bare reason. */
const asBlocker = (raw: string): string => (raw.startsWith('BLOCKER:') ? raw : `BLOCKER: ${raw}`);

/**
 * The spec a header declares on its own. `id` is the resolved id (the header's `id:` or the derived one), `job` the lane placement resolved against the workflow, `workflow` the workflow file the step lives in.
 */
export function headerSpec(
  file: string,
  id: string,
  h: HeaderFields,
  job: string,
  workflow: string
): GateSpec {
  let ci: CiCoverage;
  if (h.kind === 'step' || h.kind === 'shared-step') {
    ci = { kind: 'step', workflow, job, step: h.step ?? '' };
  } else if (h.kind === 'test') {
    ci = { kind: 'test', test: h.test ?? '', blocker: asBlocker(h.blocker ?? '') };
  } else {
    ci = { kind: 'local-only', blocker: asBlocker(h.blocker ?? '') };
  }
  return {
    id,
    ...(h.env === undefined ? {} : { env: { ...h.env } }),
    run: h.run,
    ...(h.slow === true ? { slow: true as const } : {}),
    gate: true,
    leaves: [file],
    ...(h.when === undefined ? {} : { when: h.when }),
    ci,
  };
}
/**
 * The per-gate DECLARATION: a comment block in the gate script itself, from which its
 * package.json key, its manifest entry and its workflow step are derived.
 *
 * WHY IN THE SCRIPT. Today a new gate is registered in four places by hand, and each
 * place has a convention that only reveals itself as a red gate: a Python gate must be
 * the bare script path in package.json (a `python3` prefix makes check:ci-parity
 * resolve the leaves to `[python3]`), the manifest's `leaves` must equal what the npm
 * script resolves to AND be git-tracked, and the workflow step name must match
 * `ci.step` exactly. Worse, the JOB is a silent choice: check:ci-docker-npm-pins
 * landed in `quality-static`, which checks out no submodules, so the file it exists to
 * scan vanished from its enumeration and its correct exclusions were reported as dead
 * (CI job 100870135489). check_syncpack_sources.py has the identical scar.
 *
 * Every one of those is derivable from facts the gate already knows about itself. This
 * module reads them; `scripts/gate-bind.ts` emits from them.
 *
 * COMMENT-MARKER AGNOSTIC on purpose: the same block must work in a `#` script, a `//`
 * TypeScript file and a ` *` docstring, because the gates are written in all three.
 */

/**
 * WHAT A DECLARATION IS ALLOWED TO BE, v2.
 *
 * v1 required `step`, and that single requirement made 158 of the 409 registered gates
 * undeclarable rather than merely undeclared. Three shapes the manifest already records
 * have no step of their own to name:
 *
 *   - the 143 gate-tests, which ALL rode one hand-written battery step
 *     ("Quality-gate unit tests"; that step and its battery were retired on 2026-10-09).
 *     None owned it, so `--extract` correctly refused them one by one for a reason that
 *     was true and unfixable: `step "..." is shared by 143 entries; no one gate owns it`.
 *     The same shape survives in the gates that ride a composite step such as `i18n`;
 *   - the `ci.kind: 'test'` entries, whose CI coverage IS a named gate test (a pytest
 *     module under check:ci-pytest), and which carry a BLOCKER explaining why no lane can
 *     run them directly;
 *   - the 2 `ci.kind: 'local-only'` entries, which no CI step invokes at all.
 *
 * Demanding a step from those three forces the author to choose between lying (naming a
 * step it does not own, which the binder then tries to emit) and not declaring (which
 * leaves the gate hand-registered forever). `kind` is the third option, and it uses the
 * manifest's own vocabulary so `gates.lock.json` can be generated from headers without
 * inventing a translation.
 *
 * Only `step` emits a workflow step. The other three are the EXPLICIT NON-EMITTING
 * CLASS: still bound, still checked against package.json and the manifest, still
 * required to state their needs -- but never written into a gate-bind region.
 */
export type GateKind = 'step' | 'shared-step' | 'test' | 'local-only';

/** One gate's declaration. Everything except `step` has a convention default. */
export interface GateHeader {
  /** Which of the four shapes this is. Absent means `step`, which is 251 of 409. */
  kind: GateKind;
  /**
   * The workflow step name.
   *
   * Present for `step` (which OWNS it) and for `shared-step` (which RIDES it and must not
   * emit it). Absent for `test` and `local-only`, which have no step at all.
   */
  step?: string;
  /** Capabilities the gate needs from its lane: submodules, node, python, go, ruff. */
  needs: string[];
  /**
   * Capabilities `inferredNeeds` guessed that the gate does NOT have, each with a
   * reason. See `inferredNeeds` for why this exists and why it must carry a reason.
   */
  needsNot: string[];
  /** Override the id derived from the filename. */
  id?: string;
  /** Override the run command derived from the extension. */
  run?: string;
  /** Pin a lane. Still checked as a superset of `needs`. */
  lane?: string;
  /** Prefix the run with a `--selftest &&` leg. */
  selftest?: boolean;
  /** Mark it slow for the fast-lane tier. */
  slow?: boolean;
  /**
   * Step-level `env:`, one `env-<KEY>: <value>` line per key.
   *
   * ONE KEY PER LINE, not a comma list, because the values are GitHub expressions --
   * `${{ github.event.pull_request.number }}` -- and splitting a comma list correctly
   * would mean knowing when a comma is inside `${{ }}`. A grammar that needs a parser
   * to read one field is a grammar that will be read wrong.
   *
   * WHY THE HEADER AND NOT THE WORKFLOW. 17 registered steps carry `env:` in
   * `ci-quality.yml` today and no lock entry records one, so `gate-bind` emitting such a
   * step would drop its env and report a tidy `rewrote N region(s)`. Nothing reds: the
   * receipt is stripping `DOCKERHUB_TOKEN` from `check:ci-docker-image-freshness` and
   * running the whole battery green. Declaring env HERE puts it in the lock, which is
   * what makes the emitted step reproducible and the parity gate possible.
   */
  env?: Record<string, string>;
  /**
   * An extra condition ANDed onto the standard step guard. It never REPLACES it.
   *
   * A field that could replace the guard re-opens invariant 11 through a side door: the
   * standard `if:` is what keeps a gate from running when setup failed, and a gate that
   * could opt out of it could opt out of the whole ordering contract. So `when` is a
   * CONJUNCT, always, and `steps.` is refused inside it -- a step reference is exactly
   * the shape that would let a gate reach around setup and judge its own prerequisites.
   */
  when?: string;
  /** Free prose: why the gate exists. Emitted as the manifest entry's comment. */
  why?: string;
  /**
   * `emit: false` -- this gate OWNS its step and that step is hand-written. Verified
   * like any other, never written into a gate-bind region.
   *
   * Measured need, not a hypothetical: 18 gates in quality-code run BETWEEN the lane's
   * `Setup workspace` step and its `- id: setup` step, so their hand-written steps carry
   * no `steps.setup.outcome` guard and run whether setup succeeded or not. Emitting them
   * would move them below that guard, and the gates that would be silenced are the ones
   * that explain a broken setup: check-setup-idempotency.sh, check-toolchain-pins.sh,
   * check-host-toolchain-coverage.sh, check-hook-integrity.sh. A gate that only reports
   * when the thing it inspects already worked is worth less than no gate.
   *
   * Requires `blocker:`, for the same reason the stepless kinds do: without a stated
   * reason it is indistinguishable from a registration nobody finished.
   */
  emit?: boolean;
  /** For `kind: test`: the gate-test whose run IS this gate's CI coverage. */
  test?: string;
  /**
   * For `kind: test` and `kind: local-only`: why no lane runs this gate directly.
   *
   * Mandatory, and it is the same BLOCKER discipline the manifest already enforces on
   * those two kinds. A non-emitting gate with no stated reason is indistinguishable from
   * one whose registration was simply never finished.
   */
  blocker?: string;
}

const OPEN = /^\s*(?:#|\/\/|\*)?\s*-{2,}\s*gate\s*-{2,}\s*$/;
const CLOSE = /^\s*(?:#|\/\/|\*)?\s*-{2,}\s*end gate\s*-{2,}\s*$/;
const FIELD = /^\s*(?:#|\/\/|\*)?\s*([a-z][a-z-]*)\s*:\s*(.*?)\s*$/;
/** `env-<KEY>: <value>`. Uppercase by design: an env var that is not SHOUTY is a typo. */
const ENV_FIELD = /^\s*(?:#|\/\/|\*)?\s*env-([A-Z][A-Z0-9_]*)\s*:\s*(.*?)\s*$/;

/** Strip a trailing `# ...` note, which is prose about the value, not the value. */
const value = (raw: string): string => raw.replace(/\s+#\s.*$/, '').trim();

const KINDS: readonly GateKind[] = ['step', 'shared-step', 'test', 'local-only'];

/** A present block that does not yield a declaration, and the reason it does not. */
export interface HeaderProblem {
  error: string;
}

/**
 * The header block of one gate script: a declaration, a REASON it is not one, or null
 * when the file declares nothing at all.
 *
 * The three-way return is the whole point. v1 collapsed "no block" and "a malformed
 * block" into one `null`, so a gate whose header had a typo was INVISIBLE rather than
 * wrong: `gate-bind` skipped it, reported on the gates that did parse, and exited 0. A
 * declaration that absorbs its own failure is the vacuity shape this program exists to
 * refuse, so a block that opens must either declare or explain itself.
 *
 * A file with an OPEN and no CLOSE is an error rather than a silent skip for the same
 * reason it was never read to EOF: an unterminated block would swallow the rest of the
 * script as fields, and a declaration that absorbs its own source is worse than an
 * absent one.
 */
export function analyzeGateHeader(source: string): GateHeader | HeaderProblem | null {
  const lines = source.split('\n');
  const open = lines.findIndex((l) => OPEN.test(l));
  if (open === -1) return null;
  const close = lines.findIndex((l, i) => i > open && CLOSE.test(l));
  if (close === -1) {
    return {
      error:
        `a \`---- gate ----\` block opens at line ${open + 1} and never closes. The ` +
        'closing marker is `---- end gate ----`; `---- /gate ----` is not it, and has ' +
        'silently voided a declaration twice.',
    };
  }

  const fields = new Map<string, string>();
  const env = new Map<string, string>();
  for (const line of lines.slice(open + 1, close)) {
    // ENV FIRST. `FIELD` only accepts lowercase keys, so `env-GITHUB_TOKEN:` does not match it at all -- checking env first is what makes that a feature (a dedicated grammar) rather than an accident (a silently ignored line).
    const e = ENV_FIELD.exec(line);
    if (e) {
      env.set(e[1], value(e[2]));
      continue;
    }
    const m = FIELD.exec(line);
    if (m) fields.set(m[1], value(m[2]));
  }

  const rawKind = fields.get('kind') ?? 'step';
  if (!KINDS.includes(rawKind as GateKind)) {
    return { error: `kind: ${rawKind} is not one of ${KINDS.join(', ')}` };
  }
  const kind = rawKind as GateKind;

  const step = fields.get('step');
  const owns = kind === 'step' || kind === 'shared-step';
  if (owns && (step === undefined || step === '')) {
    return {
      error:
        `kind: ${kind} needs a \`step:\`` +
        (kind === 'shared-step' ? ' naming the shared step it rides' : ' naming the step it owns'),
    };
  }
  if (!owns && step !== undefined) {
    return {
      error: `kind: ${kind} has no workflow step, so \`step: ${step}\` cannot be true`,
    };
  }
  if (kind === 'test' && (fields.get('test') ?? '') === '') {
    return {
      error: 'kind: test needs `test:` naming the gate-test that runs it in CI',
    };
  }
  // `needs-not` REQUIRES a reason, for the same argument the BLOCKER convention makes everywhere else in this repo: an unexplained subtraction from a safety-side default is indistinguishable from a mistake, and this one subtracts from a capability claim whose failure mode is a gate dying on a clean runner.
  const needsNotRaw = (fields.get('needs-not') ?? '').trim();
  if (needsNotRaw !== '' && (fields.get('blocker') ?? '') === '') {
    return {
      error:
        'needs-not needs a `blocker:` saying WHY the inference is wrong for this file. ' +
        'inferredNeeds deliberately over-infers, because over-inferring only blocks a ' +
        'declaration while under-inferring kills the gate on a clean runner, so removing ' +
        'one of its guesses is a claim that has to be argued rather than asserted.',
    };
  }

  const emitField = fields.get('emit');
  if (emitField !== undefined && !/^(true|false|yes|no|1|0)$/i.test(emitField)) {
    return { error: `emit: ${emitField} is not a boolean` };
  }
  const emit = emitField === undefined ? true : /^(true|yes|1)$/i.test(emitField);
  if (!emit && kind !== 'step') {
    return { error: `emit: false is only meaningful for kind: step, not kind: ${kind}` };
  }
  if ((!owns || !emit) && (fields.get('blocker') ?? '') === '') {
    return {
      error:
        `${emit ? `kind: ${kind}` : 'emit: false'} needs \`blocker:\` stating why it is not ` +
        'emitted. Without one it is indistinguishable from a registration nobody finished.',
    };
  }

  // `when` IS A CONJUNCT AND MAY NOT REACH FOR A STEP. See the field's own comment: a `steps.` reference is how a gate would reach around the setup guard and judge its own prerequisites, which is invariant 11 re-opened through a side door.
  const when = fields.get('when');
  if (when?.includes('steps.')) {
    return {
      error:
        `when: ${when} references \`steps.\`. The standard guard already handles step ` +
        'outcomes; a `when` that can see them can contradict it, and ANDing a ' +
        'contradiction is how a gate stops running while still looking registered.',
    };
  }
  if (when !== undefined && when.trim() === '') {
    return { error: 'when: is empty. Omit the field rather than ANDing nothing.' };
  }
  // An env value that is empty is a variable set to the empty string, which is NOT the same as unset and has bitten this repo before through toolchain_pin_for returning "".
  for (const [k, v] of env) {
    if (v.trim() === '') {
      return {
        error:
          `env-${k}: is empty. An empty value SETS the variable to "", which a reader ` +
          'cannot tell from a deliberate blank; omit the line to leave it unset.',
      };
    }
  }

  const bool = (k: string): boolean | undefined =>
    fields.has(k) ? /^(true|yes|1)$/i.test(fields.get(k) ?? '') : undefined;

  return {
    kind,
    ...(owns ? { step: step as string } : {}),
    needsNot: (fields.get('needs-not') ?? '')
      .split(',')
      .map((x) => x.trim())
      .filter((x) => x !== '' && x !== 'none'),
    needs: (fields.get('needs') ?? '')
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s !== '' && s !== 'none'),
    ...(fields.has('id') ? { id: fields.get('id') } : {}),
    ...(fields.has('run') ? { run: fields.get('run') } : {}),
    ...(fields.has('lane') ? { lane: fields.get('lane') } : {}),
    ...(bool('selftest') === undefined ? {} : { selftest: bool('selftest') }),
    ...(bool('slow') === undefined ? {} : { slow: bool('slow') }),
    ...(env.size > 0
      ? {
          env: Object.fromEntries(
            [...env].sort((a, b) => Number(String(a) > String(b)) - Number(String(a) < String(b)))
          ),
        }
      : {}),
    ...(when === undefined ? {} : { when }),
    ...(fields.has('why') ? { why: fields.get('why') } : {}),
    ...(emit ? {} : { emit: false }),
    ...(fields.has('test') ? { test: fields.get('test') } : {}),
    ...(fields.has('blocker') ? { blocker: fields.get('blocker') } : {}),
  };
}

/** The declaration, or null for both "no block" and "a block that does not parse". */
export function parseGateHeader(source: string): GateHeader | null {
  const r = analyzeGateHeader(source);
  return r === null || 'error' in r ? null : r;
}

/**
 * Why a present block yielded no declaration, or null when there is nothing to explain.
 *
 * `gate-bind` calls this for every file `parseGateHeader` skipped, which is what turns a
 * typo from invisible into a named binding problem.
 */
export function headerError(source: string): string | null {
  const r = analyzeGateHeader(source);
  return r !== null && 'error' in r ? r.error : null;
}

/**
 * The gate id a path implies. 308 of 378 current ids already follow this, which is why
 * `id:` is an override rather than a required field.
 */
export function derivedId(repoPath: string): string {
  const base = (repoPath.split('/').pop() ?? '').replace(/\.(py|sh|ts|cjs|mjs)$/, '');
  // There is no test-battery arm: the bash battery under `.ci/scripts/test/gates/` is gone and its pytest ports carry no gate header, so every derivable id is a `check:ci-` one.
  return `check:ci-${base.replace(/^check[-_]/, '').replace(/_/g, '-')}`;
}

/**
 * The run command a path implies.
 *
 * A module under `.ci/rediacc_ci` never reaches here: gate-bind's `directRun` gives it
 * `PYTHONPATH=.ci python3 -m <module>`, which the parity resolver reads as the module's file.
 * THE BARE PATH FOR .py AND .sh IS NOT COSMETIC: the parity leg of check:ci-gen-gates compares the manifest's
 * `leaves` against what the npm script resolves to, and writing `python3 <path>` makes
 * that resolve to `[python3]` and fail. Deriving it removes the whole class.
 */
export function derivedRun(repoPath: string, selftest = false): string {
  if (repoPath.endsWith('.ts')) {
    return selftest ? `tsx ${repoPath} --selftest && tsx ${repoPath}` : `tsx ${repoPath}`;
  }
  return repoPath;
}

/**
 * Strip PROSE: `#` and `//` line comments, `/* *\/` blocks, and Python docstrings.
 *
 * A comment is not code, and this helper read it as code. check_allowlist_key_matching.py
 * mentions `private/account/Dockerfile` in its docstring to explain the defect it gates;
 * nothing in it reads that file, yet the mention alone inferred a `submodules` need and
 * pushed the gate out of the slim lane into quality-code. scripts/ci-runner/lanes.ts:91
 * carries a note about the identical bug, found the identical way -- which is the whole
 * argument for fixing it HERE rather than rewording one docstring.
 *
 * A gate that genuinely needs a submodule but only says so in prose declares it in its
 * header's `needs:`, which is what that field is for.
 */
function stripProse(source: string): string {
  return source
    .replace(/("""|''')[\s\S]*?\1/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:'"\\])\/\/.*$/gm, '$1')
    .replace(/(^|\s)#.*$/gm, '$1');
}

/**
 * Capabilities a gate needs, inferred from its own source, so an author who forgets to
 * declare one is told rather than finding out from a job that lacks it.
 *
 * `--recurse-submodules` is here because it is the exact shape that shipped twice: a
 * gate enumerating with it, placed in a lane with no submodules, silently loses the
 * files it exists to judge.
 *
 * Returns each inferred need once (`submodules`, `python-yaml`, `node`, `go`), sorted in descending code-unit order.
 */
export function inferredNeeds(rawSource: string): string[] {
  const source = stripProse(rawSource);
  const out = new Set<string>();
  // `--recurse-submodules=no` (and `--no-recurse-submodules`) says the OPPOSITE: check_plan_implementation's prefetch fetches with it so a submodule is never touched, and the bare match inferred a `submodules` need from it (2026-10-03).
  if (/--recurse-submodules(?!=no\b)|private\/(renet|account|elite|homebrew-tap)\//.test(source)) {
    out.add('submodules');
  }
  if (/^\s*import\s+yaml\b|\byaml\.safe_load\b/m.test(source)) out.add('python-yaml');
  // `\bnode\b` alone matched the Python AST variable `node` in check_allowlist_key_matching.py and inferred a node runtime for a pure-Python gate. A RUNTIME need is an invocation or an ES import, never a bare identifier. ...and `node\s+[\w./]` then matched `for node in ast.walk(tree)`. A runtime need means node in COMMAND position: line start, or after a shell operator.
  if (
    /\bnpx\s|\btsx\s|(?:^|[|&;(]|\$\()\s*node\s+[\w./]|require\(|^\s*import .* from ['"]/m.test(
      source
    )
  ) {
    out.add('node');
  }
  if (/\bgo\s+(build|vet|test)\b/.test(source)) out.add('go');
  return [...out].sort((a, b) => Number(a > b) - Number(a < b));
}
