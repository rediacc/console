/**
 * DIFFERENTIAL SNAPSHOT OF THE FULLY RESOLVED ESLINT CONFIG.
 *
 * WHY THIS EXISTS. eslint.config.js was one 1,444-line file and is now six
 * modules that eslint.config.js imports and concatenates. A split like that is
 * only safe if it is a pure MOVE, and "I read the diff and it looked like a
 * move" is not evidence: flat config is order-sensitive, a block that lands one
 * position earlier can be overridden by a later one, and nothing in the lint run
 * announces that a rule quietly changed severity for one directory.
 *
 * So the split is proved instead of argued. This script asks ESLint itself,
 * through `calculateConfigForFile`, what the RESOLVED config is for every
 * tracked lintable path in the repository, and writes a deterministic record of
 * the answers. Snapshot before the split, snapshot after, compare byte for byte.
 *
 * WHAT IS RECORDED, and why it is not the raw object. The resolved config holds
 * plugin objects, a parser and a globals table, which are megabytes of identical
 * data repeated across a thousand files. Those three are recorded as a SHA-256
 * of their own deterministic serialization rather than inline: a hash compares
 * exactly as strictly as the content it stands for, and keeps the snapshot
 * diffable by a human when it reds. Everything else -- rules and their options,
 * linterOptions, parserOptions, settings, processor, language -- is expanded in
 * full, because that is where a bad split actually shows up.
 *
 * Functions are recorded as name plus a hash of their source, regular
 * expressions by their literal text, `undefined` by a marker, so that no value
 * present in the config can vanish silently into a JSON.stringify hole.
 *
 * USAGE
 *   node eslint-rules/__tests__/config-resolution-differential.mjs --out <file>
 *   node eslint-rules/__tests__/config-resolution-differential.mjs --out <file> --config <flat-config>
 *   node eslint-rules/__tests__/config-resolution-differential.mjs --compare <a> <b>
 *
 * `--out` writes the snapshot (one JSON line per path, sorted by path).
 * `--config` snapshots a DIFFERENT flat config file, which is how the before
 * side of a config refactor stays reachable after the file it lived in has been
 * rewritten: `git show HEAD:eslint.config.js > /tmp/old.mjs` at the repository
 * root, then snapshot that and the working tree and compare the two.
 * `--compare` exits non-zero and prints the first differing paths if the two
 * snapshots are not byte-identical.
 */

import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

import { ESLint } from 'eslint';

const REPO_ROOT = path.resolve(import.meta.dirname, '..', '..');

// The roots `npm run lint` passes to eslint, kept in this order so the corpus
// this script measures is the corpus CI lints and not a superset of it.
const LINT_ROOTS = [
  'packages',
  'scripts',
  'private/account',
  'eslint-rules',
  '.ci',
  'workers',
  '.github/actions',
];

// Extensions any config block in this repo can attach a language or parser to.
// .mts and .cts are in this list because they were MISSING from the first draft,
// and the omission was found by reconciling this corpus against the file list a
// real `eslint` run reports: packages/www/src/plugins/heading-anchors.d.mts is
// tracked, is linted, and was invisible here.
const LINTABLE = new Set([
  '.ts',
  '.tsx',
  '.mts',
  '.cts',
  '.js',
  '.jsx',
  '.cjs',
  '.mjs',
  '.json',
]);

function sha256(text) {
  return createHash('sha256').update(text).digest('hex');
}

/**
 * Tracked files under a root. `private/account` is a submodule, so its files are
 * tracked by its OWN index and are invisible to the superproject's `git
 * ls-files`; asking the submodule directly is the only way they appear at all.
 */
function trackedFiles(root) {
  const abs = path.join(REPO_ROOT, root);
  if (!fs.existsSync(abs)) return [];
  const isSubmodule = fs.existsSync(path.join(abs, '.git'));
  const cwd = isSubmodule ? abs : REPO_ROOT;
  const args = isSubmodule ? ['ls-files'] : ['ls-files', '--', root];
  const out = execFileSync('git', args, { cwd, encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 });
  return out
    .split('\n')
    .filter(Boolean)
    .map((rel) => (isSubmodule ? path.posix.join(root, rel) : rel));
}

function corpus() {
  const seen = new Set();
  for (const root of LINT_ROOTS) {
    for (const rel of trackedFiles(root)) {
      if (LINTABLE.has(path.extname(rel))) seen.add(rel);
    }
  }
  return [...seen].sort();
}

// Deterministic serialization. Object keys are emitted in sorted order so two
// runs cannot differ merely because a spread produced a different insertion
// order; cycles become a marker rather than a throw.
const memo = new WeakMap();
let circularHits = 0;

function ser(value, seen) {
  if (value === undefined) return '__undefined__';
  if (value === null) return null;
  const type = typeof value;
  if (type === 'function') return `__function__:${value.name}:${sha256(value.toString())}`;
  if (type === 'bigint') return `__bigint__:${value.toString()}`;
  if (type === 'symbol') return `__symbol__:${value.toString()}`;
  if (type !== 'object') {
    if (type === 'number' && !Number.isFinite(value)) return `__number__:${String(value)}`;
    return value;
  }
  if (value instanceof RegExp) return `__regexp__:${value.toString()}`;
  if (value instanceof Date) return `__date__:${value.toISOString()}`;
  if (memo.has(value)) return memo.get(value);
  if (seen.has(value)) {
    circularHits += 1;
    return '__circular__';
  }
  seen.add(value);
  const hitsBefore = circularHits;
  let out;
  if (Array.isArray(value)) {
    out = value.map((entry) => ser(entry, seen));
  } else {
    out = {};
    for (const key of Object.keys(value).sort()) out[key] = ser(value[key], seen);
  }
  seen.delete(value);
  // A subtree that hit a cycle serialized differently depending on WHERE it was
  // reached from, so caching it would leak one path's placeholder into another.
  if (circularHits === hitsBefore) memo.set(value, out);
  return out;
}

const hashMemo = new WeakMap();

/** A hash reference for the three bulk values: plugins, parser, globals. */
function hashRef(value, label) {
  if (value === undefined) return '__undefined__';
  if (value === null) return null;
  if (typeof value !== 'object' && typeof value !== 'function') return value;
  if (hashMemo.has(value)) return hashMemo.get(value);
  const ref = `__${label}__:${sha256(JSON.stringify(ser(value, new Set())))}`;
  hashMemo.set(value, ref);
  return ref;
}

function record(config) {
  const out = {};
  for (const key of Object.keys(config).sort()) {
    const value = config[key];
    if (key === 'plugins' && value && typeof value === 'object') {
      const plugins = {};
      for (const name of Object.keys(value).sort()) plugins[name] = hashRef(value[name], 'plugin');
      out.plugins = plugins;
      continue;
    }
    if (key === 'languageOptions' && value && typeof value === 'object') {
      const lang = {};
      for (const inner of Object.keys(value).sort()) {
        lang[inner] =
          inner === 'globals' || inner === 'parser'
            ? hashRef(value[inner], inner)
            : ser(value[inner], new Set());
      }
      out.languageOptions = lang;
      continue;
    }
    out[key] = ser(value, new Set());
  }
  return out;
}

async function snapshot(outPath, overrideConfigFile) {
  const paths = corpus();
  const eslint = new ESLint(
    overrideConfigFile ? { cwd: REPO_ROOT, overrideConfigFile } : { cwd: REPO_ROOT },
  );
  const lines = [];
  let ignored = 0;
  let failed = 0;
  for (const rel of paths) {
    const abs = path.join(REPO_ROOT, rel);
    if (await eslint.isPathIgnored(abs)) {
      ignored += 1;
      continue;
    }
    let config;
    try {
      config = await eslint.calculateConfigForFile(abs);
    } catch (error) {
      failed += 1;
      lines.push(JSON.stringify({ path: rel, error: String(error && error.message) }));
      continue;
    }
    lines.push(JSON.stringify({ path: rel, config: record(config) }));
  }
  fs.writeFileSync(outPath, `${lines.join('\n')}\n`);
  process.stdout.write(
    `candidates=${paths.length} ignored=${ignored} resolved=${lines.length - failed} errors=${failed}\n`,
  );
  process.stdout.write(`snapshot=${outPath} sha256=${sha256(fs.readFileSync(outPath, 'utf8'))}\n`);
}

function compare(aPath, bPath) {
  const a = fs.readFileSync(aPath, 'utf8');
  const b = fs.readFileSync(bPath, 'utf8');
  const aHash = sha256(a);
  const bHash = sha256(b);
  process.stdout.write(`before=${aPath} sha256=${aHash}\n`);
  process.stdout.write(`after=${bPath} sha256=${bHash}\n`);
  if (a === b) {
    process.stdout.write(`IDENTICAL: ${a.split('\n').length - 1} path(s) resolve byte for byte\n`);
    return 0;
  }
  const aLines = a.split('\n');
  const bLines = b.split('\n');
  const index = new Map(aLines.map((line) => [JSON.parse(line || '{}').path, line]).filter(([k]) => k));
  const bIndex = new Map(bLines.map((line) => [JSON.parse(line || '{}').path, line]).filter(([k]) => k));
  let differing = 0;
  const samples = [];
  for (const [key, line] of index) {
    const other = bIndex.get(key);
    if (other === line) continue;
    differing += 1;
    if (samples.length < 5) samples.push({ path: key, before: line, after: other });
  }
  for (const key of bIndex.keys()) {
    if (!index.has(key)) {
      differing += 1;
      if (samples.length < 5) samples.push({ path: key, before: undefined, after: bIndex.get(key) });
    }
  }
  process.stdout.write(`DIFFERENT: ${differing} path(s) resolve differently\n`);
  for (const sample of samples) {
    process.stdout.write(`\n--- ${sample.path}\n`);
    process.stdout.write(`  before: ${firstDelta(sample.before, sample.after)}\n`);
  }
  return 1;
}

/** The first differing key of two snapshot lines, so a red names the rule. */
function firstDelta(before, after) {
  if (before === undefined || after === undefined) return 'path present in only one snapshot';
  const a = JSON.parse(before).config || {};
  const b = JSON.parse(after).config || {};
  const keys = [...new Set([...Object.keys(a), ...Object.keys(b)])].sort();
  const deltas = [];
  for (const key of keys) {
    const left = JSON.stringify(a[key]);
    const right = JSON.stringify(b[key]);
    if (left === right) continue;
    if (key === 'rules') {
      const ruleNames = [...new Set([...Object.keys(a.rules || {}), ...Object.keys(b.rules || {})])].sort();
      for (const rule of ruleNames) {
        const l = JSON.stringify((a.rules || {})[rule]);
        const r = JSON.stringify((b.rules || {})[rule]);
        if (l !== r) deltas.push(`rules[${rule}]: ${l} -> ${r}`);
      }
      continue;
    }
    deltas.push(`${key}: ${left} -> ${right}`);
  }
  return deltas.slice(0, 6).join('; ') || 'byte difference outside the parsed keys';
}

const argv = process.argv.slice(2);
if (argv[0] === '--out' && argv[1]) {
  // `--config` points the run at a DIFFERENT flat config file, which is how the
  // before side of a config refactor stays reachable once the file it lived in
  // has been rewritten.
  const configFlag = argv.indexOf('--config');
  await snapshot(path.resolve(argv[1]), configFlag === -1 ? undefined : path.resolve(argv[configFlag + 1]));
} else if (argv[0] === '--compare' && argv[1] && argv[2]) {
  process.exitCode = compare(path.resolve(argv[1]), path.resolve(argv[2]));
} else {
  process.stderr.write(
    'usage: config-resolution-differential.mjs --out <file> | --compare <before> <after>\n',
  );
  process.exitCode = 2;
}
