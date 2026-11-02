/**
 * `npm run settings`: one registry of tunables and one verb that writes every copy of a value
 * (agent/plans/PLAN-settings-set-verb.md).
 *
 *   list [--json]                                  every registered id, each copy's value, and
 *                                                  whether the copies agree (rc 1 when any
 *                                                  copy is missing, disagrees or is out of range)
 *   get <id> [--json]                              one id, every copy with its file and line
 *   set <id> <value> --reason '<why>' [--task <id>]
 *                                                  parse, range-check, plan every copy and
 *                                                  reason path, write through the pins
 *                                                  transaction, run the id's tests, print the
 *                                                  commit lines; never commits or pushes
 *   --selftest                                     the fixture controls and their mutants
 *
 * THE REGISTRY is .ci/config/settings.json (scripts/lib/settings/registry.ts); units and their
 * parsers are scripts/lib/settings/units.ts; a copy is rewritten by its byte span
 * (scripts/lib/settings/copies.ts), so nothing else in a file moves.
 *
 * THE WRITE is the pins transaction (scripts/lib/pins/txn.ts), not a second implementation:
 * a file holding another session's changes refuses the whole run by name, the before-bytes are
 * journaled under .ci/cache/pins/settings-<stamp>/ before the first write, the id's pytest
 * files run as a step and its gates as `npm run ci -- --only`, and a red restores every file
 * whose bytes are still the ones this run wrote. The journal shares the pins journal root (and
 * its one-run lock and per-tree ledger) because txn.ts fixes that root; `npm run pins -- verify`
 * therefore also sees a settings run killed mid-write.
 *
 * SETTINGS_ROOT points the verb at a fixture tree (the selftest's seam); SETTINGS_MUTANT,
 * honoured only with SETTINGS_ROOT, disables one safety property:
 *   no-range-check   a value outside the entry's min/max is written
 *   first-copy-only  `set` plans only the first copy (and skips the overlay agreement check)
 *   no-dirty-check   the transaction's refusal of a peer-dirty file is off
 *   no-restore       a red test leaves the written bytes in place
 */

import { execFileSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { type ControlCase, summarizeControls } from '../lib/controls.js';
import { isEntryPoint } from '../lib/entry-point.js';
import type { FileWrite, Mutant as PinMutant, PinPlan, PlanStep } from '../lib/pins/driver.js';
import type { PinEntry } from '../lib/pins/registry.js';
import { realRunner, runTransaction, takeLock } from '../lib/pins/txn.js';
import { CopyError, readCopy, writeCopy, writeReason } from '../lib/settings/copies.js';
import {
  type EntryState,
  inspect,
  loadRegistry,
  parseRegistry,
  REGISTRY_REL,
  RegistryError,
  type SettingEntry,
} from '../lib/settings/registry.js';
import { formatValue, parseValue, UnitError } from '../lib/settings/units.js';

const MUTANTS = ['no-range-check', 'first-copy-only', 'no-dirty-check', 'no-restore'] as const;
type Mutant = (typeof MUTANTS)[number];

const REPO_ROOT = path.resolve(import.meta.dirname, '../..');

class Usage extends Error {}

interface Io {
  out: (line: string) => void;
  err: (line: string) => void;
}

interface Ctx extends Io {
  root: string;
  mutant: Mutant | null;
}

const USAGE = `usage: npm run settings -- list [--json]
       npm run settings -- get <id> [--json]
       npm run settings -- set <id> <value> --reason '<why>' [--task <id>]
       npm run settings -- --selftest`;

// ---- list / get -------------------------------------------------------------------------------

function stateJson(s: EntryState): Record<string, unknown> {
  return {
    id: s.entry.id,
    unit: s.entry.unit,
    value: s.value,
    human: s.value === null ? null : formatValue(s.entry.unit, s.value),
    min: s.entry.min,
    max: s.entry.max,
    agree: s.agree,
    in_range: s.inRange,
    copies: s.copies.map((c) => ({
      copy: c.label,
      file: c.file,
      line: c.line,
      value: c.value,
      error: c.error,
    })),
    problems: s.problems,
  };
}

function list(c: Ctx, json: boolean): number {
  const states = loadRegistry(c.root).map((e) => inspect(c.root, e));
  const bad = states.filter((s) => s.problems.length > 0);
  if (json) {
    c.out(JSON.stringify({ settings: states.map(stateJson) }, null, 2));
    return bad.length > 0 ? 1 : 0;
  }
  for (const s of states) {
    const human = s.value === null ? '?' : formatValue(s.entry.unit, s.value);
    const verdict = s.problems.length === 0 ? 'agree' : 'PROBLEM';
    c.out(
      `${s.entry.id}  ${human} (${s.value ?? '?'} ${s.entry.unit})  ${s.copies.length} cop${s.copies.length === 1 ? 'y' : 'ies'} ${verdict}`
    );
    for (const cp of s.copies)
      c.out(
        `    ${cp.error ? 'MISSING' : String(cp.value)}  ${cp.label}${cp.line ? `:${cp.line}` : ''}`
      );
    for (const p of s.problems) c.err(`    PROBLEM ${s.entry.id}: ${p}`);
  }
  c.out(
    bad.length === 0
      ? `${states.length} settings, every copy agrees and sits in range.`
      : `${bad.length} of ${states.length} settings have problems: ${bad.map((s) => s.entry.id).join(', ')}`
  );
  return bad.length > 0 ? 1 : 0;
}

function entryOf(c: Ctx, id: string): SettingEntry {
  const reg = loadRegistry(c.root);
  const e = reg.find((x) => x.id === id);
  if (!e)
    throw new Usage(
      `no setting ${JSON.stringify(id)} in ${REGISTRY_REL} (registered: ${reg.map((x) => x.id).join(', ')})`
    );
  return e;
}

function get(c: Ctx, id: string, json: boolean): number {
  const s = inspect(c.root, entryOf(c, id));
  if (json) {
    c.out(JSON.stringify(stateJson(s), null, 2));
    return s.problems.length > 0 ? 1 : 0;
  }
  const e = s.entry;
  c.out(
    `${e.id}: ${s.value === null ? '?' : formatValue(e.unit, s.value)} (${s.value ?? '?'} ${e.unit})`
  );
  c.out(`  range ${formatValue(e.unit, e.min)} .. ${formatValue(e.unit, e.max)}; ${e.why}`);
  s.copies.forEach((cp, i) =>
    c.out(
      `  ${i === 0 ? 'source' : 'copy  '} ${cp.error ? `MISSING (${cp.error})` : String(cp.value)}  ${cp.file}${cp.line ? `:${cp.line}` : ''}  ${cp.label}`
    )
  );
  for (const r of e.reason_paths) c.out(`  reason ${r.file}#${r.json_path} (${r.mode})`);
  c.out(`  tests  ${[...e.tests.pytest, ...e.tests.gates].join(', ') || '(none)'}`);
  for (const p of s.problems) c.err(`  PROBLEM: ${p}`);
  return s.problems.length > 0 ? 1 : 0;
}

// ---- set -------------------------------------------------------------------------------------

/** Every file `set` writes, with its planned text; refuses (Usage) before any write on a bad value or a copy that will not resolve. */
export function planSet(
  root: string,
  e: SettingEntry,
  value: number,
  reason: string,
  mutant: Mutant | null
): FileWrite[] {
  if (mutant !== 'no-range-check' && (value < e.min || value > e.max))
    throw new Usage(
      `${e.id}: ${formatValue(e.unit, value)} (${value}) is outside the registered range ${formatValue(e.unit, e.min)} .. ${formatValue(e.unit, e.max)} (${e.min} .. ${e.max}); nothing written`
    );
  const original = new Map<string, string | null>();
  const planned = new Map<string, string>();
  const read = (rel: string): string => {
    if (planned.has(rel)) return planned.get(rel) as string;
    if (!original.has(rel)) {
      const abs = path.join(root, rel);
      original.set(rel, fs.existsSync(abs) ? fs.readFileSync(abs, 'utf8') : null);
    }
    const t = original.get(rel);
    if (t === null || t === undefined)
      throw new Usage(`${e.id}: ${rel} does not exist; nothing written`);
    return t;
  };
  const human = formatValue(e.unit, value);
  try {
    for (const c of mutant === 'first-copy-only' ? e.copies.slice(0, 1) : e.copies)
      planned.set(c.file, writeCopy(read(c.file), c, value));
    for (const r of e.reason_paths)
      planned.set(r.file, writeReason(read(r.file), r, human, reason));
    if (mutant !== 'first-copy-only')
      for (const c of e.copies) {
        const got = readCopy(read(c.file), c).value;
        if (got !== value)
          throw new CopyError(`the planned ${c.file} reads ${String(got)} back, not ${value}`);
      }
  } catch (err) {
    if (err instanceof CopyError) throw new Usage(`${e.id}: ${err.message}; nothing written`);
    throw err;
  }
  return [...planned]
    .filter(([rel, after]) => original.get(rel) !== after)
    .map(([file, after]) => ({ repo: '.', file, after }));
}

const shq = (s: string): string =>
  /^[\w@%+=:,./-]+$/.test(s) ? s : `'${s.replace(/'/g, `'\\''`)}'`;

const newStamp = (): string =>
  `settings-${new Date()
    .toISOString()
    .replace(/[-:]/g, '')
    .replace(/\.\d{3}Z$/, 'Z')}-${crypto.randomBytes(3).toString('hex')}`;

function submodulesOf(root: string): string[] {
  try {
    return execFileSync(
      'git',
      ['-C', root, 'config', '--file', '.gitmodules', '--get-regexp', 'path'],
      {
        encoding: 'utf8',
        stdio: ['ignore', 'pipe', 'ignore'],
      }
    )
      .split('\n')
      .map((l) => l.split(' ')[1])
      .filter((p): p is string => !!p);
  } catch {
    return [];
  }
}

let pytestBin: string | null | undefined;

/**
 * The pytest binary `.ci/bootstrap.sh doctor` resolves ($PYTEST_BIN, a PATH binary at the pin,
 * the repo-local install), through check_pytest.resolve_pytest rather than a further copy of
 * that ladder; resolved once per process, always from the console root (a fixture carries no
 * bootstrap). null when none resolves.
 */
function resolvePytest(): string | null {
  if (pytestBin !== undefined) return pytestBin;
  try {
    const out = execFileSync(
      'python3',
      [
        '-c',
        'import pathlib, sys\nfrom rediacc_ci.check_pytest import resolve_pytest\nprint(resolve_pytest(pathlib.Path(sys.argv[1])) or "")',
        REPO_ROOT,
      ],
      {
        encoding: 'utf8',
        env: { ...process.env, PYTHONPATH: path.join(REPO_ROOT, '.ci') },
        stdio: ['ignore', 'pipe', 'pipe'],
        timeout: 180_000,
      }
    ).trim();
    pytestBin = out === '' ? null : out;
  } catch {
    pytestBin = null;
  }
  return pytestBin;
}

function set(c: Ctx, id: string, raw: string, reason: string, task: string | null): number {
  const e = entryOf(c, id);
  let value: number;
  try {
    value = parseValue(e.unit, raw);
  } catch (err) {
    if (err instanceof UnitError) throw new Usage(`${e.id}: ${err.message}; nothing written`);
    throw err;
  }
  const before = inspect(c.root, e);
  const writes = planSet(c.root, e, value, reason, c.mutant);
  if (writes.length === 0) {
    c.out(
      `${e.id} already holds ${formatValue(e.unit, value)} at every copy with this reason; nothing written.`
    );
    return 0;
  }
  const human = formatValue(e.unit, value);
  let pytest: string | null = null;
  if (e.tests.pytest.length) {
    const bin = resolvePytest();
    if (!bin)
      throw new Usage(
        `${e.id} names pytest tests and no pytest resolves (bash .ci/bootstrap.sh installs it; bash .ci/bootstrap.sh doctor shows what resolved); nothing written`
      );
    // No `-p no:cacheprovider`: disabling that plugin unregisters pyproject's `cache_dir` ini key, and under its `--strict-config`
    // pytest then exits 4 having collected nothing, so every real `set` went red and restored (the cache lands in the ignored .ci/cache/pytest).
    pytest = `PYTHONPATH=.ci PYTHONDONTWRITEBYTECODE=1 ${shq(bin)} -q ${e.tests.pytest.map(shq).join(' ')}`;
  }
  const steps: PlanStep[] = pytest
    ? [{ label: `tests: ${pytest}`, run: pytest, cwd: '.', writes: [] }]
    : [];
  const plan = {
    entry: { id: `settings:${e.id}`, gates: e.tests.gates, derive: [] } as unknown as PinEntry,
    from: before.value === null ? null : String(before.value),
    to: { version: String(value), publishedMs: null },
    writes,
    steps,
    changes: e.copies.map((cp) => `${cp.file}: ${before.value ?? '?'} -> ${value}`),
  } as PinPlan;
  const release = takeLock(c.root);
  if (!release)
    throw new Usage('another pins or settings run holds .ci/cache/pins/.lock; nothing written');
  let res: ReturnType<typeof runTransaction>;
  try {
    res = runTransaction([plan], {
      root: c.root,
      stamp: newStamp(),
      runner: realRunner,
      mutant: (c.mutant === 'no-dirty-check' || c.mutant === 'no-restore'
        ? c.mutant
        : null) as PinMutant | null,
      npmVersion: null,
      submodules: submodulesOf(c.root),
    });
  } finally {
    release();
  }
  const ran = [
    ...(pytest
      ? [`${pytest}  # rc=${res.commands.find((x) => x.cmd === pytest)?.rc ?? 'not run'}`]
      : []),
    ...(res.gates ? [`npm run ci -- --only ${res.gates.ids.join(',')}  # rc=${res.gates.rc}`] : []),
  ];
  if (!res.ok) {
    c.err(`FAILED ${e.id} -> ${human}: ${res.failure}`);
    if (res.restored.length) c.err(`  restored: ${res.restored.join(', ')}`);
    if (res.leftAlone.length)
      c.err(`  left alone (changed since this run wrote them): ${res.leftAlone.join(', ')}`);
    for (const r of ran) c.err(`  ran: ${r}`);
    c.err(`  journal: ${path.relative(c.root, res.dir)}`);
    return 1;
  }
  const paths = res.changes.flatMap((ch) => ch.paths);
  const added = res.changes.flatMap((ch) => ch.added);
  const msg = [
    `chore(settings): ${e.id} to ${human}`,
    '',
    `${e.id}: ${before.value === null ? '?' : formatValue(e.unit, before.value)} -> ${human} (${value} ${e.unit}), written to every registered copy:`,
    ...e.copies.map(
      (cp) =>
        `- ${cp.file} ${'json_path' in cp ? cp.json_path : `${cp.py_dict}[${JSON.stringify(cp.py_key)}]`}`
    ),
    '',
    `Reason: ${reason.trim()}`,
    '',
    'Verification:',
    ...(ran.length ? ran.map((r) => `- ${r}`) : ['- no tests registered for this id']),
    ...(task ? ['', `PR-TASK: ${task}`] : []),
    '',
  ].join('\n');
  const msgFile = path.join(res.dir, 'commit-msg.txt');
  fs.writeFileSync(msgFile, msg);
  c.out(`${e.id} set to ${human} (${value}) in ${paths.join(', ')}`);
  for (const r of ran) c.out(`  ran: ${r}`);
  c.out('commit with:');
  if (added.length) c.out(`  git add -- ${added.map(shq).join(' ')}`);
  c.out(`  git commit -F ${shq(path.relative(c.root, msgFile))} -- ${paths.map(shq).join(' ')}`);
  return 0;
}

// ---- the CLI ---------------------------------------------------------------------------------

function flag(argv: string[], name: string): string | null {
  const i = argv.indexOf(name);
  if (i < 0) return null;
  const v = argv[i + 1];
  if (v === undefined || v.startsWith('--')) throw new Usage(`${name} needs a value`);
  argv.splice(i, 2);
  return v;
}

export function main(argv: string[], env: NodeJS.ProcessEnv, io: Io): number {
  const fixture = env.SETTINGS_ROOT;
  const m = fixture ? env.SETTINGS_MUTANT : undefined;
  if (m && !(MUTANTS as readonly string[]).includes(m)) {
    io.err(`SETTINGS_MUTANT ${m} is not one of ${MUTANTS.join(', ')}`);
    return 2;
  }
  const c: Ctx = { ...io, root: fixture ?? REPO_ROOT, mutant: m ? (m as Mutant) : null };
  const args = [...argv];
  try {
    const json = args.includes('--json');
    if (json) args.splice(args.indexOf('--json'), 1);
    const verb = args.shift();
    if (verb === 'list' && args.length === 0) return list(c, json);
    if (verb === 'get' && args.length === 1) return get(c, args[0], json);
    if (verb === 'set') {
      const reason = flag(args, '--reason');
      const task = flag(args, '--task');
      if (args.length !== 2) throw new Usage(USAGE);
      if (!reason || reason.trim() === '')
        throw new Usage(
          `set needs --reason '<why>' (the ruling, written beside the value); nothing written`
        );
      return set(c, args[0], args[1], reason, task);
    }
    throw new Usage(USAGE);
  } catch (err) {
    if (err instanceof Usage || err instanceof RegistryError) {
      io.err(err.message);
      return err instanceof Usage && err.message === USAGE ? 2 : 1;
    }
    throw err;
  }
}

// ---- selftest --------------------------------------------------------------------------------

const SPEND = '.ci/config/cf-spend-guard.json';
const PY = '.ci/rediacc_ci/ops/cf_usage_report.py';
const R2 = 'cf.r2_storage_bytes';

interface Run {
  rc: number;
  out: string;
  err: string;
}

function drive(root: string, argv: string[], mutant: Mutant | null): Run {
  const out: string[] = [];
  const err: string[] = [];
  const rc = main(
    argv,
    { SETTINGS_ROOT: root, ...(mutant ? { SETTINGS_MUTANT: mutant } : {}) },
    {
      out: (l) => out.push(l),
      err: (l) => err.push(l),
    }
  );
  return { rc, out: out.join('\n'), err: err.join('\n') };
}

const git = (root: string, ...args: string[]): string =>
  execFileSync(
    'git',
    [
      '-C',
      root,
      '-c',
      'core.hooksPath=/dev/null',
      '-c',
      'user.email=selftest@invalid',
      '-c',
      'user.name=selftest',
      ...args,
    ],
    { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }
  );

const FIXTURE_TEST = `import json, pathlib


def test_r2_ceiling_is_not_the_poisoned_value():
    d = json.loads(pathlib.Path(".ci/config/cf-spend-guard.json").read_text())
    assert d["notifications"]["products"]["r2_storage"]["limit"] != 4000000000000
`;

/**
 * The console's own `[tool.pytest.ini_options]` table, verbatim, so the fixture's nested pytest
 * meets the ini a real `set` meets (`--strict-config`, `cache_dir`, the addopts). A fixture with
 * no ini once hid an argv that made every real run exit 4 having collected nothing.
 */
function pytestIni(text = fs.readFileSync(path.join(REPO_ROOT, 'pyproject.toml'), 'utf8')): string {
  const m = /^\[tool\.pytest\.ini_options\]\n[\s\S]*?(?=^\[|(?![\s\S]))/m.exec(text);
  if (!m)
    throw new Error(
      'pyproject.toml has no [tool.pytest.ini_options] table to copy into the fixture'
    );
  return m[0];
}

/**
 * A git tree holding the REAL registry, the REAL spend-guard JSON and the REAL cf_usage_report.py
 * (so the byte-span edits run on the shapes they will meet), with the R2 ceiling seeded back to
 * 200 GB at every copy and each id's tests pointed at one fixture test that goes red on 4 TB.
 */
function fixture(): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'settings-selftest-'));
  const reg = JSON.parse(fs.readFileSync(path.join(REPO_ROOT, REGISTRY_REL), 'utf8'));
  for (const s of reg.settings) s.tests = { gates: [], pytest: ['tests/test_fx.py'] };
  const files: Record<string, string> = {
    [REGISTRY_REL]: `${JSON.stringify(reg, null, 2)}\n`,
    [SPEND]: fs.readFileSync(path.join(REPO_ROOT, SPEND), 'utf8'),
    [PY]: fs.readFileSync(path.join(REPO_ROOT, PY), 'utf8'),
    'tests/test_fx.py': FIXTURE_TEST,
    '.gitignore': '.ci/cache/\n__pycache__/\n',
    'pyproject.toml': pytestIni(),
  };
  const r2 = (parseRegistry(reg).find((e) => e.id === R2) as SettingEntry).copies;
  for (const cp of r2) files[cp.file] = writeCopy(files[cp.file], cp, 200e9);
  for (const [rel, text] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), text);
  }
  git(root, 'init', '-q');
  git(root, 'add', '-A');
  git(root, 'commit', '-q', '-m', 'fixture');
  return root;
}

const read = (root: string, rel: string): string => fs.readFileSync(path.join(root, rel), 'utf8');
const snap = (root: string): string => [SPEND, PY].map((f) => read(root, f)).join('\0');
const r2Values = (root: string): unknown[] => {
  const e = loadRegistry(root).find((x) => x.id === R2) as SettingEntry;
  return e.copies.map((cp) => readCopy(read(root, cp.file), cp).value);
};

function unitCases(): ControlCase[] {
  const good: [Parameters<typeof parseValue>[0], string, number][] = [
    ['bytes', '5TB', 5e12],
    ['bytes', '500GB', 5e11],
    ['bytes', '5e12', 5e12],
    ['bytes', '5000000000000', 5e12],
    ['bytes', '5_000_000_000_000', 5e12],
    ['bytes', '4GiB', 2 ** 32],
    ['bytes', '1.5 TB', 1.5e12],
    ['count', '20M', 2e7],
    ['count', '2.5M', 2.5e6],
    ['count', '1.5k', 1500],
    ['ms', '60M', 6e7],
    ['ms', '90s', 90000],
    ['ms', '2h', 7.2e6],
    ['usd', '$350', 350],
    ['usd', '49.99', 49.99],
    ['usd', '350 USD', 350],
  ];
  const bad: [Parameters<typeof parseValue>[0], string][] = [
    ['bytes', '5XB'],
    ['bytes', '5tb'],
    ['bytes', 'five'],
    ['bytes', '1.5'],
    ['bytes', '-5TB'],
    ['bytes', '5__0'],
    ['count', '20MB'],
    ['count', '0.5'],
    ['usd', '$1.234'],
    ['ms', '5 days'],
  ];
  const cases: ControlCase[] = good.map(([u, raw, want]) => {
    let got: unknown;
    try {
      got = parseValue(u, raw);
    } catch (err) {
      got = (err as Error).message;
    }
    return {
      name: `units: ${u} ${JSON.stringify(raw)} parses to ${want}`,
      ok: got === want,
      detail: `got ${String(got)}`,
    };
  });
  for (const [u, raw] of bad) {
    let threw = false;
    try {
      parseValue(u, raw);
    } catch (err) {
      threw = err instanceof UnitError;
    }
    cases.push({ name: `units: ${u} ${JSON.stringify(raw)} is refused`, ok: threw });
  }
  cases.push({
    name: 'units: 5000000000000 bytes reads back as 5 TB, 4294967296 as 4 GiB, 20000000 as 20M',
    ok:
      formatValue('bytes', 5e12) === '5 TB' &&
      formatValue('bytes', 2 ** 32) === '4 GiB' &&
      formatValue('count', 2e7) === '20M',
  });
  return cases;
}

function registryCases(): ControlCase[] {
  const base = {
    id: 'x',
    unit: 'count',
    min: 1,
    max: 2,
    why: 'w',
    copies: [{ file: 'f.json', json_path: '/a' }],
    tests: { gates: [], pytest: [] },
  };
  const refuses = (name: string, doc: unknown): ControlCase => {
    let threw = '';
    try {
      parseRegistry(doc);
    } catch (err) {
      threw = err instanceof RegistryError ? err.message : `other: ${(err as Error).message}`;
    }
    return {
      name: `registry: ${name} is refused`,
      ok: threw !== '' && !threw.startsWith('other'),
      detail: threw,
    };
  };
  return [
    refuses('a duplicate id', { settings: [base, base] }),
    refuses('an unknown unit', { settings: [{ ...base, unit: 'furlongs' }] }),
    refuses('min above max', { settings: [{ ...base, min: 3 }] }),
    refuses('an entry with no copy', { settings: [{ ...base, copies: [] }] }),
    refuses('a copy with both json_path and py_dict', {
      settings: [{ ...base, copies: [{ file: 'f', json_path: '/a', py_dict: 'D', py_key: 'k' }] }],
    }),
  ];
}

function treeCases(m: Mutant | null): ControlCase[] {
  const cases: ControlCase[] = [];
  const roots: string[] = [];
  const fx = (): string => {
    const r = fixture();
    roots.push(r);
    return r;
  };
  try {
    // The real tree: the acceptance reading of `list`.
    const real = main(['list', '--json'], {}, { out: () => {}, err: () => {} });
    const realR2 = inspect(
      REPO_ROOT,
      entryOf({ root: REPO_ROOT, mutant: null, out: () => {}, err: () => {} }, R2)
    );
    cases.push({
      name: 'list: the real tree resolves every registered copy, they agree, and the R2 ceiling reads 5000000000000 at all three copies',
      ok:
        real === 0 && realR2.copies.length === 3 && realR2.copies.every((cp) => cp.value === 5e12),
      detail: `rc=${real} r2=${realR2.copies.map((cp) => `${cp.label}=${String(cp.value)}`).join(', ')}`,
    });

    // A planted disagreement and a dangling path go red in list.
    {
      const r = fx();
      const e = loadRegistry(r).find((x) => x.id === R2) as SettingEntry;
      fs.writeFileSync(path.join(r, PY), writeCopy(read(r, PY), e.copies[2], 7e9));
      const run = drive(r, ['list'], m);
      cases.push({
        name: 'list: a copy planted out of agreement is named and exits 1',
        ok: run.rc === 1 && run.err.includes(`PROBLEM ${R2}: copies disagree`),
        detail: `rc=${run.rc} err=${run.err.slice(0, 300)}`,
      });
      const reg = JSON.parse(read(r, REGISTRY_REL));
      reg.settings[0].copies[0].json_path = '/notifications/products/no_such_product/limit';
      fs.writeFileSync(path.join(r, REGISTRY_REL), JSON.stringify(reg));
      const dangling = drive(r, ['get', reg.settings[0].id], m);
      cases.push({
        name: 'get: a copy whose path does not resolve is named and exits 1',
        ok:
          dangling.rc === 1 &&
          dangling.out.includes('MISSING') &&
          dangling.err.includes('does not resolve'),
        detail: `rc=${dangling.rc} out=${dangling.out.slice(0, 300)} err=${dangling.err.slice(0, 300)}`,
      });
    }

    // Control 1: an out-of-range value is refused before any write.
    {
      const r = fx();
      const pre = snap(r);
      const run = drive(r, ['set', R2, '5PB', '--reason', 'selftest'], m);
      cases.push({
        name: 'set: a value outside the range (5PB, max 1 PB) is refused and no byte changes',
        ok: run.rc === 1 && run.err.includes('outside the registered range') && snap(r) === pre,
        detail: `rc=${run.rc} err=${run.err.slice(0, 300)} changed=${snap(r) !== pre}`,
      });
      const bad = drive(r, ['set', R2, '5 parsecs', '--reason', 'selftest'], m);
      cases.push({
        name: 'set: an unparseable value is refused and no byte changes',
        ok: bad.rc === 1 && bad.err.includes('is not a byte size') && snap(r) === pre,
        detail: `rc=${bad.rc} err=${bad.err.slice(0, 300)}`,
      });
      const noReason = drive(r, ['set', R2, '5TB'], m);
      cases.push({
        name: 'set: a run without --reason is refused and no byte changes',
        ok: noReason.rc === 1 && noReason.err.includes('--reason') && snap(r) === pre,
        detail: `rc=${noReason.rc} err=${noReason.err}`,
      });
    }

    // Control 2: a file holding another session's change refuses the whole run.
    {
      const r = fx();
      const peer = read(r, SPEND).replace('"policy_prefix"', '"policy_prefix" ');
      fs.writeFileSync(path.join(r, SPEND), peer);
      const pyBefore = read(r, PY);
      const run = drive(r, ['set', R2, '5TB', '--reason', 'selftest'], m);
      cases.push({
        name: "set: a spend-guard file holding a peer's uncommitted change refuses the run by name, and the peer's bytes and the other copy stay",
        ok:
          run.rc === 1 &&
          run.err.includes(`refused: ${SPEND}`) &&
          read(r, SPEND) === peer &&
          read(r, PY) === pyBefore,
        detail: `rc=${run.rc} err=${run.err.slice(0, 400)}`,
      });
    }

    // Control 3: a red test restores every written byte.
    {
      const r = fx();
      const pre = snap(r);
      const run = drive(r, ['set', R2, '4TB', '--reason', 'selftest'], m);
      cases.push({
        name: 'set: a failing test (4TB is poisoned in the fixture test) restores both spend-guard copies and the code copy byte for byte',
        ok:
          run.rc === 1 &&
          run.err.includes('step failed') &&
          run.err.includes('restored:') &&
          snap(r) === pre,
        detail: `rc=${run.rc} err=${run.err.slice(0, 400)} restoredBytes=${snap(r) === pre}`,
      });
    }

    // Control 4: 5TB lands as 5000000000000 at every copy, with nothing else moved.
    {
      const r = fx();
      const run = drive(
        r,
        ['set', R2, '5TB', '--reason', 'operator ruling selftest', '--task', 'deadbeef'],
        m
      );
      const vals = r2Values(r);
      const numstat = git(r, 'diff', '--numstat');
      const spend = JSON.parse(read(r, SPEND));
      const msgRel = /git commit -F (\S+) --/.exec(run.out)?.[1];
      const msg = msgRel ? read(r, msgRel) : '';
      cases.push({
        name: 'set: 5TB is written as 5000000000000 to both spend-guard copies (and the code default), the test runs green, and the commit line is printed',
        ok:
          run.rc === 0 &&
          spend.notifications.products.r2_storage.limit === 5000000000000 &&
          spend.report.r2_storage_bytes === 5000000000000 &&
          vals.every((v) => v === 5e12) &&
          read(r, PY).includes('"r2_storage_bytes": 5_000_000_000_000,') &&
          run.out.includes(`-- ${SPEND} ${PY}`) &&
          msg.includes('PR-TASK: deadbeef') &&
          msg.includes('# rc=0'),
        detail: `rc=${run.rc} vals=${vals.join(',')} out=${run.out.slice(0, 400)} err=${run.err.slice(0, 400)}`,
      });
      cases.push({
        name: 'set: only the value and reason lines move (spend-guard 4 lines: two limits, the why, report_reason; the code 1 line)',
        ok: numstat.includes(`4\t4\t${SPEND}`) && numstat.includes(`1\t1\t${PY}`),
        detail: numstat,
      });
      cases.push({
        name: "set: the ruling lands in the product's why and replaces only the r2 segment of report_reason",
        ok:
          spend.notifications.products.r2_storage.why ===
            'R2 storage, 5 TB. operator ruling selftest.' &&
          spend.report_reason.startsWith(
            'r2_storage_bytes: 5 TB, operator ruling selftest. containers_*: '
          ),
        detail: `why=${spend.notifications.products.r2_storage.why} reason=${spend.report_reason.slice(0, 120)}`,
      });
      const again = drive(r, ['set', R2, '5TB', '--reason', 'operator ruling selftest'], m);
      cases.push({
        name: 'set: repeating the same value and reason writes nothing',
        ok: again.rc === 0 && again.out.includes('nothing written'),
        detail: `rc=${again.rc} out=${again.out} err=${again.err}`,
      });
    }
  } finally {
    for (const r of roots) fs.rmSync(r, { recursive: true, force: true });
  }
  return cases;
}

/**
 * The fixture's one test is a single JSON assertion, so a host with no pytest (the CI Code lane
 * bootstraps none) runs it through this stub, handed to the resolver as $PYTEST_BIN: the verb's
 * own ladder is exercised unchanged, only the binary differs. A host that resolves a real pytest
 * keeps it, so the nested-ini argv check above still runs there. Returns the stub's dir, or null.
 */
function stubPytestIfAbsent(): string | null {
  if (resolvePytest() !== null) return null;
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'settings-pytest-stub-'));
  const bin = path.join(dir, 'pytest');
  fs.writeFileSync(
    bin,
    `#!/usr/bin/env python3
import json, pathlib, sys
if sys.argv[1:] != ["-q", "tests/test_fx.py"]:
    print("stub pytest: unexpected argv %r" % sys.argv[1:], file=sys.stderr)
    sys.exit(4)
d = json.loads(pathlib.Path(".ci/config/cf-spend-guard.json").read_text())
if d["notifications"]["products"]["r2_storage"]["limit"] == 4000000000000:
    print("FAILED tests/test_fx.py::test_r2_ceiling_is_not_the_poisoned_value")
    sys.exit(1)
print("1 passed")
`,
    { mode: 0o755 }
  );
  process.env.PYTEST_BIN = bin;
  pytestBin = undefined;
  if (resolvePytest() !== bin) {
    fs.rmSync(dir, { recursive: true, force: true });
    delete process.env.PYTEST_BIN;
    pytestBin = undefined;
    return null;
  }
  return dir;
}

function selftest(): number {
  const stubDir = stubPytestIfAbsent();
  try {
    return runSelftest();
  } finally {
    if (stubDir) fs.rmSync(stubDir, { recursive: true, force: true });
  }
}

function runSelftest(): number {
  const quiet = { log: () => {}, err: () => {} };
  console.log('controls:');
  const rc = summarizeControls([...unitCases(), ...registryCases(), ...treeCases(null)]);
  let missed = 0;
  console.log('mutants (each must turn at least one control red):');
  for (const m of MUTANTS) {
    const cases = treeCases(m);
    const failed = summarizeControls(cases, quiet) !== 0;
    const by = cases.filter((x) => !x.ok).map((x) => x.name.split(' (')[0].slice(0, 70));
    console.log(
      `  ${failed ? 'PASS' : 'FAIL'}  mutant ${m} ${failed ? `is caught by: ${by.join('; ')}` : 'went UNCAUGHT'}`
    );
    if (!failed) missed++;
  }
  return rc !== 0 || missed > 0 ? 1 : 0;
}

if (isEntryPoint(import.meta.filename)) {
  const argv = process.argv.slice(2);
  process.exit(
    argv[0] === '--selftest' && argv.length === 1
      ? selftest()
      : main(argv, process.env, { out: (l) => console.log(l), err: (l) => console.error(l) })
  );
}
