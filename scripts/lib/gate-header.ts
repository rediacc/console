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

/** One gate's declaration. Everything except `step` has a convention default. */
export interface GateHeader {
  /** The workflow step name. The only field with no sensible default. */
  step: string;
  /** Capabilities the gate needs from its lane: submodules, node, python, go, ruff. */
  needs: string[];
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
  /** Free prose: why the gate exists. Emitted as the manifest entry's comment. */
  why?: string;
}

const OPEN = /^\s*(?:#|\/\/|\*)?\s*-{2,}\s*gate\s*-{2,}\s*$/;
const CLOSE = /^\s*(?:#|\/\/|\*)?\s*-{2,}\s*end gate\s*-{2,}\s*$/;
const FIELD = /^\s*(?:#|\/\/|\*)?\s*([a-z][a-z-]*)\s*:\s*(.*?)\s*$/;

/** Strip a trailing `# ...` note, which is prose about the value, not the value. */
const value = (raw: string): string => raw.replace(/\s+#\s.*$/, '').trim();

/**
 * The header block of one gate script, or null when it declares none.
 *
 * A file with an OPEN and no CLOSE returns null rather than reading to EOF: an
 * unterminated block would silently swallow the rest of the script as fields, and a
 * declaration that absorbs its own source is worse than an absent one.
 */
export function parseGateHeader(source: string): GateHeader | null {
  const lines = source.split('\n');
  const open = lines.findIndex((l) => OPEN.test(l));
  if (open === -1) return null;
  const close = lines.findIndex((l, i) => i > open && CLOSE.test(l));
  if (close === -1) return null;

  const fields = new Map<string, string>();
  for (const line of lines.slice(open + 1, close)) {
    const m = FIELD.exec(line);
    if (m) fields.set(m[1], value(m[2]));
  }
  const step = fields.get('step');
  if (step === undefined || step === '') return null;

  const bool = (k: string): boolean | undefined =>
    fields.has(k) ? /^(true|yes|1)$/i.test(fields.get(k) ?? '') : undefined;

  return {
    step,
    needs: (fields.get('needs') ?? '')
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s !== '' && s !== 'none'),
    ...(fields.has('id') ? { id: fields.get('id') } : {}),
    ...(fields.has('run') ? { run: fields.get('run') } : {}),
    ...(fields.has('lane') ? { lane: fields.get('lane') } : {}),
    ...(bool('selftest') === undefined ? {} : { selftest: bool('selftest') }),
    ...(bool('slow') === undefined ? {} : { slow: bool('slow') }),
    ...(fields.has('why') ? { why: fields.get('why') } : {}),
  };
}

/**
 * The gate id a path implies. 308 of 378 current ids already follow this, which is why
 * `id:` is an override rather than a required field.
 */
export function derivedId(repoPath: string): string {
  const base = (repoPath.split('/').pop() ?? '').replace(/\.(py|sh|ts|cjs|mjs)$/, '');
  if (repoPath.includes('/test/gates/')) return `gate-test:${base.replace(/^test[-_]/, '')}`;
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
export function stripProse(source: string): string {
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
