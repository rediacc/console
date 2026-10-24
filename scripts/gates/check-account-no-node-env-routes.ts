/**
 * check:ci-account-no-node-env-routes -- account route handlers do not branch
 * on NODE_ENV.
 *
 * WHY THIS REPLACED A GREP. The old gate was an inline
 * `! grep -rn 'process.env.NODE_ENV' private/account/src/routes/ && echo OK`.
 * A missing routes directory is a grep error, and a negated error is a pass;
 * the dotted spelling alone also misses `process.env['NODE_ENV']` and a
 * destructured `const { NODE_ENV } = process.env`.
 *
 * THE RULE. No .ts file under private/account/src/routes mentions
 * `process.env.NODE_ENV`, `process.env['NODE_ENV']` or `{ NODE_ENV } =
 * process.env`. Comments count: the over-match is deliberate, a route file has
 * no reason to name it. The directory must exist and hold at least MIN_FILES
 * route files, or the gate refuses (a moved directory is not a clean tree).
 *
 * ---- gate ----
 * step: Assert no NODE_ENV branching in account routes
 * needs: node, submodules
 * lane: quality-go
 * selftest: true
 * ---- end gate ----
 */

import fs from 'node:fs';
import path from 'node:path';
import { isEntryPoint } from '../lib/entry-point.js';

const ROOT = path.resolve(import.meta.dirname, '..', '..');
const ROUTES = 'private/account/src/routes';
const MIN_FILES = 10;

// `?.` counts as a dot everywhere: process.env?.NODE_ENV and process?.env?.['NODE_ENV'] read the same value.
const PATTERNS: RegExp[] = [
  /process\s*\??\.\s*env\s*\??\.\s*NODE_ENV\b/,
  /process\s*\??\.\s*env\s*(?:\?\.)?\s*\[\s*['"`]NODE_ENV['"`]\s*\]/,
  /\{[^}]*\bNODE_ENV\b[^}]*\}\s*=\s*process\s*\??\.\s*env\b/,
];

export interface Hit {
  line: number;
  text: string;
}

export function findNodeEnv(src: string): Hit[] {
  const out: Hit[] = [];
  const lines = src.split('\n');
  // Whole-source match first so a destructuring wrapped over lines is seen; report its first line.
  for (const re of PATTERNS) {
    const g = new RegExp(re.source, 'g');
    for (let m = g.exec(src); m; m = g.exec(src)) {
      const line = src.slice(0, m.index).split('\n').length;
      out.push({ line, text: (lines[line - 1] ?? '').trim().slice(0, 100) });
    }
  }
  return out.sort((a, b) => a.line - b.line);
}

function tsFiles(dir: string): string[] {
  const out: string[] = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...tsFiles(p));
    else if (e.name.endsWith('.ts')) out.push(p);
  }
  // Code-unit order, never localeCompare: the scan order (and any printed finding order) must not depend on the host locale or ICU.
  return out.sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
}

function selftest(): void {
  const fail = (m: string): never => {
    console.error(`  FAIL  ${m}`);
    process.exit(1);
  };
  if (
    findNodeEnv('const a = process.env.JWT_SECRET;\nconst b = c.env.NODE_ENVIRONMENT_X;').length !==
    0
  )
    fail('CONTROL: a clean route was reported');
  console.log('  PASS  CONTROL: a clean route is accepted');
  if (findNodeEnv("if (process.env.NODE_ENV === 'production') {}").length !== 1)
    fail('dotted plant not caught');
  console.log('  PASS  dotted plant is caught');
  if (findNodeEnv("const x = process.env['NODE_ENV'];").length !== 1)
    fail('bracket plant not caught');
  console.log('  PASS  bracket plant is caught');
  const wrapped = 'const {\n  PORT,\n  NODE_ENV,\n} = process.env;';
  if (findNodeEnv(wrapped).length !== 1) fail('wrapped destructuring plant not caught');
  console.log('  PASS  wrapped destructuring plant is caught');
  for (const plant of [
    "if (process.env?.NODE_ENV === 'test') {}",
    "if (process?.env?.NODE_ENV === 'test') {}",
    "const y = process?.env?.['NODE_ENV'];",
  ]) {
    if (findNodeEnv(plant).length !== 1) fail(`optional-chaining plant not caught: ${plant}`);
  }
  console.log('  PASS  optional-chaining plants are caught');
}

function main(): void {
  if (process.argv.includes('--selftest')) {
    selftest();
    console.log('check-account-no-node-env-routes: selftest ok (5 controls)');
    return;
  }
  const dir = path.join(ROOT, ROUTES);
  if (!fs.existsSync(dir)) {
    console.error(
      `✗ ${ROUTES} does not exist, so this gate checked NOTHING. Update ROUTES if it moved.`
    );
    process.exit(1);
  }
  const files = tsFiles(dir);
  if (files.length < MIN_FILES) {
    console.error(
      `✗ VACUOUS: only ${files.length} .ts file(s) under ${ROUTES}, below the floor of ${MIN_FILES}.`
    );
    process.exit(1);
  }
  let bad = 0;
  for (const f of files) {
    for (const h of findNodeEnv(fs.readFileSync(f, 'utf-8'))) {
      bad++;
      console.error(`✗ ${path.relative(ROOT, f)}:${h.line}  ${h.text}`);
    }
  }
  if (bad > 0) {
    console.error(
      `\n  ${bad} NODE_ENV reference(s) in account routes. Routes behave the same in every environment; move the switch into configuration injected at startup.`
    );
    process.exit(1);
  }
  console.log(`✓ no NODE_ENV branching in account routes: ${files.length} route file(s) scanned`);
}

if (isEntryPoint(import.meta.filename)) main();
