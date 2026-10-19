#!/usr/bin/env tsx
/**
 * check:ci-selftest-reachability -- every selftest entry point in the tree is run by
 * something CI runs. An unrun selftest reads exactly like a passing one.
 *
 * THE DEFECT THIS CLOSES. Four selftests under scripts/lib/pins/ (the embed, toolchain and
 * devcontainer drivers, and the transaction journal) were run by no package.json script, no
 * manifest entry, no workflow step and no pytest file. Their controls and mutants could not go
 * red anywhere, and three of them could not even start in a checkout without the private
 * submodules. This gate's first run found three more of the class: the `--selftest` legs of
 * check:types:incremental and check:ci-proxy-image-smoke (both `local-only`) and of
 * check:env-credential-drift (no manifest gate). check:ci-standalone-selftests runs all seven
 * now; this gate is the sweep of the class, so the next one cannot land the same way.
 *
 * THE CORPUS, a selftest entry point: a tracked .ts/.mts/.js/.mjs/.cjs/.py/.sh file outside
 * a test directory whose basename says `selftest` (any of `selftest`, `self-test`,
 * `self_test`), or whose source handles a `--selftest` flag. A `test-*`/`test_*` control file
 * is not in it: check:ci-test-file-orphans owns that class, with rules of its own (the
 * `test_hooks_delegates.py` glob among them) that this gate does not repeat.
 *
 * THE RULE. Each must be REACHED from a CI root, transitively, along any of these edges:
 *
 *   ROOTS   the resolved leaves (`resolveInvocations`, the resolver check:ci-parity uses) of
 *           every gates.lock.json entry whose `ci.kind` is `step` or `test`; every pytest
 *           file under the `testpaths` pyproject.toml declares (check:ci-pytest runs them);
 *           and every workflow and composite-action YAML file.
 *   IMPORT  a relative TS/JS `import`/`export from`/`import()`/`require()`, and a Python
 *           `import`/`from ... import` (rediacc_ci and rediacc_hooks packages, relative
 *           imports, and a bare module beside the importer).
 *   NAME    a non-comment line of a reached file naming the target's path or basename as a
 *           token that ends at a quote, whitespace, a comma, a semicolon or the line end, or a
 *           dotted `rediacc_ci.`/`rediacc_hooks.` module name: the shape of a spawn, a
 *           `python3 -m` and an `importlib` call.
 *
 * WHICH WAY IT ERRS, on purpose. A false finding would push someone to wire or delete a file
 * that is in fact run, so every edge over-counts life: a NAME edge does not prove the reached
 * file executes the name, only that it could. What it guarantees is the floor that bit: a
 * selftest that NOTHING CI runs names, imports or spawns. A token followed by `)` or a
 * backtick is prose (`(scripts/x.ts)`, `` `x.ts` ``), and that exclusion is what keeps a
 * docstring that merely MENTIONS a selftest from certifying it, the exact shape that hid the
 * devcontainer driver's selftest behind a pytest docstring. Registration data (package.json,
 * the gate manifest, any .json) is never a NAME source: it names every script, local-only
 * ones included, and the lock's resolved leaves already read it structurally.
 *
 * BLIND SPOTS, stated so a green is not read as more than it is. The question is whether the
 * FILE is reached, not whether its `--selftest` leg runs: a gate leaf whose npm script never
 * passes `--selftest` is reached. And a reached file that names the target only to READ it
 * (a regex subject, a fixture table) still certifies it.
 *
 * THE CONTROLS. `--selftest` drives `entryPoints` and `reach` on an in-memory tree, both
 * directions: a planted selftest named by nothing, named only in a comment, or only in prose
 * is reported; one imported, spawned, or run as a `python3 -m` module is not. Every real run
 * also plants a ghost selftest into the real corpus and requires it to be reported before
 * the verdict on the tree counts.
 *
 * ---- gate ----
 * step: Selftest entry points are CI-reachable
 * needs: node, submodules
 * selftest: true
 * why: a selftest that no gate runs cannot go red in CI, and seven sat that way unnoticed.
 *      This refuses any selftest entry point nothing CI runs can reach
 * ---- end gate ----
 *
 * Usage:
 *   npx tsx scripts/gates/check-selftest-reachability.ts [--selftest]
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import {
  type ControlCase,
  refuse,
  refused,
  refuseIfEmpty,
  summarizeControls,
} from '../lib/controls.js';
import { isEntryPoint } from '../lib/entry-point.js';
import { REPO_ROOT } from '../lib/repo-root.js';
import { loadScripts, resolveInvocations } from './check-ci-parity.js';

const SOURCE_EXT = /\.(?:ts|mts|js|mjs|cjs|py|sh)$/;
const JS_EXT = /\.(?:ts|mts|js|mjs|cjs)$/;
const NAMED = /self[-_]?test/i;
/**
 * A `--selftest` flag the file itself HANDLES: an argv `includes`/comparison, a `case` arm, a
 * Python `in` test or argparse option, a shell `case` arm or `[[ $1 == --selftest ]]`.
 *
 * Not a bare quoted `'--selftest'`: that is how an INVOKER spells it too (a shim passing
 * `main(["--selftest"])`, a test spawning a gate), and measured on 2026-10-14 the bare form
 * pulled 23 invokers and docstrings into a corpus of 245 handlers.
 */
const HANDLES =
  /(?:includes|indexOf|has)\(\s*['"]--selftest['"]|[=!]==?\s*['"]--selftest['"]|['"]--selftest['"]\s*[=!]==?|case\s+['"]--selftest['"]|['"]--selftest['"]\s+(?:not\s+)?in\b|add_argument\(\s*['"]--selftest|--selftest\)|\[\[?\s+"?\$\{?\w+\}?"?\s+==?\s+"?--selftest/;
const TEST_PATH = /(^|\/)tests?\/|(^|\/)test_[^/]*\.py$|\.(?:test|spec)\.[cm]?[jt]s$/;
/** `test-*` and `test_*` control files are check:ci-test-file-orphans' corpus, judged by its own rules. */
const ORPHANS_GATE_NAME = /^test[-_].*\.(?:py|sh|ts)$/;
/** The lock kinds CI executes. `local-only` is run by `npm run ci` and by no runner. */
const CI_KINDS = new Set(['step', 'test']);
/** The Python package roots on sys.path (pyproject `pythonpath`, mypy_path). */
const PY_ROOTS = ['.ci', '.claude'];

/** Is this tracked file a selftest entry point? */
export function isSelftestEntry(file: string, text: string): boolean {
  if (!SOURCE_EXT.test(file) || TEST_PATH.test(file)) return false;
  if (ORPHANS_GATE_NAME.test(path.posix.basename(file))) return false;
  return NAMED.test(path.posix.basename(file)) || HANDLES.test(text);
}

/** The corpus: every selftest entry point among `tracked`. */
export function entryPoints(tracked: readonly string[], read: (f: string) => string): string[] {
  return tracked.filter((f) => SOURCE_EXT.test(f) && isSelftestEntry(f, read(f))).sort();
}

/** One reached file and the file that reached it, for the report. */
export interface Reach {
  reached: Map<string, string>;
}

const COMMENT = (file: string): RegExp =>
  JS_EXT.test(file) ? /^\s*(?:\/\/|\/\*|\*)/ : /^\s*#(?!!)/;

/** A path-shaped token, captured whole, ending where a spawn argument ends. */
const PATH_TOKEN =
  /(?<![\w.$/-])((?:[\w.@$/{}-]*\/)?[\w.-]+\.(?:ts|mts|js|mjs|cjs|py|sh))(?=["'\s,;]|$)/g;
const MODULE_TOKEN = /\b((?:rediacc_ci|rediacc_hooks)(?:\.\w+)+)/g;
/**
 * Registration DATA, never a NAME source. package.json and the gate manifest name every
 * script the repository has, local-only ones included, and they are already read
 * structurally through the lock's resolved leaves. Reached by an import (a gate that reads
 * the manifest, a test constant that imports package.json), they would otherwise certify
 * every file they mention: measured 2026-10-14, that edge alone counted the local-only
 * check:types:incremental and check:env-credential-drift leaves as CI-run.
 */
const DATA_SOURCE = /(?:^|\/)package\.json$|^scripts\/ci-runner\/manifest\.ts$|\.json$/;

/** The tracked file a dotted module names, trying it as a module, a package, and its parent. */
function resolveModule(mod: string, has: (f: string) => boolean, besideDir?: string): string[] {
  const out: string[] = [];
  const rel = mod.replace(/\./g, '/');
  const bases = [...PY_ROOTS, ''];
  if (besideDir !== undefined) bases.unshift(besideDir);
  for (const b of bases) {
    for (const c of [`${rel}.py`, `${rel}/__init__.py`, `${rel}/__main__.py`]) {
      const p = b ? path.posix.join(b, c) : c;
      if (has(p)) out.push(p);
    }
  }
  return out;
}

/** The Python files `text` imports. */
function pythonImports(file: string, text: string, has: (f: string) => boolean): string[] {
  const out: string[] = [];
  const dir = path.posix.dirname(file);
  const relBase = (dots: string): string => {
    let d = dir;
    for (let i = 1; i < dots.length; i++) d = path.posix.dirname(d);
    return d;
  };
  for (const m of text.matchAll(/^\s*from\s+(\.*)([\w.]*)\s+import\s+\(?([^)#\n]+)/gm)) {
    const [, dots, mod, names] = m;
    const parts = (names ?? '')
      .split(',')
      .map((n) => n.trim().split(/\s+/)[0] ?? '')
      .filter(Boolean);
    if (dots) {
      const base = relBase(dots);
      const stem = mod ? path.posix.join(base, mod.replace(/\./g, '/')) : base;
      for (const c of [`${stem}.py`, `${stem}/__init__.py`]) if (has(c)) out.push(c);
      for (const n of parts) if (has(`${stem}/${n}.py`)) out.push(`${stem}/${n}.py`);
      continue;
    }
    out.push(...resolveModule(mod ?? '', has, dir));
    for (const n of parts) out.push(...resolveModule(`${mod}.${n}`, has, dir));
  }
  for (const m of text.matchAll(/^\s*import\s+([\w., ]+)/gm)) {
    for (const piece of (m[1] ?? '').split(',')) {
      const mod = piece.trim().split(/\s+/)[0];
      if (mod) out.push(...resolveModule(mod, has, dir));
    }
  }
  return out;
}

// `tail` holds no blanks, so `for await` reads `forawait` there.
const COND_HEAD = /(?:^|[^\w$.])(?:if|while|for(?:await)?|with)$/;

/** Whether a `/` after `tail` (the last non-blank characters of the code so far, empty at the start) starts a regex literal rather than dividing: true at the start, after an operator or opener, after a keyword that takes an operand, and after the `)` closing an `if`/`while`/`for`/`for await`/`with` head (`condClose`); false after a postfix `++`/`--`, a value, or any other `)` or `]`. */
function regexAllowed(tail: string, condClose: boolean): boolean {
  if (tail === '') return true;
  const last = tail[tail.length - 1] as string;
  if (last === ')') return condClose;
  if ((last === '+' || last === '-') && tail[tail.length - 2] === last) return false;
  if ('(,=:[!&|?{};+-*%<>~^'.includes(last)) return true;
  return /(?:^|[^\w$.])(?:return|typeof|case|in|of|void|delete|throw|yield|await|else|do)$/.test(
    tail
  );
}

/** The index just past the regex literal opening at `start`, or past the `/` alone when the line holds no closing one. */
function regexEnd(text: string, start: number): number {
  let inClass = false;
  for (let i = start + 1; i < text.length; i++) {
    const c = text[i];
    if (c === '\n') return start + 1;
    if (c === '\\') i++;
    else if (c === '[') inClass = true;
    else if (c === ']') inClass = false;
    else if (c === '/' && !inClass) return i + 1;
  }
  return start + 1;
}

/**
 * `text` with its JS/TS comments blanked (newlines kept), found by one scan that tracks string state. A commented-out import is no edge; a `//` or `/*` inside a quoted string or template (a glob path, a URL) opens nothing; a `/*` inside a line comment opens nothing; `\r` does not stop a line comment from ending at its `\n`. A regex literal (a `/` where an expression may start) is copied whole, so `/https?:\/\//` opens no comment. A quote left open at a line end closes there, so a stray apostrophe in a regex literal cannot swallow the rest of the file.
 */
export function stripJsComments(text: string): string {
  let out = '';
  let i = 0;
  let quote = '';
  let tail = '';
  let condClose = false;
  const heads: boolean[] = [];
  const emit = (piece: string): void => {
    out += piece;
    tail = (tail + piece).trimEnd().slice(-16);
  };
  const blank = (s: string): string => s.replace(/[^\n]/g, ' ');
  while (i < text.length) {
    const c = text[i] as string;
    const two = text.slice(i, i + 2);
    if (quote) {
      if (c === '\\') {
        emit(text.slice(i, i + 2));
        i += 2;
        continue;
      }
      if (c === quote || (c === '\n' && quote !== '`')) quote = '';
      emit(c);
      i++;
    } else if (c === '/' && two !== '//' && two !== '/*' && regexAllowed(tail, condClose)) {
      const stop = regexEnd(text, i);
      emit(text.slice(i, stop));
      i = stop;
    } else if (two === '//') {
      const end = text.indexOf('\n', i);
      const stop = end === -1 ? text.length : end;
      emit(blank(text.slice(i, stop)));
      i = stop;
    } else if (two === '/*') {
      const end = text.indexOf('*/', i + 2);
      const stop = end === -1 ? text.length : end + 2;
      emit(blank(text.slice(i, stop)));
      i = stop;
    } else {
      if (c === "'" || c === '"' || c === '`') quote = c;
      if (c === '(') heads.push(COND_HEAD.test(tail));
      else if (c === ')') condClose = heads.pop() ?? false;
      emit(c);
      i++;
    }
  }
  return out;
}

/** The JS/TS files `text` imports by a relative specifier. */
function jsImports(file: string, text: string, has: (f: string) => boolean): string[] {
  const out: string[] = [];
  const dir = path.posix.dirname(file);
  const spec =
    /(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*|\bnew\s+URL\s*\(\s*)['"](\.{1,2}\/[^'"]+)['"]/g;
  const code = stripJsComments(text);
  for (const m of code.matchAll(spec)) {
    const p = path.posix.normalize(path.posix.join(dir, m[1] ?? ''));
    const stem = p.replace(/\.[cm]?js$/, '');
    for (const c of [
      p,
      `${stem}.ts`,
      `${stem}.mts`,
      `${stem}.tsx`,
      `${stem}.js`,
      `${stem}.mjs`,
      `${stem}/index.ts`,
      `${stem}/index.js`,
    ]) {
      if (has(c)) out.push(c);
    }
  }
  return out;
}

/**
 * Every tracked file reachable from `roots` along IMPORT and NAME edges.
 *
 * @param roots The files CI runs directly.
 * @param tracked Every tracked path.
 * @param read The text of a tracked path ('' when unreadable).
 */
export function reach(
  roots: Iterable<string>,
  tracked: readonly string[],
  read: (f: string) => string
): Map<string, string> {
  const set = new Set(tracked);
  const has = (f: string): boolean => set.has(f);
  const byBase = new Map<string, string[]>();
  for (const f of tracked) {
    const b = path.posix.basename(f);
    byBase.set(b, [...(byBase.get(b) ?? []), f]);
  }
  const reached = new Map<string, string>();
  const queue: string[] = [];
  const visit = (f: string, from: string): void => {
    if (!has(f) || reached.has(f)) return;
    reached.set(f, from);
    queue.push(f);
  };
  for (const r of roots) visit(r, '(root)');
  while (queue.length > 0) {
    const f = queue.shift() as string;
    const text = read(f);
    if (!text) continue;
    if (JS_EXT.test(f)) for (const t of jsImports(f, text, has)) visit(t, f);
    if (f.endsWith('.py')) for (const t of pythonImports(f, text, has)) visit(t, f);
    if (DATA_SOURCE.test(f)) continue;
    const comment = COMMENT(f);
    for (const line of text.split('\n')) {
      if (comment.test(line)) continue;
      for (const m of line.matchAll(PATH_TOKEN)) {
        const segs = (m[1] ?? '').split('/');
        const base = segs[segs.length - 1] ?? '';
        // The trailing run of literal segments: `$ROOT/.ci/x.sh` and `../lib/x.ts` name `.ci/x.sh` and `lib/x.ts`.
        let i = segs.length - 1;
        while (i > 0 && /^[\w.-]+$/.test(segs[i - 1] ?? '') && !/^\.\.?$/.test(segs[i - 1] ?? ''))
          i--;
        const tail = segs.slice(i).join('/');
        for (const cand of byBase.get(base) ?? []) {
          // A token with directories names files whose path ends with them; a bare basename names every file of that name.
          if (cand === tail || cand.endsWith(`/${tail}`)) visit(cand, f);
        }
      }
      for (const m of line.matchAll(MODULE_TOKEN)) {
        for (const t of resolveModule(m[1] ?? '', has)) visit(t, f);
      }
    }
  }
  return reached;
}

/** The pytest `testpaths` pyproject.toml declares. */
export function pytestPaths(pyproject: string): string[] {
  const m = /^testpaths\s*=\s*\[([^\]]*)\]/m.exec(pyproject);
  if (!m) return [];
  return [...(m[1] ?? '').matchAll(/"([^"]+)"/g)].map((x) => (x[1] ?? '').replace(/\/$/, ''));
}

interface LockEntry {
  id: string;
  run: string;
  ci?: { kind?: string };
}

/** The real roots: CI-run lock leaves, pytest files, and the workflow and action YAML. */
function realRoots(root: string, tracked: readonly string[]): string[] {
  const lock = JSON.parse(
    fs.readFileSync(path.join(root, 'scripts/ci-runner/gates.lock.json'), 'utf8')
  ) as LockEntry[];
  const u = loadScripts(root);
  const out = new Set<string>();
  const ciEntries = lock.filter((e) => CI_KINDS.has(e.ci?.kind ?? ''));
  refuseIfEmpty(ciEntries, 'gates.lock.json entries with ci.kind step|test', 'Is the lock empty?');
  for (const e of ciEntries) {
    for (const inv of resolveInvocations(e.run, u)) out.add(inv.leaf);
  }
  const testpaths = refuseIfEmpty(
    pytestPaths(fs.readFileSync(path.join(root, 'pyproject.toml'), 'utf8')),
    'pyproject.toml [tool.pytest.ini_options] testpaths',
    'The testpaths line moved or changed shape, so the pytest roots cannot be read.'
  );
  for (const f of tracked) {
    const base = path.posix.basename(f);
    const underTests = testpaths.some((t) => f.startsWith(`${t}/`));
    if (underTests && f.endsWith('.py') && (/^test_/.test(base) || base === 'conftest.py')) {
      out.add(f);
    }
    if (/^\.github\/(?:workflows|actions)\/.*\.ya?ml$/.test(f)) out.add(f);
  }
  return [...out];
}

function selftestCases(): ControlCase[] {
  const files: Record<string, string> = {
    'package.json': '',
    '.github/workflows/ci.yml': 'steps:\n  - run: tsx scripts/gates/check-a.ts\n',
    'scripts/ci-runner/manifest.ts': "run: 'tsx scripts/lib/registered-selftest.ts',\n",
    'scripts/lib/registered-selftest.ts': 'console.log(1);\n',
    'scripts/gates/check-a.ts': [
      "import { GATES } from '../ci-runner/manifest.js';",
      "import { x } from '../lib/imported-selftest.js';",
      '// spawns scripts/lib/commented-selftest.ts, in a comment only',
      "// import { y } from '../lib/commented-import-selftest.js';",
      '/* a block comment whose interior lines carry no marker:',
      "import { z } from '../lib/block-commented-selftest.js';",
      '*/',
      "run(); // import { w } from '../lib/trailing-commented-selftest.js';",
      "const glob = './src/**/*.ts'; /* closes later */",
      '// see /* notes, a line comment that opens no block',
      "import { real } from '../lib/after-line-comment-selftest.js';",
      "const note = 'a */ b'; /* swallowed? */",
      "x=/* import './nowhere.js' */ 1;",
      "const u = ' //'; import q from '../lib/after-string-slashes-selftest.js';",
      "const g = './a/*/*.ts'; import r from '../lib/after-glob-selftest.js';",
      'const crlf = 1; // import { c } from "../lib/crlf-commented-selftest.js";\r',
      "const run = spawnSync('tsx', [path.join(ROOT, 'scripts/lib/spawned-selftest.ts')]);",
      'process.argv.includes("--selftest");',
    ].join('\n'),
    'scripts/lib/imported-selftest.ts': 'export const x = 1;\n',
    'scripts/lib/spawned-selftest.ts': 'console.log(1);\n',
    'scripts/lib/commented-selftest.ts': 'console.log(1);\n',
    'scripts/lib/commented-import-selftest.ts': 'console.log(1);\n',
    'scripts/lib/block-commented-selftest.ts': 'console.log(1);\n',
    'scripts/lib/trailing-commented-selftest.ts': 'console.log(1);\n',
    'scripts/lib/after-line-comment-selftest.ts': 'console.log(1);\n',
    'scripts/lib/after-string-slashes-selftest.ts': 'console.log(1);\n',
    'scripts/lib/after-glob-selftest.ts': 'console.log(1);\n',
    'scripts/lib/crlf-commented-selftest.ts': 'console.log(1);\n',
    'scripts/lib/orphan-selftest.ts': 'console.log(1);\n',
    'scripts/lib/prose-selftest.ts': 'console.log(1);\n',
    'scripts/lib/handler.ts': "if (process.argv.includes('--selftest')) run();\n",
    'scripts/lib/handler-run.ts': "if (process.argv[2] === '--selftest') run();\n",
    '.ci/rediacc_ci/tests/test_x.py': [
      '"""The selftest (scripts/lib/prose-selftest.ts) proves this."""',
      'from rediacc_ci.quality import mod_a',
      'subprocess.run(["python3", "-m", "rediacc_ci.quality.mod_b", "--selftest"])',
      'subprocess.run(["bash", ROOT / "scripts/lib/handler-run.ts"])',
    ].join('\n'),
    '.ci/rediacc_ci/quality/mod_a.py': 'if "--selftest" in sys.argv: pass\n',
    '.ci/rediacc_ci/quality/mod_b.py': 'if "--selftest" in sys.argv: pass\n',
    '.ci/rediacc_ci/quality/mod_c.py': 'if "--selftest" in sys.argv: pass\n',
  };
  const tracked = Object.keys(files);
  const read = (f: string): string => files[f] ?? '';
  const corpus = entryPoints(tracked, read);
  const reached = reach(
    ['.github/workflows/ci.yml', '.ci/rediacc_ci/tests/test_x.py'],
    tracked,
    read
  );
  const unreached = new Set(corpus.filter((f) => !reached.has(f)));
  const cases: ControlCase[] = [];
  const expect = (f: string, red: boolean, why: string): void => {
    cases.push({
      name: `${red ? 'reported' : 'not reported'}: ${why} (${f})`,
      ok: corpus.includes(f) && unreached.has(f) === red,
      detail: `in corpus=${corpus.includes(f)} unreached=${unreached.has(f)}`,
    });
  };
  expect('scripts/lib/orphan-selftest.ts', true, 'a selftest nothing names');
  expect(
    'scripts/lib/registered-selftest.ts',
    true,
    'a selftest only the manifest names, reached through a gate that imports the manifest'
  );
  expect('scripts/lib/commented-selftest.ts', true, 'a selftest named only in a comment');
  expect(
    'scripts/lib/commented-import-selftest.ts',
    true,
    'a selftest imported only by a commented-out import'
  );
  expect(
    'scripts/lib/block-commented-selftest.ts',
    true,
    'a selftest imported only inside a block comment'
  );
  expect(
    'scripts/lib/trailing-commented-selftest.ts',
    true,
    'a selftest imported only in a trailing line comment'
  );
  expect(
    'scripts/lib/crlf-commented-selftest.ts',
    true,
    'a selftest imported only in a trailing comment on a CRLF line'
  );
  expect(
    'scripts/lib/after-line-comment-selftest.ts',
    false,
    'an import after a line comment that holds a block opener'
  );
  expect(
    'scripts/lib/after-string-slashes-selftest.ts',
    false,
    'an import after a string that holds two slashes'
  );
  expect('scripts/lib/after-glob-selftest.ts', false, 'an import after a glob string');
  cases.push({
    name: 'a block opener after = , in a glob string, or in a line comment is read by string state',
    ok:
      !stripJsComments("x=/* import './a' */ 1;").includes("'./a'") &&
      stripJsComments("const g = './s/*/*.ts'; import './b.js';").includes("'./b.js'") &&
      stripJsComments('// see /* a\nimport "./c.js";').includes('"./c.js"'),
  });
  cases.push({
    name: 'a regex literal holding // does not blank the rest of its line, and a division is not one',
    ok:
      stripJsComments("const r = /https?:\\/\\//; import './d.js';").includes("'./d.js'") &&
      stripJsComments("const q = a / b; // import './e.js'").includes("'./e.js'") === false &&
      stripJsComments("x = [/\\//, 1]; import './f.js';").includes("'./f.js'"),
  });
  cases.push({
    name: 'a division after a postfix ++ or -- is not a regex, and a regex after an if/while head or else/do is',
    ok:
      !stripJsComments("n = i++ / 2; // import './g.js'").includes("'./g.js'") &&
      !stripJsComments("n = i-- / 2; // import './g.js'").includes("'./g.js'") &&
      !stripJsComments("n = (a + b) / 2; // import './g.js'").includes("'./g.js'") &&
      !stripJsComments("n = a[0] / 2; // import './g.js'").includes("'./g.js'") &&
      stripJsComments("if (ok) /https?:\\/\\//.test(s); import './g.js';").includes("'./g.js'") &&
      stripJsComments("else /https?:\\/\\//.test(s); import './g.js';").includes("'./g.js'") &&
      stripJsComments("do /a\\/\\//.test(s); import './g.js';").includes("'./g.js'"),
  });
  cases.push({
    name: 'a regex after a for await head is a regex, so its // does not blank the rest of the line',
    ok:
      stripJsComments("for await (const x of y) /a\\/\\//.test(x); import './h.js';").includes(
        "'./h.js'"
      ) && !stripJsComments("n = (a) / 2; // import './h.js'").includes("'./h.js'"),
  });
  cases.push({
    name: 'regexAllowed reads backward: eight times the text costs far less than eight times squared',
    ok: (() => {
      // Linear cost scales ~8x from 5000 to 40000 lines, quadratic ~64x; a ratio holds on a loaded runner where a wall-clock limit would not.
      // The two sizes are timed INTERLEAVED, best of 9 each: with best of 3 run back to back, a pre-push pool at 19 cores reddened this once (2026-10-19, rc=0 on three reruns alone) because the large size's three samples all landed in one contended stretch the small size never saw.
      const small = 'x = a / 2;\n'.repeat(5000);
      const large = 'x = a / 2;\n'.repeat(40000);
      const time = (text: string): number => {
        const t0 = process.hrtime.bigint();
        stripJsComments(text);
        return Number(process.hrtime.bigint() - t0) / 1e6;
      };
      let bestSmall = Number.POSITIVE_INFINITY;
      let bestLarge = Number.POSITIVE_INFINITY;
      for (let k = 0; k < 9; k++) {
        bestSmall = Math.min(bestSmall, time(small));
        bestLarge = Math.min(bestLarge, time(large));
      }
      return bestLarge < 24 * Math.max(bestSmall, 1);
    })(),
  });
  expect('scripts/lib/prose-selftest.ts', true, 'a selftest named only in parenthesised prose');
  expect('.ci/rediacc_ci/quality/mod_c.py', true, 'a --selftest handler nothing imports');
  expect('scripts/lib/handler.ts', true, 'a --selftest handler nothing names');
  expect('scripts/lib/imported-selftest.ts', false, 'a selftest a reached file imports');
  expect('scripts/lib/spawned-selftest.ts', false, 'a selftest a reached file spawns');
  expect('.ci/rediacc_ci/quality/mod_a.py', false, 'a handler a pytest file imports');
  expect('.ci/rediacc_ci/quality/mod_b.py', false, 'a handler run as python3 -m');
  expect('scripts/lib/handler-run.ts', false, 'a handler a pytest file names as a path');
  expect('scripts/gates/check-a.ts', false, 'a gate the workflow runs');
  cases.push({
    name: 'a file with no selftest name and no --selftest handling is not in the corpus',
    ok: !corpus.includes('.ci/rediacc_ci/tests/test_x.py') && !corpus.includes('package.json'),
    detail: corpus.join(', '),
  });
  cases.push({
    name: 'an INVOKER passing "--selftest" to another script is not a selftest entry point',
    ok: !isSelftestEntry('scripts/lib/invoker.ts', "spawnSync('tsx', ['x.ts', '--selftest']);"),
  });
  cases.push({
    name: 'a test-*.py control file is left to check:ci-test-file-orphans',
    ok: !isSelftestEntry('.claude/hooks/stop/test-x.py', 'if "--selftest" in sys.argv: pass'),
  });
  cases.push({
    name: 'a shell case arm and a [[ $1 == --selftest ]] test are handlers',
    ok:
      isSelftestEntry('.ci/scripts/a.sh', 'case "$1" in\n  --selftest) run ;;\nesac') &&
      isSelftestEntry('.ci/scripts/b.sh', 'if [[ "$1" == "--selftest" ]]; then run; fi'),
  });
  cases.push({
    name: 'pytestPaths reads the testpaths list',
    ok:
      pytestPaths('[x]\ntestpaths = [\n    "a/tests",\n    "b/tests/",\n]\n').join(',') ===
      'a/tests,b/tests',
    detail: pytestPaths('testpaths = [\n "a/tests",\n]').join(','),
  });
  return cases;
}

function main(argv: string[]): number {
  if (argv.includes('--selftest')) return summarizeControls(selftestCases());

  const root = REPO_ROOT;
  const tracked = execFileSync('git', ['-C', root, 'ls-files'], {
    encoding: 'utf8',
    maxBuffer: 256 * 1024 * 1024,
  })
    .split('\n')
    .filter(Boolean);
  const cache = new Map<string, string>();
  const read = (f: string): string => {
    let t = cache.get(f);
    if (t === undefined) {
      try {
        const p = path.join(root, f);
        t = fs.statSync(p).isFile() ? fs.readFileSync(p, 'utf8') : '';
      } catch {
        t = '';
      }
      cache.set(f, t);
    }
    return t;
  };

  const corpus = refuseIfEmpty(
    entryPoints(tracked, read),
    'tracked selftest entry points',
    'No file is named *selftest* or handles --selftest: the predicate or the listing broke.'
  );
  const roots = realRoots(root, tracked);
  const reached = reach(roots, tracked, read);

  // Control on the real tree: a ghost selftest no file names must be reported.
  // Built so no literal in this file spells its basename: this file is a root, and a literal would be a NAME edge that reaches the ghost (the control caught exactly that on its first run).
  const ghost = `scripts/lib/${['__ghost__', 'selftest'].join('-')}.ts`;
  const ghostTracked = [...tracked, ghost];
  const ghostRead = (f: string): string => (f === ghost ? 'console.log(1);\n' : read(f));
  const ghostCorpus = entryPoints([ghost], ghostRead);
  const ghostReached = reach(roots, ghostTracked, ghostRead);
  if (ghostCorpus.length !== 1 || ghostReached.has(ghost)) {
    refuse(
      `✗ instrument control did not fire: a planted ${ghost} that nothing names was`,
      `  ${ghostCorpus.length !== 1 ? 'not taken into the corpus' : 'counted as reached'}, so a green run here would mean nothing.`
    );
  }

  const unreached = corpus.filter((f) => !reached.has(f));
  const named = corpus.filter((f) => NAMED.test(path.posix.basename(f))).length;
  if (unreached.length > 0) {
    return refused(
      `✗ ${unreached.length} selftest entry point(s) that nothing CI runs can reach:`,
      ...unreached.map((f) => `    ${f}`),
      '',
      '  An unrun selftest reads exactly like a passing one: its controls cannot go red.',
      '  Wire it: name it in scripts/gates/check-standalone-selftests.ts SELFTESTS, run it from',
      '  a gate of its own (a gate header, then `npm run gate:bind -- --write`), import it from',
      '  a file a gate runs, or drive it from a pytest file. If nothing should run it, it is',
      '  dead code: delete it.'
    );
  }
  console.log(
    `✓ ${corpus.length} selftest entry points all CI-reachable (${named} named *selftest*, ` +
      `${corpus.length - named} handling --selftest; ${roots.length} roots, ${reached.size} files reached; ` +
      'ghost control fired)'
  );
  return 0;
}

if (isEntryPoint(import.meta.url)) process.exit(main(process.argv.slice(2)));
