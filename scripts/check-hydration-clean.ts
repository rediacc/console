#!/usr/bin/env tsx
/**
 * A React island's INITIAL state must not depend on whether it is running in a browser.
 *
 * THE DEFECT. `packages/www/src/components/InstallMethods.tsx` opens its state with
 * `useState(() => { if (typeof window === 'undefined') return 'all'; ... })`. The server
 * renders "All Methods"; the browser, running the same initializer with a `window`,
 * computes the detected platform instead. React compares the two, finds the trees differ,
 * and DISCARDS the whole server-rendered `<InstallMethods>` subtree, re-rendering it from
 * scratch. On production this is the only JavaScript error on the entire site, and
 * `/install` is the page a new user is sent to.
 *
 * WHY THE PATTERN IS SO EASY TO WRITE. `typeof window === 'undefined'` is the correct
 * guard almost everywhere else -- in an effect, an event handler, a module-level helper
 * that runs after mount. It is wrong in exactly one place: the argument to `useState` or
 * `useReducer`, which is the one expression whose result BOTH sides must agree on. So the
 * rule here is narrow on purpose. It fires on the initializer and nowhere else, because a
 * gate that flagged every SSR guard would be suppressed the same week it landed.
 *
 * IT FOLLOWS ONE HOP, AND THAT IS NOT A FLOURISH. `ThemeToggle.tsx` passes a bare function
 * reference -- `useState<Theme>(getInitialTheme)` -- and the `typeof document` branch sits
 * inside `getInitialTheme` twelve lines above. A gate that only read the argument TEXT
 * would have reported InstallMethods and called it done, which is how a class gets fixed
 * one instance at a time. Following the identifiers named in the argument to their
 * module-level definitions is what turns one finding into the four that are really there.
 *
 * WHY STATIC, NOT A BROWSER RUN. The mismatch is decidable from the source: an initializer
 * whose value is a function of `typeof window` cannot agree across the two renders. A
 * browser check would need the page built, served and hydrated, would only cover the
 * routes it was pointed at, and would report the SYMPTOM (a discarded tree) rather than
 * the line to change.
 *
 * Usage:
 *   tsx scripts/check-hydration-clean.ts [--root <dir>] [--selftest]
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SOURCE_DIR = 'packages/www/src';

/** The hooks whose first argument IS the initial state both renders must agree on. */
const STATE_HOOKS = ['useState', 'useReducer'];

/** The environment tests that make an expression render-context dependent. */
const ENV_TEST = /typeof\s+(window|document|navigator|localStorage|sessionStorage)\s*[!=]==?/;

/** A tree with fewer components than this is not a clean tree, it is a broken glob. */
const MIN_FILES = 20;

export interface HydrationFinding {
  file: string;
  line: number;
  hook: string;
  via: string | null;
  excerpt: string;
}

function walk(dir: string, out: string[] = []): string[] {
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs
    .readdirSync(dir, { withFileTypes: true })
    .sort((a, b) => a.name.localeCompare(b.name))) {
    if (entry.name.startsWith('.') || entry.name === 'node_modules') continue;
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(abs, out);
    else if (entry.name.endsWith('.tsx')) out.push(abs);
  }
  return out;
}

/**
 * The arguments of a call starting at `open` (the index of its `(`), split at top level.
 *
 * Balanced-delimiter scan rather than a regex, because a `useState` initializer routinely
 * contains parentheses, braces, arrow functions and object literals. It also tracks
 * strings and template literals so a `')'` or a `','` inside a message cannot split the
 * argument early.
 */
function callArguments(src: string, open: number): string[] {
  const args: string[] = [];
  let depth = 0;
  let start = open + 1;
  let quote: string | null = null;
  for (let i = open; i < src.length; i++) {
    const c = src[i];
    if (quote) {
      if (c === '\\') i++;
      else if (c === quote) quote = null;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') {
      quote = c;
      continue;
    }
    if (c === '(' || c === '[' || c === '{') depth++;
    else if (c === ')' || c === ']' || c === '}') {
      depth--;
      if (depth === 0) {
        args.push(src.slice(start, i));
        break;
      }
    } else if (c === ',' && depth === 1) {
      args.push(src.slice(start, i));
      start = i + 1;
    }
  }
  return args;
}

/** The balanced body starting at `open`, used for a function's `{ ... }`. */
function balancedBody(src: string, open: number): string {
  return callArguments(src, open).join(',');
}

/**
 * Which arguments of a hook call ARE the initial state.
 *
 * `useState(init)` -- the first. `useReducer(reducer, initialArg, init?)` -- the SECOND
 * and third; the first is the reducer, which runs only on dispatch and may legitimately
 * touch the environment. Reading argument one for both was the first version's bug, and
 * the useReducer control caught it: the scan saw only `reducer` and reported nothing.
 */
const STATE_ARG_INDICES: Record<string, number[]> = {
  useState: [0],
  useReducer: [1, 2],
};

/** Module-level (or file-level) function bodies, by name, for the one-hop lookup. */
function namedFunctionBodies(src: string): Map<string, string> {
  const out = new Map<string, string>();
  const patterns = [
    /function\s+([A-Za-z_$][\w$]*)\s*\(/g,
    /(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*(?::[^=]+)?=>/g,
  ];
  for (const re of patterns) {
    for (const m of src.matchAll(re)) {
      const brace = src.indexOf('{', m.index! + m[0].length - 1);
      if (brace < 0) continue;
      // A body that starts more than 200 characters after the signature is not this
      // function's body; a concise arrow body has none at all.
      if (brace - (m.index! + m[0].length) > 200) continue;
      out.set(m[1], balancedBody(src, brace));
    }
  }
  return out;
}

const lineOf = (src: string, index: number): number => src.slice(0, index).split('\n').length;

export function scanSource(src: string, file: string): HydrationFinding[] {
  const findings: HydrationFinding[] = [];
  const bodies = namedFunctionBodies(src);

  for (const hook of STATE_HOOKS) {
    // `useState<Theme>(` and `useState(` both, and never `myUseState(`.
    const re = new RegExp(`\\b${hook}\\s*(?:<[^(<>]*>)?\\s*\\(`, 'g');
    for (const m of src.matchAll(re)) {
      const open = src.indexOf('(', m.index! + m[0].length - 1);
      const args = callArguments(src, open);
      const arg = (STATE_ARG_INDICES[hook] ?? [0]).map((i) => args[i] ?? '').join('\n');
      if (arg.trim() === '') continue;

      if (ENV_TEST.test(arg)) {
        findings.push({
          file,
          line: lineOf(src, m.index!),
          hook,
          via: null,
          excerpt: arg.replace(/\s+/g, ' ').trim().slice(0, 110),
        });
        continue;
      }

      // ONE HOP. Any identifier the argument names -- called or passed bare -- whose
      // module-level body tests the environment makes this initializer environment
      // dependent just as surely as an inline test would.
      for (const ident of new Set(arg.match(/[A-Za-z_$][\w$]*/g) ?? [])) {
        const body = bodies.get(ident);
        if (body && ENV_TEST.test(body)) {
          findings.push({
            file,
            line: lineOf(src, m.index!),
            hook,
            via: ident,
            excerpt: arg.replace(/\s+/g, ' ').trim().slice(0, 110),
          });
          break;
        }
      }
    }
  }
  return findings;
}

function selftest(): boolean {
  const failures: string[] = [];
  const check = (name: string, ok: boolean, detail = '') => {
    if (ok) console.log(`  PASS  ${name}`);
    else {
      console.error(`  FAIL  ${name}${detail ? `\n        ${detail}` : ''}`);
      failures.push(name);
    }
  };

  // THE PLANT: the exact shape from InstallMethods.tsx:134.
  const PLANT = `const C = () => {
  const [filter, setFilter] = useState<FilterTab>(() => {
    if (typeof window === 'undefined') return 'all';
    return detectPlatform();
  });
  return <div>{filter}</div>;
};`;
  const planted = scanSource(PLANT, 'Planted.tsx');
  check(
    'a `typeof window` branch in a useState initializer is reported',
    planted.length === 1 && planted[0].via === null,
    JSON.stringify(planted)
  );

  const INDIRECT = `function getInitialTheme(): Theme {
  if (typeof document !== 'undefined') {
    const current = document.documentElement.dataset.theme;
    if (current === 'dark') return current;
  }
  return 'light';
}
const T = () => {
  const [theme, setTheme] = useState<Theme>(getInitialTheme);
  return <button>{theme}</button>;
};`;
  const indirect = scanSource(INDIRECT, 'Indirect.tsx');
  check(
    'a bare function reference whose body tests the environment is reported',
    indirect.length === 1 && indirect[0].via === 'getInitialTheme',
    JSON.stringify(indirect)
  );

  const REDUCER = `const R = () => {
  const [s, d] = useReducer(reducer, typeof window === 'undefined' ? null : window.name);
  return <i>{s}</i>;
};`;
  check('useReducer is covered too', scanSource(REDUCER, 'R.tsx').length === 1);

  // ---- CONTROLS THAT MUST NOT FIRE ------------------------------------------------
  const EFFECT = `const C = () => {
  const [x, setX] = useState(false);
  useEffect(() => {
    if (typeof window === 'undefined') return;
    setX(window.innerWidth > 900);
  }, []);
  return <div>{String(x)}</div>;
};`;
  check(
    'an SSR guard inside useEffect is NOT reported (control)',
    scanSource(EFFECT, 'Effect.tsx').length === 0,
    JSON.stringify(scanSource(EFFECT, 'Effect.tsx'))
  );

  const HANDLER = `const C = () => {
  const [x, setX] = useState(0);
  const onClick = () => { if (typeof window !== 'undefined') setX(window.scrollY); };
  return <button onClick={onClick}>{x}</button>;
};`;
  check(
    'an SSR guard inside an event handler is NOT reported (control)',
    scanSource(HANDLER, 'Handler.tsx').length === 0
  );

  const HELPER_NOT_USED = `function getStored() {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem('k');
}
const C = () => {
  const [x, setX] = useState<string | null>(null);
  useEffect(() => { setX(getStored()); }, []);
  return <div>{x}</div>;
};`;
  check(
    'a guarded helper NOT reached from an initializer is not reported (control)',
    scanSource(HELPER_NOT_USED, 'Helper.tsx').length === 0,
    JSON.stringify(scanSource(HELPER_NOT_USED, 'Helper.tsx'))
  );

  const PARENS = `const C = () => {
  const [x] = useState(() => build({ msg: 'a ) b', n: (1 + 2) }));
  return <i>{x}</i>;
};`;
  check(
    'an initializer full of parentheses and strings does not confuse the scan (control)',
    scanSource(PARENS, 'Parens.tsx').length === 0
  );

  const OTHER_HOOK = `const C = () => {
  const v = useMemoLike(() => typeof window === 'undefined');
  return <i>{String(v)}</i>;
};`;
  check(
    'a hook that is not useState/useReducer is not judged (control)',
    scanSource(OTHER_HOOK, 'Other.tsx').length === 0
  );

  // The scanner must survive a real file without throwing, and the walker must find files.
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'hydration-'));
  fs.writeFileSync(path.join(tmp, 'A.tsx'), PLANT);
  check('the walker finds .tsx files on disk', walk(tmp).length === 1);
  fs.rmSync(tmp, { recursive: true, force: true });

  if (failures.length > 0) {
    console.error(`\n✗ ${failures.length} self-test failure(s)`);
    return false;
  }
  return true;
}

function main(): void {
  const argv = process.argv.slice(2);
  const arg = (name: string): string | undefined => {
    const i = argv.indexOf(name);
    return i >= 0 ? argv[i + 1] : undefined;
  };

  if (argv.includes('--selftest')) process.exit(selftest() ? 0 : 1);
  if (!argv.includes('--skip-control') && !selftest()) process.exit(1);

  const base = path.resolve(arg('--root') ?? REPO_ROOT);
  const dir = path.join(base, SOURCE_DIR);
  if (!fs.existsSync(dir)) {
    console.error(`✗ Refusing to run: ${dir} does not exist.`);
    process.exit(1);
  }

  const files = walk(dir);
  if (files.length < MIN_FILES) {
    console.error(
      `✗ Refusing to run: only ${files.length} .tsx file(s) under ${dir}, below the floor of ` +
        `${MIN_FILES}.\n  Zero findings over an empty glob reads exactly like a clean tree.`
    );
    process.exit(1);
  }

  const findings: HydrationFinding[] = [];
  for (const file of files) {
    findings.push(...scanSource(fs.readFileSync(file, 'utf-8'), path.relative(base, file)));
  }

  if (findings.length === 0) {
    console.log(
      `✓ No environment-dependent state initializers across ${files.length} React component(s).`
    );
    return;
  }

  console.error(
    `✗ ${findings.length} state initializer(s) compute a different value on the server than in ` +
      `the browser, across ${files.length} component(s):\n`
  );
  for (const f of findings) {
    const via = f.via ? ` via ${f.via}()` : '';
    console.error(`  ${f.file}:${f.line}  ${f.hook}${via}`);
    console.error(`    ${f.excerpt}`);
  }
  console.error(
    '\nReact compares the server HTML with the first client render. When the initial state\n' +
      'differs it DISCARDS the whole subtree, so the island silently re-renders from scratch\n' +
      'and any server-rendered content inside it is thrown away.\n' +
      'Fix: give the initializer ONE value both renders agree on (the server value), then move\n' +
      'the browser-only refinement into a useEffect that runs after mount.'
  );
  process.exit(1);
}

main();
