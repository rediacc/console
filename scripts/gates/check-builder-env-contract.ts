/**
 * check:ci-builder-env-contract -- the env names a workflow step EXPORTS must
 * be exactly the names the deploy builder it invokes READS.
 *
 * THE DEFECT CLASS. Three CI builders marshal a `wrangler secret bulk` payload
 * out of environment variables:
 *
 *   .ci/rediacc_ci/deploy/set_account_worker_secrets.py   (cd-deploy-account.yml)
 *   .ci/rediacc_ci/deploy/set_www_worker_secrets.py       (cd-deploy-worker.yml)
 *   .ci/rediacc_ci/deploy/set_preview_worker_secrets.py   (ci.yml)
 *
 * and exactly one place decides what those variables are called on the way in:
 * the `env:` block of the workflow step whose `run:` invokes the builder. The
 * two sides are joined by NOTHING but a matching string.
 *
 * THE BUILDERS ARE PYTHON. The workflow steps invoke the module:
 *
 *      run: PYTHONPATH=.ci python3 -m rediacc_ci.deploy.set_account_worker_secrets
 *
 * so a step is found by EITHER spelling: the builder's file path, or `-m`
 * followed by the module the path maps to (`.ci/rediacc_ci/<pkg>/<name>.py` ->
 * `rediacc_ci.<pkg>.<name>`). The bash twins are deleted; the READ side is parsed
 * out of the port itself: a literal `os.environ.get("NAME"` or `env.get("NAME"`
 * call is a read, and so is the first column of a two-column `KEYS` row (the
 * www and preview ports copy `os.environ` wholesale and index it by that column).
 * A builder file that is missing is a refusal, not a pass on nothing.
 *
 * On 2026-09-02 the `SECRET_*` / `VAR_*` translation shim was deleted from all
 * three builders, so each now reads the full Worker name directly
 * (`ACCOUNT_JWT_SECRET`, `CLOUDFLARE_TURNSTILE_SECRET_KEY`, ...). The workflows
 * kept exporting the OLD names for a while, and nothing anywhere noticed:
 *
 *   check:ci-worker-secret-names  proves the builder's OUTPUT keys exist in
 *                                 private/account/src/types/env.ts
 *   check:ci-workflow-gates       proves a reusable workflow's `secrets:`
 *                                 contract matches its `secrets.X` reads
 *   check-workflows.sh            proves an env VALUE is not an unexpanded
 *                                 `$IDENT`
 *
 * None of them compares the workflow's exported env NAMES against the names
 * the builder reads. A rename on either side is silent at author time, silent
 * at lint time, and silent in the job log: the port reads the missing name as the
 * empty string, and the builder's `REQUIRED_NONEMPTY` guard (or, worse, no guard
 * at all for an optional key) fires at DEPLOY time, in production, on whichever
 * region deploys first.
 *
 * WHAT IS CHECKED, per (workflow step, builder) pair:
 *   1. every name the builder READS from the environment is EXPORTED by the
 *      step -- the "ships an empty value" direction;
 *   2. every name the step EXPORTS is READ by the builder -- the OTHER half of
 *      the same defect, a leftover export nobody consumes after a rename;
 *   3. every name in a `REQUIRED_NONEMPTY` guard tuple is a name the port
 *      actually reads (or a fan-in prefix), so a half-renamed guard cannot
 *      refuse on a variable nothing supplies.
 *
 * THE FAN-INS. set_account_worker_secrets.py does not read its regional
 * credentials by literal name; it builds the name from the `SUFFIXED_PREFIXES`
 * tuple and looks it up:
 *
 *      name = "%s_%s" % (prefix, suffix)    # AWS_SES_ACCESS_KEY_ID_EU, ...
 *
 * A find-and-replace cannot see those names and neither can a naive scanner,
 * which is exactly why they are worth checking. This gate resolves them by
 * expanding SUFFIX over the three real regions (EU / US / ASIA, the values
 * `matrix.secretSuffix` takes in cd-deploy-account.yml), so all three regional
 * spellings must be exported.
 *
 * NOT CHECKED, and said out loud rather than left to be discovered:
 *   - .ci/rediacc_ci/ops/deploy_bench.py also builds a secret payload, but it reads
 *     the `deploy-bench` Bitwarden profile rather than a workflow `env:` block. That
 *     is a different contract with a different oracle; this gate does not look at
 *     it, and its names are covered by check:ci-worker-secret-names. (run.sh was named here
 *     too until commit dd5dfba3c deleted its `pr` verb and the payload with it.)
 *   - VALUES. A name exported as `${{ secrets.TYPO }}` is present and empty.
 *     That is the builders' `REQUIRED_NONEMPTY` guards and check_bws_map.py.
 *   - names read by an imported library (`rediacc_ci.core.common`) rather than
 *     by the builder itself. Only the builder file is parsed.
 *
 * Run: npx tsx scripts/gates/check-builder-env-contract.ts
 *
 * Control-first: both extractors are proven on synthetic input, in BOTH
 * directions, before any verdict; every pair carries floors on exports, reads
 * and fan-ins so a broken regex reads as a refusal rather than as "nothing to
 * check"; a missing workflow, a missing builder, an unfindable step or an
 * empty env block all REFUSE rather than pass; and every allowlist entry must
 * fire at least once or the gate fails on the dead exemption.
 *
 * ---- gate ----
 * step: Builder env contract
 * needs: node
 * ---- end gate ----
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..', '..');

/** The values `matrix.secretSuffix` takes in cd-deploy-account.yml. */
const REGION_SUFFIXES = ['EU', 'US', 'ASIA'];
/** The two channels a region-and-channel fan-in (`<PREFIX>_<SUFFIX>_<CHANNEL>`) expands over. */
const CHANNEL_SUFFIXES = ['STABLE', 'EDGE'];

interface Pair {
  workflow: string;
  builder: string;
  /** Fewest env names the step is known to export. Below it, refuse. */
  exportFloor: number;
  /** Fewest environment names the builder is known to read. Below it, refuse. */
  readFloor: number;
  /** Fewest `${!var}` fan-ins the builder is known to use. */
  fanInFloor: number;
  /** Fewest `SUFFIXED_CHANNEL_PREFIXES` region-and-channel fan-ins the builder is known to use. */
  channelFanInFloor: number;
}

/**
 * Measured 2026-09-02: 44/32/4, 27/25/0, 17/16/0 (exports / direct reads /
 * fan-ins). The floors sit under those, far enough to survive an honest edit
 * and close enough that a lost payload is a refusal, not a pass.
 *
 * Region-and-channel fan-ins (`SUFFIXED_CHANNEL_PREFIXES`), counted when channelFanInFloor was
 * added: 1/0/0, one prefix (`ACCOUNT_CONFIG_SERVER_KEY`) in the account builder and none in the
 * other two.
 */
const PAIRS: Pair[] = [
  {
    workflow: '.github/workflows/cd-deploy-account.yml',
    builder: '.ci/rediacc_ci/deploy/set_account_worker_secrets.py',
    exportFloor: 35,
    readFloor: 25,
    fanInFloor: 4,
    channelFanInFloor: 1,
  },
  {
    workflow: '.github/workflows/cd-deploy-worker.yml',
    builder: '.ci/rediacc_ci/deploy/set_www_worker_secrets.py',
    exportFloor: 20,
    readFloor: 20,
    fanInFloor: 0,
    channelFanInFloor: 0,
  },
  {
    workflow: '.github/workflows/ci.yml',
    builder: '.ci/rediacc_ci/deploy/set_preview_worker_secrets.py',
    exportFloor: 12,
    readFloor: 12,
    fanInFloor: 0,
    channelFanInFloor: 0,
  },
];

/**
 * The ONLY names allowed to sit on one side of a contract and not the other,
 * each with the reason it is genuinely not a finding.
 *
 * This list is LIVENESS-CHECKED: an entry that never fires in a run is a dead
 * exemption and fails the gate, so it cannot quietly become a way to pass.
 * `direction` pins WHICH half is being excused, so an entry excusing a missing
 * export cannot also start excusing a missing read.
 *
 * Names the original design named but that are NOT here -- TARGET, SUFFIX,
 * WORKER_NAME, BACKUP_BUCKET_STABLE, BACKUP_BUCKET_EDGE, R2_JURISDICTION --
 * are absent on purpose: every one of them is BOTH exported by its step and
 * read by its builder, so an exemption for them would excuse nothing and would
 * be exactly the dead entry the liveness check exists to remove.
 */
interface Exemption {
  name: string;
  direction: 'exported-not-read' | 'read-not-exported';
  reason: string;
}

const EXEMPT: Exemption[] = [
  {
    name: 'CLOUDFLARE_API_TOKEN',
    direction: 'exported-not-read',
    reason:
      'BLOCKER: consumed by `npx wrangler` out of the environment, never by the builder script itself. Dropping it breaks auth, so it must stay exported.',
  },
  {
    name: 'CLOUDFLARE_ACCOUNT_ID',
    direction: 'exported-not-read',
    reason: 'BLOCKER: same as CLOUDFLARE_API_TOKEN -- wrangler reads it, the builder does not.',
  },
  {
    name: 'PR_NUMBER',
    direction: 'read-not-exported',
    reason:
      'BLOCKER: set as JOB-level env on deploy-preview in ci.yml (one definition serving ~8 steps), not repeated in the step env block. This gate parses the STEP block only.',
  },
];

// ── Extractors, exported so a selftest can drive them directly ─────────────

/** A literal-name read of the environment: `os.environ.get("NAME"` or `env.get("NAME"`, the call possibly wrapped onto the next line. */
const ENV_GET_RE = /\b(?:os\.environ|env)\.get\(\s*"([A-Z][A-Z0-9_]*)"/g;
/** A two-column `KEYS` row, `("NAME", "jq_var"),`: the env name and the Worker key are one spelling. */
const KEYS_ROW_2COL = /^\s+\("([A-Z][A-Z0-9_]*)",\s*"[a-z][a-z0-9_]*"\),?\s*$/;
/** One quoted UPPERCASE entry of a name tuple, `    "NAME",`. */
const NAME_ENTRY = /^\s+"([A-Z][A-Z0-9_]*)",?\s*$/;

/**
 * The lines (0-based index, text) of the module-level tuple `NAME = (` ... `)`,
 * and nothing around it. The close is the first column-0 `)` after the opening,
 * which is how ruff formats every tuple in these ports. Missing tuple: empty.
 */
function tupleLines(text: string, name: string): { line: number; text: string }[] {
  const lines = text.split('\n');
  const open = lines.findIndex((l) => new RegExp(`^${name}\\b[^\\n]*=\\s*\\($`).test(l));
  if (open < 0) return [];
  const out: { line: number; text: string }[] = [];
  for (let i = open + 1; i < lines.length && lines[i] !== ')'; i++) {
    out.push({ line: i, text: lines[i] });
  }
  return out;
}

/**
 * Environment names a builder reads, mapped to the 1-based line of the first
 * read. A whole-line comment never counts, so a name mentioned in prose is not a
 * read; a call on a non-environment mapping (`values.get("X"`) is not matched.
 */
export function builderReads(source: string): Map<string, number> {
  // Triple-quoted strings (module and function docstrings) are prose: blank them, keeping every newline so line numbers stay true.
  const text = source.replace(/"""[\s\S]*?"""/g, (block) => block.replace(/[^\n]/g, ' '));
  const out = new Map<string, number>();
  const lineOf = (offset: number) => text.slice(0, offset).split('\n').length;
  const lines = text.split('\n');
  for (const m of text.matchAll(ENV_GET_RE)) {
    const line = lineOf(m.index ?? 0);
    if (/^\s*#/.test(lines[line - 1])) continue;
    if (!out.has(m[1])) out.set(m[1], line);
  }
  for (const { line, text: row } of tupleLines(text, 'KEYS')) {
    const m = KEYS_ROW_2COL.exec(row);
    if (m && !out.has(m[1])) out.set(m[1], line + 1);
  }
  return out;
}

/**
 * Region fan-ins, resolved. The port holds the prefixes in `SUFFIXED_PREFIXES`
 * and builds `<PREFIX>_<SUFFIX>`; expanding SUFFIX over the real regions gives the
 * names the workflow step must export. Returns the constructed names with the line
 * of their prefix, plus the raw templates so a caller can report them.
 */
export function builderFanIns(text: string): {
  names: Map<string, number>;
  templates: string[];
} {
  const names = new Map<string, number>();
  const templates: string[] = [];
  for (const { line, text: row } of tupleLines(text, 'SUFFIXED_PREFIXES')) {
    const m = NAME_ENTRY.exec(row);
    if (!m) continue;
    templates.push(`${m[1]}_\${SUFFIX}`);
    for (const suffix of REGION_SUFFIXES) names.set(`${m[1]}_${suffix}`, line + 1);
  }
  return { names, templates };
}

/**
 * Region-and-channel fan-ins, resolved. The port holds the prefixes in
 * `SUFFIXED_CHANNEL_PREFIXES` and builds `<PREFIX>_<SUFFIX>_<STABLE|EDGE>` (the
 * config server key since dce7b1183, one vault entry per region and channel).
 * Expanding over the real regions and both channels gives the names the workflow
 * step must export. The tuple is read in either layout ruff leaves it in: one
 * entry per line, or a one-line `= ("A",)` for a single entry.
 */
export function builderChannelFanIns(text: string): {
  names: Map<string, number>;
  prefixes: string[];
} {
  const names = new Map<string, number>();
  const prefixes: string[] = [];
  const lines = text.split('\n');
  const add = (prefix: string, line: number) => {
    prefixes.push(prefix);
    for (const suffix of REGION_SUFFIXES) {
      for (const channel of CHANNEL_SUFFIXES) names.set(`${prefix}_${suffix}_${channel}`, line);
    }
  };
  const oneLine = lines.findIndex((l) =>
    /^SUFFIXED_CHANNEL_PREFIXES\b[^\n]*=\s*\(.*\)\s*$/.test(l)
  );
  if (oneLine >= 0) {
    const body = lines[oneLine].slice(lines[oneLine].indexOf('('));
    for (const m of body.matchAll(/"([A-Z][A-Z0-9_]*)"/g)) add(m[1], oneLine + 1);
    return { names, prefixes };
  }
  for (const { line, text: row } of tupleLines(text, 'SUFFIXED_CHANNEL_PREFIXES')) {
    const m = NAME_ENTRY.exec(row);
    if (m) add(m[1], line + 1);
  }
  return { names, prefixes };
}

/**
 * The names in the `REQUIRED_NONEMPTY` and `REQUIRED_NONEMPTY_STABLE` guard
 * tuples, with the line. `varName` is the name itself when the port reads it from
 * the environment, `null` for a fan-in prefix (its value comes from the constructed
 * name, so the label is the Worker key rather than an env name) and for a channel
 * fan-in (`<NAME>_STABLE` and `<NAME>_EDGE` both read), and `(unread)` for
 * a guard on a name the port never reads: that guard could only ever fire, or never.
 */
export function guardLabels(
  text: string,
  reads: Map<string, number>,
  fanInPrefixes: Set<string>
): { label: string; varName: string | null; line: number }[] {
  const out: { label: string; varName: string | null; line: number }[] = [];
  for (const tuple of ['REQUIRED_NONEMPTY', 'REQUIRED_NONEMPTY_STABLE']) {
    for (const { line, text: row } of tupleLines(text, tuple)) {
      const m = NAME_ENTRY.exec(row);
      if (!m) continue;
      const name = m[1];
      // A channel fan-in reads `<NAME>_STABLE` and `<NAME>_EDGE` and guards the chosen value under the Worker key, as a region fan-in does.
      const channelFanIn = reads.has(`${name}_STABLE`) && reads.has(`${name}_EDGE`);
      const varName =
        fanInPrefixes.has(name) || channelFanIn ? null : reads.has(name) ? name : '(unread)';
      out.push({ label: name, varName, line: line + 1 });
    }
  }
  return out;
}

export interface StepEnv {
  stepName: string;
  stepLine: number;
  names: Map<string, number>;
  /** Which spelling of the builder the step's `run:` actually used. */
  invokedAs: 'path' | 'python-module';
}

/**
 * The python module a `.ci/rediacc_ci/<pkg>/<name>.py` builder is run as, by the
 * one rule the ports follow: the directory under `.ci/` is the package and the
 * basename is the module. `null` for any path that does not have that shape, so a
 * builder living somewhere else is matched by path only.
 */
export function pythonPortModule(builder: string): string | null {
  const m = /^\.ci\/(rediacc_ci\/[a-z][a-z0-9_]*)\/([a-z0-9][a-z0-9_]*)\.py$/.exec(builder);
  if (!m) return null;
  return `${m[1].replace(/\//g, '.')}.${m[2]}`;
}

/**
 * Does this `run:` scalar invoke `builder`, by either spelling?
 *
 * The module form demands a real `-m <module>` invocation and a boundary after
 * it, so neither a prose mention nor a LONGER module name
 * (`...set_account_worker_secrets_v2`) can claim the step. The step this gate
 * finds decides which env block it reads; a loose match would read a
 * neighbour's.
 */
export function runInvokesBuilder(runScalar: string, builder: string): StepEnv['invokedAs'] | null {
  if (runScalar.includes(builder)) return 'path';
  const mod = pythonPortModule(builder);
  if (mod === null) return null;
  const re = new RegExp(`(?:^|\\s)-m\\s+${mod.replace(/\./g, '\\.')}(?![\\w.])`);
  return re.test(runScalar) ? 'python-module' : null;
}

/**
 * The `env:` block of the step whose `run:` invokes `builder`.
 *
 * A hand parser on the YAML SHAPE, the way .ci/scripts/quality/check_bws_map.py
 * does it: pulling in a YAML dependency for a fixed shape only adds a way for
 * this gate to go stale. Ambiguity is a refusal, never a guess -- if the block
 * we carve out holds more than one step-level `run:` or `env:`, the split is
 * wrong and `null` comes back rather than a set of names from a neighbour.
 */
export function stepEnvNames(yamlText: string, builder: string): StepEnv | null {
  const lines = yamlText.split('\n');
  const starts: number[] = [];
  lines.forEach((l, i) => {
    if (
      /^\s*-\s+(name|uses|id|run|env|if|with|shell|working-directory|continue-on-error|timeout-minutes):/.test(
        l
      )
    ) {
      starts.push(i);
    }
  });
  for (let s = 0; s < starts.length; s++) {
    const from = starts[s];
    const to = s + 1 < starts.length ? starts[s + 1] : lines.length;
    const block = lines.slice(from, to);
    const runIdx = block.findIndex((l) => /^\s*run:/.test(l));
    if (runIdx < 0) continue;
    const keyIndent = block[runIdx].length - block[runIdx].trimStart().length;
    // The builder must appear in the `run:` SCALAR (its line plus any more- indented continuation), never merely somewhere in the step: a comment naming the builder must not claim the step.
    let runEnd = runIdx + 1;
    while (
      runEnd < block.length &&
      (block[runEnd].trim() === '' ||
        block[runEnd].length - block[runEnd].trimStart().length > keyIndent)
    )
      runEnd += 1;
    const invokedAs = runInvokesBuilder(block.slice(runIdx, runEnd).join('\n'), builder);
    if (invokedAs === null) continue;
    const atKey = (re: RegExp) =>
      block.filter((l) => new RegExp(`^\\s{${keyIndent}}${re.source}`).test(l)).length;
    if (atKey(/run:/) !== 1 || atKey(/env:/) !== 1) return null;
    const envIdx = block.findIndex((l) => new RegExp(`^\\s{${keyIndent}}env:\\s*$`).test(l));
    if (envIdx < 0) return null;
    const names = new Map<string, number>();
    let childIndent = -1;
    for (let k = envIdx + 1; k < block.length; k++) {
      const raw = block[k];
      if (raw.trim() === '') continue;
      const ind = raw.length - raw.trimStart().length;
      if (ind <= keyIndent) break;
      if (/^\s*#/.test(raw)) continue;
      if (childIndent < 0) childIndent = ind;
      if (ind !== childIndent) continue; // a block scalar's body, not a key
      const m = /^\s*([A-Za-z_][A-Za-z0-9_]*):\s/.exec(raw);
      if (m && !names.has(m[1])) names.set(m[1], from + k + 1);
    }
    const nameIdx = block.findIndex((l) => /^\s*-?\s*name:/.test(l));
    return {
      stepName:
        nameIdx >= 0 ? block[nameIdx].replace(/^\s*-?\s*name:\s*/, '').trim() : '(unnamed step)',
      stepLine: from + 1,
      names,
      invokedAs,
    };
  }
  return null;
}

// ── Controls: prove every extractor, both directions, before any verdict ────
{
  const builderFixture = [
    '"""docstring: env.get("DOC_ONLY_NAME", "") is prose, not a read.',
    'a second docstring line."""',
    '# os.environ.get("COMMENT_ONLY_NAME", "") must be ignored',
    'SUFFIXED_PREFIXES: tuple[str, ...] = (',
    '    "AWS_SES_ACCESS_KEY_ID",',
    '    "OBS_OTLP_CREDENTIALS",',
    ')',
    'KEYS: tuple[tuple[str, str], ...] = (',
    '    ("ACCOUNT_JWT_SECRET", "jwt"),',
    '    ("ROOT_EMAIL", "admin"),',
    ')',
    'REQUIRED_NONEMPTY: tuple[str, ...] = (',
    '    "ACCOUNT_JWT_SECRET",',
    '    "AWS_SES_ACCESS_KEY_ID",',
    '    "RENAMED_AWAY",',
    ')',
    'worker = os.environ.get("WORKER_NAME", "")',
    'jurisdiction = os.environ.get(',
    '    "R2_JURISDICTION", ""',
    ')',
    'pr = env.get("PR_NUMBER", "")',
    'other = values.get("NOT_AN_ENV_READ", "")',
  ].join('\n');

  const reads = builderReads(builderFixture);
  const mustRead = [
    'WORKER_NAME',
    'R2_JURISDICTION',
    'PR_NUMBER',
    'ACCOUNT_JWT_SECRET',
    'ROOT_EMAIL',
  ];
  const mustNotRead = ['COMMENT_ONLY_NAME', 'DOC_ONLY_NAME', 'NOT_AN_ENV_READ', 'RENAMED_AWAY'];
  for (const n of mustRead) {
    if (!reads.has(n)) {
      console.error(
        `x instrument control: builderReads() missed ${n}. Read set was ${JSON.stringify([...reads.keys()])}. Every verdict below would be meaningless.`
      );
      process.exit(1);
    }
  }
  for (const n of mustNotRead) {
    if (reads.has(n)) {
      console.error(
        `x instrument control: builderReads() wrongly reported ${n} as an environment read (it sits in a comment, a docstring, a non-environment mapping, or a guard tuple). A gate that over-reads flags the whole tree.`
      );
      process.exit(1);
    }
  }

  const fan = builderFanIns(builderFixture);
  for (const n of [
    'AWS_SES_ACCESS_KEY_ID_EU',
    'AWS_SES_ACCESS_KEY_ID_US',
    'AWS_SES_ACCESS_KEY_ID_ASIA',
    'OBS_OTLP_CREDENTIALS_ASIA',
  ]) {
    if (!fan.names.has(n)) {
      console.error(
        `x instrument control: builderFanIns() did not resolve ${n} from SUFFIXED_PREFIXES. Got ${JSON.stringify([...fan.names.keys()])}. The fan-ins are the half a find-and-replace cannot see; unresolved, they would be silently unchecked.`
      );
      process.exit(1);
    }
  }
  if (fan.templates.length !== 2) {
    console.error(
      `x instrument control: builderFanIns() read ${fan.templates.length} template(s) from a fixture with two prefixes.`
    );
    process.exit(1);
  }

  const guards = guardLabels(builderFixture, reads, new Set(['AWS_SES_ACCESS_KEY_ID']));
  if (
    guards.length !== 3 ||
    guards[0].varName !== 'ACCOUNT_JWT_SECRET' ||
    guards[1].varName !== null ||
    guards[2].varName !== '(unread)'
  ) {
    console.error(
      `x instrument control: guardLabels() read ${JSON.stringify(guards)}; expected a direct guard on ACCOUNT_JWT_SECRET, a fan-in guard with varName null, and a guard on a name nothing reads flagged (unread).`
    );
    process.exit(1);
  }

  // A channel fan-in counts only with BOTH channel names read; one alone leaves the guard (unread).
  const channelText = 'REQUIRED_NONEMPTY: tuple[str, ...] = (\n    "BACKUP_KEY",\n)\n';
  const both = guardLabels(
    channelText,
    new Map([
      ['BACKUP_KEY_STABLE', 1],
      ['BACKUP_KEY_EDGE', 2],
    ]),
    new Set()
  );
  const one = guardLabels(channelText, new Map([['BACKUP_KEY_STABLE', 1]]), new Set());
  if (
    both.length !== 1 ||
    both[0].varName !== null ||
    one.length !== 1 ||
    one[0].varName !== '(unread)'
  ) {
    console.error(
      `x instrument control: guardLabels() read ${JSON.stringify({ both, one })}; expected a channel fan-in (varName null) with both _STABLE and _EDGE read, and (unread) with only one.`
    );
    process.exit(1);
  }

  // Region-and-channel fan-ins: both tuple layouts expand to region x channel, and a guard on the prefix is a fan-in RESULT, not an (unread) name.
  for (const layout of [
    'SUFFIXED_CHANNEL_PREFIXES: tuple[str, ...] = ("CONFIG_KEY",)\n',
    'SUFFIXED_CHANNEL_PREFIXES: tuple[str, ...] = (\n    "CONFIG_KEY",\n)\n',
  ]) {
    const cf = builderChannelFanIns(layout);
    if (
      cf.prefixes.join(',') !== 'CONFIG_KEY' ||
      cf.names.size !== 6 ||
      !cf.names.has('CONFIG_KEY_ASIA_EDGE')
    ) {
      console.error(
        `x instrument control: builderChannelFanIns() read ${JSON.stringify({ prefixes: cf.prefixes, names: [...cf.names.keys()] })} from ${JSON.stringify(layout)}; expected the one prefix CONFIG_KEY expanded to six region-and-channel names.`
      );
      process.exit(1);
    }
  }
  if (
    builderChannelFanIns('OTHER_PREFIXES: tuple[str, ...] = ("CONFIG_KEY",)\n').prefixes.length !==
    0
  ) {
    console.error(
      'x instrument control: builderChannelFanIns() read a tuple that is not SUFFIXED_CHANNEL_PREFIXES.'
    );
    process.exit(1);
  }
  const cfGuard = guardLabels(
    'REQUIRED_NONEMPTY: tuple[str, ...] = (\n    "CONFIG_KEY",\n)\n',
    new Map(),
    new Set(['CONFIG_KEY'])
  );
  const cfUnread = guardLabels(
    'REQUIRED_NONEMPTY: tuple[str, ...] = (\n    "CONFIG_KEY",\n)\n',
    new Map(),
    new Set()
  );
  if (cfGuard[0]?.varName !== null || cfUnread[0]?.varName !== '(unread)') {
    console.error(
      `x instrument control: guardLabels() read ${JSON.stringify({ cfGuard, cfUnread })}; a guard on a region-and-channel prefix must be a fan-in (varName null), and the same guard with no such prefix must stay (unread).`
    );
    process.exit(1);
  }

  const wfFixture = [
    'jobs:',
    '  deploy:',
    '    steps:',
    '      - name: Unrelated step',
    '        env:',
    '          DECOY_NAME: ${{ secrets.DECOY }}',
    '        run: echo hi',
    '',
    '      - name: Set Worker secrets',
    '        env:',
    '          # a comment inside the env block',
    '          ACCOUNT_JWT_SECRET: ${{ secrets.ACCOUNT_JWT_SECRET }}',
    '          WORKER_NAME: ${{ steps.config.outputs.worker }}',
    '          FOLDED_NOTE: >-',
    '            NOT_A_KEY: the body of a folded scalar, not an env name',
    '        run: .ci/rediacc_ci/deploy/set_fixture_secrets.py',
  ].join('\n');
  const step = stepEnvNames(wfFixture, '.ci/rediacc_ci/deploy/set_fixture_secrets.py');
  if (
    !step ||
    step.stepName !== 'Set Worker secrets' ||
    step.names.size !== 3 ||
    !step.names.has('ACCOUNT_JWT_SECRET') ||
    step.names.has('DECOY_NAME') ||
    step.names.has('NOT_A_KEY')
  ) {
    console.error(
      `x instrument control: stepEnvNames() read ${JSON.stringify(step && { n: step.stepName, k: [...step.names.keys()] })}; expected exactly ACCOUNT_JWT_SECRET, WORKER_NAME and FOLDED_NOTE from the step that runs the fixture builder -- nothing from the neighbouring step, and nothing from the body of a folded scalar.`
    );
    process.exit(1);
  }
  if (step.invokedAs !== 'path') {
    console.error(
      `x instrument control: stepEnvNames() reported the fixture's literal file-path run: line as "${step.invokedAs}". The two spellings must stay distinguishable in the output.`
    );
    process.exit(1);
  }
  if (stepEnvNames(wfFixture, '.ci/rediacc_ci/deploy/absent_builder.py') !== null) {
    console.error(
      'x instrument control: stepEnvNames() invented a step for a builder no step invokes. It must return null so the caller can refuse.'
    );
    process.exit(1);
  }

  // The PORTED spelling: the same builder, invoked as its python module.
  if (
    pythonPortModule('.ci/rediacc_ci/deploy/set_fixture_secrets.py') !==
    'rediacc_ci.deploy.set_fixture_secrets'
  ) {
    console.error(
      `x instrument control: pythonPortModule() mapped the fixture builder to ${JSON.stringify(pythonPortModule('.ci/rediacc_ci/deploy/set_fixture_secrets.py'))}; the rule is .ci/rediacc_ci/<pkg>/<name>.py -> rediacc_ci.<pkg>.<name>.`
    );
    process.exit(1);
  }
  if (pythonPortModule('scripts/ops/example_builder.py') !== null) {
    console.error(
      'x instrument control: pythonPortModule() invented a module for a path outside .ci/rediacc_ci/. A builder with no port must be matched by path only.'
    );
    process.exit(1);
  }
  const portedFixture = wfFixture.replace(
    '        run: .ci/rediacc_ci/deploy/set_fixture_secrets.py',
    '        run: PYTHONPATH=.ci python3 -m rediacc_ci.deploy.set_fixture_secrets'
  );
  if (portedFixture === wfFixture) {
    console.error(
      'x instrument control: the ported-invocation fixture is identical to the file-path one, so the next two assertions would prove nothing about the module form.'
    );
    process.exit(1);
  }
  const portedStep = stepEnvNames(portedFixture, '.ci/rediacc_ci/deploy/set_fixture_secrets.py');
  if (
    !portedStep ||
    portedStep.invokedAs !== 'python-module' ||
    portedStep.stepName !== 'Set Worker secrets' ||
    portedStep.names.size !== 3 ||
    !portedStep.names.has('ACCOUNT_JWT_SECRET')
  ) {
    console.error(
      `x instrument control: stepEnvNames() did not find the step whose run: invokes the builder's python port. Read ${JSON.stringify(portedStep && { n: portedStep.stepName, as: portedStep.invokedAs, k: [...portedStep.names.keys()] })}. A ported builder would read as VACUOUS INPUT and the contract would go unchecked.`
    );
    process.exit(1);
  }
  // ... and the module match must be exact: a LONGER module name is a different
  // script, and claiming its step would read a neighbour's env block.
  const nearMiss = wfFixture.replace(
    '        run: .ci/rediacc_ci/deploy/set_fixture_secrets.py',
    '        run: PYTHONPATH=.ci python3 -m rediacc_ci.deploy.set_fixture_secrets_v2'
  );
  if (stepEnvNames(nearMiss, '.ci/rediacc_ci/deploy/set_fixture_secrets.py') !== null) {
    console.error(
      'x instrument control: stepEnvNames() matched rediacc_ci.deploy.set_fixture_secrets_v2 for set_fixture_secrets.py. A prefix match claims the wrong step and checks the wrong env block.'
    );
    process.exit(1);
  }
  if (
    stepEnvNames(
      wfFixture.replace(
        '        run: .ci/rediacc_ci/deploy/set_fixture_secrets.py',
        '        run: echo "see rediacc_ci.deploy.set_fixture_secrets for the payload"'
      ),
      '.ci/rediacc_ci/deploy/set_fixture_secrets.py'
    ) !== null
  ) {
    console.error(
      'x instrument control: a step merely NAMING the module in prose was matched as invoking it. Only a real `-m <module>` invocation may claim a step.'
    );
    process.exit(1);
  }

  // The failure direction, both halves, on the same fixture pair.
  const exported = new Set(step.names.keys());
  const renamed = new Set(['ACCOUNT_JWT_SECRETX', 'WORKER_NAME']);
  const missingRead = [...reads.keys()].filter(
    (n) => n === 'ACCOUNT_JWT_SECRET' && !renamed.has(n)
  );
  if (missingRead.length !== 1) {
    console.error(
      'x instrument control did not fire: a builder read absent from the step env was not detectable. The gate could not report the defect it exists for.'
    );
    process.exit(1);
  }
  const leftover = [...renamed].filter((n) => !reads.has(n));
  if (leftover.length !== 1 || leftover[0] !== 'ACCOUNT_JWT_SECRETX') {
    console.error(
      'x instrument control did not fire: a leftover export nobody reads was not detectable.'
    );
    process.exit(1);
  }
  // And the NEGATIVE direction: an agreeing pair must produce nothing.
  const agreeing = [...reads.keys()].filter(
    (n) => ['ACCOUNT_JWT_SECRET'].includes(n) && !exported.has(n)
  );
  if (agreeing.length !== 0) {
    console.error(
      'x instrument control: a name that IS exported was still reported as missing. The gate would flag a healthy tree.'
    );
    process.exit(1);
  }
}

// ── Verdict over the real tree ─────────────────────────────────────────────

const refusals: string[] = [];
const problems: string[] = [];
const fired = new Set<string>();
const shape: string[] = [];
let totalExports = 0;
let totalReads = 0;
let totalFanIns = 0;
let totalGuards = 0;

const exemptFor = (name: string, direction: Exemption['direction']) =>
  EXEMPT.find((e) => e.name === name && e.direction === direction);

for (const pair of PAIRS) {
  let wfText: string;
  let bText: string;
  try {
    wfText = readFileSync(join(ROOT, pair.workflow), 'utf8');
  } catch {
    refusals.push(
      `    ${pair.workflow}: MISSING. Refusing to run: this gate cannot see the workflow half of the contract, and a green verdict would mean nothing.`
    );
    continue;
  }
  try {
    bText = readFileSync(join(ROOT, pair.builder), 'utf8');
  } catch {
    refusals.push(
      `    ${pair.builder}: MISSING. Refusing to run: this gate cannot see the builder half of the contract, and a green verdict would mean nothing.`
    );
    continue;
  }

  const step = stepEnvNames(wfText, pair.builder);
  if (step === null) {
    refusals.push(
      `    ${pair.workflow}: no step whose \`run:\` invokes ${pair.builder}, or the step's shape is ambiguous (more than one step-level run:/env:). Refusing to run rather than checking a contract with one end missing.`
    );
    continue;
  }
  if (step.names.size < pair.exportFloor) {
    refusals.push(
      `    ${pair.workflow}:${step.stepLine} step "${step.stepName}" yielded only ${step.names.size} exported env name(s), floor is ${pair.exportFloor}. The env block moved or the parser broke; refusing rather than passing on a short read.`
    );
    continue;
  }

  const reads = builderReads(bText);
  if (reads.size < pair.readFloor) {
    refusals.push(
      `    ${pair.builder}: yielded only ${reads.size} environment read(s), floor is ${pair.readFloor}. The extractor lost the file; refusing.`
    );
    continue;
  }
  const fan = builderFanIns(bText);
  if (fan.templates.length < pair.fanInFloor) {
    refusals.push(
      `    ${pair.builder}: resolved ${fan.templates.length} SUFFIXED_PREFIXES fan-in(s), floor is ${pair.fanInFloor}. The regional indirection is the half no find-and-replace can see; refusing rather than checking the easy names only.`
    );
    continue;
  }

  const chan = builderChannelFanIns(bText);
  if (chan.prefixes.length < pair.channelFanInFloor) {
    refusals.push(
      `    ${pair.builder}: resolved ${chan.prefixes.length} SUFFIXED_CHANNEL_PREFIXES fan-in(s), floor is ${pair.channelFanInFloor}. The region-and-channel indirection is invisible to a find-and-replace; refusing rather than checking the easy names only.`
    );
    continue;
  }

  const allReads = new Map(reads);
  for (const [n, l] of fan.names) if (!allReads.has(n)) allReads.set(n, l);
  for (const [n, l] of chan.names) if (!allReads.has(n)) allReads.set(n, l);
  // The fan-in TEMPLATE variables (SUFFIX) are read; the constructed names
  // replace the indirection itself, which is a local variable and never appears.

  totalExports += step.names.size;
  totalReads += reads.size;
  totalFanIns += fan.templates.length;

  for (const [name, line] of allReads) {
    if (step.names.has(name)) continue;
    const ex = exemptFor(name, 'read-not-exported');
    if (ex) {
      fired.add(`${ex.name}|${ex.direction}`);
      continue;
    }
    problems.push(
      `    ${pair.builder}:${line}  reads ${name}, which ${pair.workflow}:${step.stepLine} ("${step.stepName}") does NOT export.\n` +
        `      The port reads it as "" and the deploy ships an empty value. Export it from that step, or stop reading it.`
    );
  }
  for (const [name, line] of step.names) {
    if (allReads.has(name)) continue;
    const ex = exemptFor(name, 'exported-not-read');
    if (ex) {
      fired.add(`${ex.name}|${ex.direction}`);
      continue;
    }
    problems.push(
      `    ${pair.workflow}:${line}  exports ${name}, which ${pair.builder} never reads.\n` +
        `      A leftover export is the OTHER half of a rename: the builder is reading some other spelling. Delete it, or fix the name the builder reads.`
    );
  }

  const fanPrefixes = new Set([
    ...fan.templates.map((t) => t.replace(/_\$\{SUFFIX\}$/, '')),
    ...chan.prefixes,
  ]);
  for (const g of guardLabels(bText, reads, fanPrefixes)) {
    totalGuards += 1;
    if (g.varName === null) continue; // a fan-in RESULT; its label is the Worker key
    if (g.label !== g.varName) {
      problems.push(
        `    ${pair.builder}:${g.line}  guard demands "${g.label}", but the port never reads that name from the environment.\n` +
          `      A half-renamed guard refuses on a variable nothing supplies. Make the guard name match what the port reads.`
      );
    }
  }

  shape.push(
    `    ${pair.workflow}:${step.stepLine} "${step.stepName}" (runs ${step.invokedAs === 'python-module' ? `the module ${pythonPortModule(pair.builder)}` : 'the file by path'}) exports ${step.names.size} -> ${pair.builder} reads ${reads.size} + ${fan.names.size} fan-in name(s) from ${fan.templates.length} template(s) + ${chan.names.size} region-and-channel name(s) from ${chan.prefixes.length} prefix(es)`
  );
}

if (refusals.length > 0) {
  console.error(
    `x builder env contract: VACUOUS INPUT, refusing to run (${refusals.length}):\n${refusals.join('\n')}\n\n` +
      '  A contract check with one end missing is not a check. It would print a\n' +
      '  checkmark having compared nothing, which is the exact shape this gate exists\n' +
      '  to prevent on the deploy path.'
  );
  process.exit(1);
}

if (shape.length !== PAIRS.length) {
  console.error(
    `x builder env contract: only ${shape.length} of ${PAIRS.length} pair(s) were checked. Refusing a verdict on a partial run.`
  );
  process.exit(1);
}

const dead = EXEMPT.filter((e) => !fired.has(`${e.name}|${e.direction}`));
if (dead.length > 0) {
  problems.push(
    ...dead.map(
      (e) =>
        `    EXEMPT list: "${e.name}" (${e.direction}) never fired this run -- a dead exemption.\n` +
        `      Remove it from EXEMPT in scripts/gates/check-builder-env-contract.ts. An allowlist entry that excuses nothing is how an allowlist becomes a way to pass.`
    )
  );
}

if (problems.length > 0) {
  console.error(
    `x builder env contract broken (${problems.length}):\n${problems.join('\n')}\n\n` +
      '  The workflow step and the builder it runs are joined by nothing but a matching\n' +
      '  string. A disagreement is silent at author time and at lint time; it surfaces\n' +
      '  at DEPLOY time, in production, on the first region that deploys.\n' +
      '  Do not add the name to EXEMPT to get past this. Fix the spelling on one side.'
  );
  process.exit(1);
}

console.log(
  `+ builder env contract: ${PAIRS.length} (workflow step, builder) pair(s) agree in BOTH directions --\n` +
    `  ${totalExports} exported env name(s) vs ${totalReads} direct read(s) plus ${totalFanIns} SUFFIXED_PREFIXES fan-in(s)\n` +
    `  expanded over ${REGION_SUFFIXES.join('/')}, and ${totalGuards} guard name(s) are names the port\n` +
    `  reads. ${EXEMPT.length} exemption(s), all live:\n` +
    EXEMPT.map((e) => `    ${e.name} (${e.direction}): ${e.reason.replace(/^BLOCKER: /, '')}`).join(
      '\n'
    ) +
    '\n' +
    shape.join('\n') +
    '\n' +
    '  Blind spots, stated rather than left to be found: this proves the NAMES agree, not\n' +
    "  that a value is non-empty (that is the builders' REQUIRED_NONEMPTY guards). It does\n" +
    '  NOT cover .ci/rediacc_ci/ops/deploy_bench.py, which builds the same payload from\n' +
    '  a Bitwarden profile rather than a workflow env: block -- a different contract with a\n' +
    '  different oracle. Names read by a sourced library are invisible here too.'
);
