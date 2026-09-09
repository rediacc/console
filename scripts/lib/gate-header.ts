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
 *   - the 143 gate-tests, which ALL ride one hand-written battery step
 *     ("Quality-gate unit tests" in quality-security, ci-quality.yml:2191). None owns it,
 *     so `--extract` correctly refuses them one by one for a reason that is true and
 *     unfixable: `step "..." is shared by 143 entries; no one gate owns it`;
 *   - the 13 `ci.kind: 'test'` entries, whose CI coverage IS a named gate-test riding
 *     that same battery, and which carry a BLOCKER explaining why no lane can run them
 *     directly;
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
export type GateKind = 'step' | 'battery' | 'test' | 'local-only';

/** One gate's declaration. Everything except `step` has a convention default. */
export interface GateHeader {
  /** Which of the four shapes this is. Absent means `step`, which is 251 of 409. */
  kind: GateKind;
  /**
   * The workflow step name.
   *
   * Present for `step` (which OWNS it) and for `battery` (which RIDES it and must not
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

const KINDS: readonly GateKind[] = ['step', 'battery', 'test', 'local-only'];

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
    // ENV FIRST. `FIELD` only accepts lowercase keys, so `env-GITHUB_TOKEN:` does not
    // match it at all -- checking env first is what makes that a feature (a dedicated
    // grammar) rather than an accident (a silently ignored line).
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
  const owns = kind === 'step' || kind === 'battery';
  if (owns && (step === undefined || step === '')) {
    return {
      error:
        `kind: ${kind} needs a \`step:\`` +
        (kind === 'battery' ? ' naming the shared step it rides' : ' naming the step it owns'),
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
  // `needs-not` REQUIRES a reason, for the same argument the BLOCKER convention makes
  // everywhere else in this repo: an unexplained subtraction from a safety-side default
  // is indistinguishable from a mistake, and this one subtracts from a capability claim
  // whose failure mode is a gate dying on a clean runner.
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

  // `when` IS A CONJUNCT AND MAY NOT REACH FOR A STEP. See the field's own comment: a
  // `steps.` reference is how a gate would reach around the setup guard and judge its own
  // prerequisites, which is invariant 11 re-opened through a side door.
  const when = fields.get('when');
  if (when !== undefined && when.includes('steps.')) {
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
  // An env value that is empty is a variable set to the empty string, which is NOT the
  // same as unset and has bitten this repo before through toolchain_pin_for returning "".
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
    ...(env.size > 0 ? { env: Object.fromEntries([...env].sort()) } : {}),
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
  // BOTH ARMS NORMALISE `_` TO `-`, and until 2026-09-08 only the second did.
  // The prefix strip has been `[-_]`-tolerant on both lines for a while, which
  // made the missing normalisation on the gate-test arm read as deliberate. It
  // was not: every one of the 149 `id: 'gate-test:...'` entries in
  // scripts/ci-runner/manifest.ts is hyphenated, so a ported `test_gate_lanes.py`
  // would have derived `gate-test:gate_lanes` and matched none of them.
  // LATENT RATHER THAN LIVE TODAY, stated so nobody reads this as a bug that was
  // biting: `.ci/scripts/test/gates/` holds 149 files and 0 `.py`, and the pytest
  // ports live under `.ci/rediacc_ci/tests/gates/` -- note the `s` -- which this
  // branch does not match and which carries no gate header anyway. It fires on
  // the first battery test ported IN PLACE.
  if (repoPath.includes('/test/gates/'))
    return `gate-test:${base.replace(/^test[-_]/, '').replace(/_/g, '-')}`;
  return `check:ci-${base.replace(/^check[-_]/, '').replace(/_/g, '-')}`;
}

/**
 * The run command a path implies.
 *
 * THE BARE PATH FOR .py AND .sh IS NOT COSMETIC: check:ci-parity compares the manifest's
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
 * Capabilities a gate needs, inferred from its own source, so an author who forgets to
 * declare one is told rather than finding out from a job that lacks it.
 *
 * `--recurse-submodules` is here because it is the exact shape that shipped twice: a
 * gate enumerating with it, placed in a lane with no submodules, silently loses the
 * files it exists to judge.
 */
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

export function inferredNeeds(rawSource: string): string[] {
  const source = stripProse(rawSource);
  const out = new Set<string>();
  if (/--recurse-submodules|private\/(renet|account|elite|homebrew-tap)\//.test(source)) {
    out.add('submodules');
  }
  if (/^\s*import\s+yaml\b|\byaml\.safe_load\b/m.test(source)) out.add('python-yaml');
  // `\bnode\b` alone matched the Python AST variable `node` in
  // check_allowlist_key_matching.py and inferred a node runtime for a pure-Python gate.
  // A RUNTIME need is an invocation or an ES import, never a bare identifier.
  // ...and `node\s+[\w./]` then matched `for node in ast.walk(tree)`. A runtime need
  // means node in COMMAND position: line start, or after a shell operator.
  if (
    /\bnpx\s|\btsx\s|(?:^|[|&;(]|\$\()\s*node\s+[\w./]|require\(|^\s*import .* from ['"]/m.test(
      source
    )
  ) {
    out.add('node');
  }
  if (/\bgo\s+(build|vet|test)\b/.test(source)) out.add('go');
  return [...out].sort();
}
