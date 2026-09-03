/**
 * check:ci-builder-env-contract -- the env names a workflow step EXPORTS must
 * be exactly the names the deploy builder it invokes READS.
 *
 * THE DEFECT CLASS. Three CI builders marshal a `wrangler secret bulk` payload
 * out of environment variables:
 *
 *   .ci/scripts/deploy/set-account-worker-secrets.sh   (cd-deploy-account.yml)
 *   .ci/scripts/deploy/set-www-worker-secrets.sh       (cd-deploy-worker.yml)
 *   .ci/scripts/deploy/set-preview-worker-secrets.sh   (ci.yml)
 *
 * and exactly one place decides what those variables are called on the way in:
 * the `env:` block of the workflow step whose `run:` invokes the builder. The
 * two sides are joined by NOTHING but a matching string.
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
 * at lint time, and silent in the job log: bash expands the missing name to the
 * empty string via its `:-` default, the builder's `_require_nonempty` guard
 * (or, worse, no guard at all for an optional key) fires at DEPLOY time, in
 * production, on whichever region deploys first.
 *
 * WHAT IS CHECKED, per (workflow step, builder) pair:
 *   1. every name the builder READS from the environment is EXPORTED by the
 *      step -- the "ships an empty value" direction;
 *   2. every name the step EXPORTS is READ by the builder -- the OTHER half of
 *      the same defect, a leftover export nobody consumes after a rename;
 *   3. every `_require_nonempty NAME "${VAR:-}"` guard names the variable it
 *      actually inspects (label == VAR), so a half-renamed guard cannot report
 *      one name while checking another.
 *
 * THE FAN-INS. set-account-worker-secrets.sh does not read its regional
 * credentials by literal name; it builds the name and dereferences it:
 *
 *      ses_key_var="AWS_SES_ACCESS_KEY_ID_${SUFFIX}"
 *      ses_access_key_id="${!ses_key_var:-}"
 *
 * A find-and-replace cannot see those names and neither can a naive scanner,
 * which is exactly why they are worth checking. This gate resolves them by
 * expanding SUFFIX over the three real regions (EU / US / ASIA, the values
 * `matrix.secretSuffix` takes in cd-deploy-account.yml), so all three regional
 * spellings must be exported.
 *
 * NOT CHECKED, and said out loud rather than left to be discovered:
 *   - scripts/dev/deploy-bench.sh and run.sh also build a secret payload, but
 *     they read a local `.env` file rather than a workflow `env:` block. That
 *     is a different contract with a different oracle; this gate does not look
 *     at them, and their names are covered by check:ci-worker-secret-names.
 *   - VALUES. A name exported as `${{ secrets.TYPO }}` is present and empty.
 *     That is the builders' `_require_nonempty` guards and check_bws_map.py.
 *   - names read by a sourced library (.ci/scripts/lib/common.sh) rather than
 *     by the builder itself. Only the builder file is parsed.
 *
 * Run: npx tsx scripts/check-builder-env-contract.ts
 *
 * Control-first: both extractors are proven on synthetic input, in BOTH
 * directions, before any verdict; every pair carries floors on exports, reads
 * and fan-ins so a broken regex reads as a refusal rather than as "nothing to
 * check"; a missing workflow, a missing builder, an unfindable step or an
 * empty env block all REFUSE rather than pass; and every allowlist entry must
 * fire at least once or the gate fails on the dead exemption.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..');

/** The values `matrix.secretSuffix` takes in cd-deploy-account.yml. */
const REGION_SUFFIXES = ['EU', 'US', 'ASIA'];

interface Pair {
  workflow: string;
  builder: string;
  /** Fewest env names the step is known to export. Below it, refuse. */
  exportFloor: number;
  /** Fewest environment names the builder is known to read. Below it, refuse. */
  readFloor: number;
  /** Fewest `${!var}` fan-ins the builder is known to use. */
  fanInFloor: number;
}

/**
 * Measured 2026-09-02: 44/32/4, 27/25/0, 17/16/0 (exports / direct reads /
 * fan-ins). The floors sit under those, far enough to survive an honest edit
 * and close enough that a lost payload is a refusal, not a pass.
 */
const PAIRS: Pair[] = [
  {
    workflow: '.github/workflows/cd-deploy-account.yml',
    builder: '.ci/scripts/deploy/set-account-worker-secrets.sh',
    exportFloor: 35,
    readFloor: 25,
    fanInFloor: 4,
  },
  {
    workflow: '.github/workflows/cd-deploy-worker.yml',
    builder: '.ci/scripts/deploy/set-www-worker-secrets.sh',
    exportFloor: 20,
    readFloor: 20,
    fanInFloor: 0,
  },
  {
    workflow: '.github/workflows/ci.yml',
    builder: '.ci/scripts/deploy/set-preview-worker-secrets.sh',
    exportFloor: 12,
    readFloor: 12,
    fanInFloor: 0,
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

/** Shell variables bash itself supplies; never part of a workflow contract. */
const SHELL_BUILTINS = new Set([
  'BASH',
  'BASH_SOURCE',
  'BASHPID',
  'BASH_VERSION',
  'FUNCNAME',
  'GROUPS',
  'HISTFILE',
  'HOME',
  'HOSTNAME',
  'IFS',
  'LANG',
  'LC_ALL',
  'LINENO',
  'OLDPWD',
  'OPTARG',
  'OPTIND',
  'OSTYPE',
  'PATH',
  'PIPESTATUS',
  'PPID',
  'PS1',
  'PS2',
  'PWD',
  'RANDOM',
  'REPLY',
  'SECONDS',
  'SHELL',
  'SHLVL',
  'TERM',
  'TMPDIR',
  'UID',
  'EUID',
  'USER',
]);

// ── Extractors, exported so a selftest can drive them directly ─────────────

/** `$NAME`, `${NAME}`, `${NAME:-...}`, `${NAME:?...}` -- upper-snake only. */
const READ_RE = /\$\{([A-Z][A-Z0-9_]*)(?=[}:[])|\$([A-Z][A-Z0-9_]*)/g;
/** `NAME=`, `local NAME=`, `export NAME=`, `declare -r NAME=`. */
const ASSIGN_RE =
  /^\s*(?:local\s+|export\s+|declare\s+(?:-\w+\s+)?|readonly\s+)?([A-Z][A-Z0-9_]*)=/;

/**
 * Environment names a builder reads, mapped to the 1-based line of the first
 * read.
 *
 * A name assigned locally STRICTLY BEFORE its first read is a local variable,
 * not an environment input (`WORKER="pr-${PR_NUMBER}"`, `SCRIPT_DIR=...`).
 * "Strictly" matters: `R2_JURISDICTION="${R2_JURISDICTION:-}"` reads the
 * environment on the right-hand side of its own assignment, so an assignment
 * on the SAME line must not disqualify it. That one line is the difference
 * between checking R2_JURISDICTION and silently dropping it.
 */
export function builderReads(text: string): Map<string, number> {
  const lines = text.split('\n');
  const firstRead = new Map<string, number>();
  const firstAssign = new Map<string, number>();
  lines.forEach((raw, i) => {
    if (/^\s*#/.test(raw)) return; // whole-line comment
    const assign = ASSIGN_RE.exec(raw);
    if (assign && !firstAssign.has(assign[1])) firstAssign.set(assign[1], i);
    for (const m of raw.matchAll(READ_RE)) {
      const name = m[1] ?? m[2];
      if (!firstRead.has(name)) firstRead.set(name, i);
    }
  });
  const out = new Map<string, number>();
  for (const [name, line] of firstRead) {
    if (SHELL_BUILTINS.has(name)) continue;
    const assigned = firstAssign.get(name);
    if (assigned !== undefined && assigned < line) continue;
    out.set(name, line + 1);
  }
  return out;
}

/**
 * `${!var}` fan-ins, resolved. Returns the constructed names with the line of
 * the template assignment, plus the raw templates so a caller can report them.
 */
export function builderFanIns(text: string): { names: Map<string, number>; templates: string[] } {
  const lines = text.split('\n');
  const names = new Map<string, number>();
  const templates: string[] = [];
  const vars = new Set([...text.matchAll(/\$\{!([A-Za-z_][A-Za-z0-9_]*)/g)].map((m) => m[1]));
  for (const v of vars) {
    const idx = lines.findIndex((l) => new RegExp(`^\\s*(?:local\\s+)?${v}=`).test(l));
    if (idx < 0) continue;
    const m = /=\s*"([^"]*)"/.exec(lines[idx]);
    if (!m) continue;
    templates.push(m[1]);
    for (const suffix of REGION_SUFFIXES) {
      const resolved = m[1].replace(/\$\{SUFFIX\}|\$SUFFIX/g, suffix);
      if (/^[A-Z][A-Z0-9_]*$/.test(resolved) && !names.has(resolved)) names.set(resolved, idx + 1);
    }
  }
  return { names, templates };
}

/** `_require_nonempty LABEL "${VAR:-}"` pairs, with the line. Local-variable
 *  values (`"$ses_access_key_id"`) are returned with `varName: null`: those are
 *  fan-in RESULTS, whose label is the Worker key rather than an env name. */
export function guardLabels(
  text: string
): { label: string; varName: string | null; line: number }[] {
  const out: { label: string; varName: string | null; line: number }[] = [];
  text.split('\n').forEach((raw, i) => {
    if (/^\s*#/.test(raw)) return;
    const m = /^\s*_require_nonempty\s+([A-Za-z_][A-Za-z0-9_]*)\s+"([^"]*)"/.exec(raw);
    if (!m) return;
    const v = /^\$\{([A-Z][A-Z0-9_]*)(?::-)?\}$/.exec(m[2]);
    out.push({ label: m[1], varName: v ? v[1] : null, line: i + 1 });
  });
  return out;
}

export interface StepEnv {
  stepName: string;
  stepLine: number;
  names: Map<string, number>;
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
    // The builder must appear in the `run:` SCALAR (its line plus any more-
    // indented continuation), never merely somewhere in the step: a comment
    // naming the builder must not claim the step.
    let runEnd = runIdx + 1;
    while (
      runEnd < block.length &&
      (block[runEnd].trim() === '' ||
        block[runEnd].length - block[runEnd].trimStart().length > keyIndent)
    )
      runEnd += 1;
    if (!block.slice(runIdx, runEnd).join('\n').includes(builder)) continue;
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
    };
  }
  return null;
}

// ── Controls: prove every extractor, both directions, before any verdict ────
{
  const builderFixture = [
    '#!/bin/bash',
    '# ${COMMENT_ONLY_NAME} must be ignored',
    'SCRIPT_DIR="$(dirname "${BASH_SOURCE[0]}")"',
    ': "${WORKER_NAME:?required}"',
    'R2_JURISDICTION="${R2_JURISDICTION:-}"',
    'key_var="AWS_SES_ACCESS_KEY_ID_${SUFFIX}"',
    'ses_key="${!key_var:-}"',
    'WORKER="pr-${PR_NUMBER}"',
    'echo "$SCRIPT_DIR $WORKER $R2_JURISDICTION"',
    '_require_nonempty ACCOUNT_JWT_SECRET "${ACCOUNT_JWT_SECRET:-}"',
    '_require_nonempty AWS_SES_ACCESS_KEY_ID "$ses_key"',
  ].join('\n');

  const reads = builderReads(builderFixture);
  const mustRead = ['WORKER_NAME', 'R2_JURISDICTION', 'SUFFIX', 'PR_NUMBER', 'ACCOUNT_JWT_SECRET'];
  const mustNotRead = ['SCRIPT_DIR', 'WORKER', 'BASH_SOURCE', 'COMMENT_ONLY_NAME'];
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
        `x instrument control: builderReads() wrongly reported ${n} as an environment read (it is a local variable, a shell builtin, or a comment). A gate that over-reads flags the whole tree.`
      );
      process.exit(1);
    }
  }

  const fan = builderFanIns(builderFixture);
  for (const n of [
    'AWS_SES_ACCESS_KEY_ID_EU',
    'AWS_SES_ACCESS_KEY_ID_US',
    'AWS_SES_ACCESS_KEY_ID_ASIA',
  ]) {
    if (!fan.names.has(n)) {
      console.error(
        `x instrument control: builderFanIns() did not resolve ${n} from AWS_SES_ACCESS_KEY_ID_\${SUFFIX}. Got ${JSON.stringify([...fan.names.keys()])}. The fan-ins are the half a find-and-replace cannot see; unresolved, they would be silently unchecked.`
      );
      process.exit(1);
    }
  }

  const guards = guardLabels(builderFixture);
  if (
    guards.length !== 2 ||
    guards[0].varName !== 'ACCOUNT_JWT_SECRET' ||
    guards[1].varName !== null
  ) {
    console.error(
      `x instrument control: guardLabels() read ${JSON.stringify(guards)}; expected a direct env guard on ACCOUNT_JWT_SECRET and a local-variable guard with varName null.`
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
    '        run: .ci/scripts/deploy/set-fixture-secrets.sh',
  ].join('\n');
  const step = stepEnvNames(wfFixture, '.ci/scripts/deploy/set-fixture-secrets.sh');
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
  if (stepEnvNames(wfFixture, '.ci/scripts/deploy/absent-builder.sh') !== null) {
    console.error(
      'x instrument control: stepEnvNames() invented a step for a builder no step invokes. It must return null so the caller can refuse.'
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
      `    ${pair.builder}: resolved ${fan.templates.length} \${!var} fan-in(s), floor is ${pair.fanInFloor}. The regional indirection is the half no find-and-replace can see; refusing rather than checking the easy names only.`
    );
    continue;
  }

  const allReads = new Map(reads);
  for (const [n, l] of fan.names) if (!allReads.has(n)) allReads.set(n, l);
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
        `      Bash expands it to "" and the deploy ships an empty value. Export it from that step, or stop reading it.`
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

  for (const g of guardLabels(bText)) {
    totalGuards += 1;
    if (g.varName === null) continue; // a fan-in RESULT; its label is the Worker key
    if (g.label !== g.varName) {
      problems.push(
        `    ${pair.builder}:${g.line}  _require_nonempty reports "${g.label}" but inspects $${g.varName}.\n` +
          `      A half-renamed guard blames the wrong name in the deploy log. Make the label match the variable.`
      );
    }
  }

  shape.push(
    `    ${pair.workflow}:${step.stepLine} "${step.stepName}" exports ${step.names.size} -> ${pair.builder} reads ${reads.size} + ${fan.names.size} fan-in name(s) from ${fan.templates.length} template(s)`
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
        `      Remove it from EXEMPT in scripts/check-builder-env-contract.ts. An allowlist entry that excuses nothing is how an allowlist becomes a way to pass.`
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
    `  ${totalExports} exported env name(s) vs ${totalReads} direct read(s) plus ${totalFanIns} \${!var} fan-in(s)\n` +
    `  expanded over ${REGION_SUFFIXES.join('/')}, and ${totalGuards} _require_nonempty guard label(s) match the\n` +
    `  variable they inspect. ${EXEMPT.length} exemption(s), all live:\n` +
    EXEMPT.map((e) => `    ${e.name} (${e.direction}): ${e.reason.replace(/^BLOCKER: /, '')}`).join(
      '\n'
    ) +
    '\n' +
    shape.join('\n') +
    '\n' +
    '  Blind spots, stated rather than left to be found: this proves the NAMES agree, not\n' +
    "  that a value is non-empty (that is the builders' _require_nonempty guards). It does\n" +
    '  NOT cover scripts/dev/deploy-bench.sh or run.sh, which build the same payload from a\n' +
    '  local .env file rather than a workflow env: block -- a different contract with a\n' +
    '  different oracle. Names read by a sourced library are invisible here too.'
);
