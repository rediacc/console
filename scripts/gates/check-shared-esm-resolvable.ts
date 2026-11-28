/**
 * check:ci-shared-esm-resolvable — the built @rediacc/shared must be loadable
 * as the ESM package it declares itself to be.
 *
 * The class this catches, paid for in full on 2026-08-14: packages/shared
 * declares `"type": "module"` with `main: ./dist/index.js`, but its build is
 * plain `tsc`, which emits relative specifiers verbatim. dist carried 120
 * extensionless specifiers, so `node --input-type=module` importing ANY
 * re-exported symbol died ERR_MODULE_NOT_FOUND at dist/config/defaults. All
 * seven consumers bundle (esbuild, vitest, wrangler, astro), and a bundler
 * resolves extensionless happily, so the package was broken exactly as it
 * advertised itself and nothing ever noticed.
 *
 * Why this gate IMPORTS rather than SCANS: a scanner for extensionless
 * specifiers is a proxy for the real question, and a novel failure mode walks
 * straight past a proxy. The JSON import attributes are the proof — missing
 * `with { type: 'json' }` breaks a raw Node import just as fatally and has
 * nothing to do with extensions. The only honest check is to load the artifact
 * the way Node would.
 *
 * Run: npx tsx scripts/gates/check-shared-esm-resolvable.ts
 *
 * Control-first, in BOTH directions (see house pattern in
 * scripts/gates/check-shared-constant-duplication.ts). The bad arms catch a detector
 * that has gone blind; the good arm catches one that has collapsed into
 * reporting everything, which would make a green run on the real package
 * indistinguishable from a broken instrument.
 *
 * ---- gate ----
 * step: Shared ESM resolvable
 * needs: node
 * lane: quality-packages
 * ---- end gate ----
 */

import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { globSync } from 'glob';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..', '..');
const DIST = join(ROOT, 'packages/shared/dist');
const PKG_JSON = join(ROOT, 'packages/shared/package.json');

/** Floors. A build that collapses to a handful of modules is not a pass. */
const MIN_MODULES = 100;
const MIN_CONCRETE_EXPORT_TARGETS = 20;

interface Failure {
  module: string;
  code: string;
  url?: string;
  message: string;
}

interface ImportResult {
  attempted: number;
  failures: Failure[];
}

const SENTINEL = '__ESM_RESOLVABLE_DONE__';

/**
 * Built modules that load only where `cloudflare:workers` resolves: on Workers (wrangler supplies the built-in) or on Node after
 * `installCloudflareWorkersShim()` from dist/mcp-host/node-workers-shim.js. Each is still IMPORTED, in a second child with that
 * shim installed, so a missing extension or import attribute behind it stays red. A module that needs the scheme and is not
 * named here is red, and a named one that loads without the shim is a dead entry and red too. Printed on a green run, with each reason's `BLOCKER: ` prefix stripped.
 */
const WORKERS_RUNTIME: Record<string, string> = {
  'mcp-host/handler.js':
    'BLOCKER: imports oauth/index.js, so it carries the same `cloudflare:workers` edge (PLAN RW-OP1 moved the handler into @rediacc/shared; the Node host installs the shim before importing it).',
  'mcp-host/oauth/index.js':
    'BLOCKER: imports @cloudflare/workers-oauth-provider, whose published dist imports `WorkerEntrypoint` from `cloudflare:workers`; Node loads it only behind installCloudflareWorkersShim().',
};
const SHIM_MODULE = 'mcp-host/node-workers-shim.js';

/** A raw-Node failure that is exactly the `cloudflare:` scheme refusal, and nothing else. */
function isWorkersSchemeRefusal(f: Pick<Failure, 'code' | 'message'>): boolean {
  return f.code === 'ERR_UNSUPPORTED_ESM_URL_SCHEME' && f.message.includes("'cloudflare:'");
}

/**
 * Import every module in a child process.
 *
 * The child is NOT stylistic. In-process, one dist module calling
 * process.exit(0) at import time would end the gate with a success code and no
 * output, which reads exactly like a pass. So the parent demands BOTH the
 * completion sentinel AND attempted === expected: a child that exits 0 without
 * finishing is a failure, not a success.
 */
function importAll(dir: string, modules: string[], shimUrl?: string): ImportResult {
  const prelude = shimUrl
    ? `const shim = await import(${JSON.stringify(shimUrl)}); shim.installCloudflareWorkersShim();`
    : '';
  const script = `
    ${prelude}
    const failures = [];
    let attempted = 0;
    for (const m of ${JSON.stringify(modules)}) {
      attempted++;
      try {
        await import(m);
      } catch (err) {
        failures.push({
          module: m,
          code: err?.code ?? 'UNKNOWN',
          url: err?.url,
          message: String(err?.message ?? err).split('\\n')[0],
        });
      }
    }
    console.log('${SENTINEL}' + JSON.stringify({ attempted, failures }));
  `;
  let stdout: string;
  try {
    stdout = execFileSync(process.execPath, ['--input-type=module', '-e', script], {
      cwd: dir,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
      maxBuffer: 32 * 1024 * 1024,
    });
  } catch (err) {
    const e = err as { stdout?: string; stderr?: string };
    stdout = e.stdout ?? '';
    if (!stdout.includes(SENTINEL)) {
      return {
        attempted: -1,
        failures: [
          {
            module: '(child process)',
            code: 'CHILD_DIED',
            message: (e.stderr ?? 'child exited without the completion sentinel')
              .trim()
              .split('\n')[0],
          },
        ],
      };
    }
  }
  const at = stdout.indexOf(SENTINEL);
  if (at === -1)
    return {
      attempted: -1,
      failures: [
        {
          module: '(child process)',
          code: 'NO_SENTINEL',
          message: 'child produced no completion sentinel',
        },
      ],
    };
  return JSON.parse(stdout.slice(at + SENTINEL.length)) as ImportResult;
}

// ── Phase 0: control, three arms ───────────────────────────────────────────
function runControls(): string | null {
  const tmp = mkdtempSync(join(tmpdir(), 'esm-resolvable-control-'));
  try {
    const arm = (name: string, files: Record<string, string>) => {
      const dir = join(tmp, name);
      mkdirSync(dir, { recursive: true });
      writeFileSync(join(dir, 'package.json'), JSON.stringify({ type: 'module' }));
      for (const [f, body] of Object.entries(files)) writeFileSync(join(dir, f), body);
      return importAll(dir, [pathToFileURL(join(dir, 'index.js')).href]);
    };

    const badExt = arm('bad-extension', {
      'index.js': "export * from './leaf';\n",
      'leaf.js': 'export const leaf = 1;\n',
    });
    if (!badExt.failures.some((f) => f.code === 'ERR_MODULE_NOT_FOUND')) {
      return 'the bad-extension arm did not report ERR_MODULE_NOT_FOUND: the detector is blind to the exact defect it exists for.';
    }

    const badJson = arm('bad-json', {
      'index.js': "import d from './d.json';\nexport default d;\n",
      'd.json': '{"a":1}',
    });
    if (badJson.failures.length === 0) {
      return 'the bad-json arm imported cleanly: a missing import attribute breaks a raw Node import just as fatally as a missing extension, and this detector cannot see it.';
    }

    const good = arm('good', {
      'index.js':
        "export * from './leaf.js';\nimport d from './d.json' with { type: 'json' };\nexport default d;\n",
      'leaf.js': 'export const leaf = 1;\n',
      'd.json': '{"a":1}',
    });
    if (good.failures.length !== 0) {
      return `the good arm FAILED (${good.failures[0]?.code}): the detector reports everything, so a green run on the real package would prove nothing.`;
    }

    const shimSource = [
      "import { registerHooks } from 'node:module';",
      "const url = 'data:text/javascript,' + encodeURIComponent('export class WorkerEntrypoint {}');",
      'export function installCloudflareWorkersShim() {',
      "  registerHooks({ resolve: (s, c, next) => (s === 'cloudflare:workers' ? { url, format: 'module', shortCircuit: true } : next(s, c)) });",
      '}',
    ].join('\n');
    const workersFiles = {
      'index.js':
        "import { WorkerEntrypoint } from 'cloudflare:workers';\nexport const ok = typeof WorkerEntrypoint;\n",
      'shim.js': shimSource,
    };
    const workersRaw = arm('workers-raw', workersFiles);
    if (!(workersRaw.failures.length === 1 && isWorkersSchemeRefusal(workersRaw.failures[0]))) {
      return `the workers arm did not fail raw with the cloudflare: scheme refusal (${workersRaw.failures[0]?.code ?? 'it loaded'}): the WORKERS_RUNTIME split cannot tell a Workers-only module from a clean one.`;
    }
    const workersDir = join(tmp, 'workers-raw');
    const workersShimmed = importAll(
      workersDir,
      [pathToFileURL(join(workersDir, 'index.js')).href],
      pathToFileURL(join(workersDir, 'shim.js')).href
    );
    if (workersShimmed.failures.length !== 0 || workersShimmed.attempted !== 1) {
      return `the workers arm FAILED behind the shim (${workersShimmed.failures[0]?.code}): the shimmed import cannot prove a WORKERS_RUNTIME module loads.`;
    }
    return null;
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
}

const controlProblem = runControls();
if (controlProblem) {
  console.error(`✗ instrument control did not fire: ${controlProblem}`);
  process.exit(1);
}

// ── Phase 1: zero-scan guard ───────────────────────────────────────────────
if (!existsSync(DIST)) {
  console.error(
    `✗ ${DIST} does not exist. Run \`npm run build:packages\` first.\n` +
      '  A missing build is an UNRUN check, never a pass.'
  );
  process.exit(1);
}

const modules = globSync('**/*.js', { cwd: DIST, absolute: true }).sort(
  (a, b) => Number(a > b) - Number(a < b)
);
if (modules.length < MIN_MODULES) {
  console.error(
    `✗ only ${modules.length} modules under dist (floor ${MIN_MODULES}).\n` +
      '  A build that collapsed to a handful of files would otherwise import\n' +
      '  cleanly and read as a pass.'
  );
  process.exit(1);
}

const pkg = JSON.parse(readFileSync(PKG_JSON, 'utf8')) as {
  exports?: Record<string, { default?: string; types?: string }>;
};
const concreteTargets = Object.values(pkg.exports ?? {})
  .map((e) => e?.default)
  .filter((t): t is string => typeof t === 'string' && !t.includes('*'));
if (concreteTargets.length < MIN_CONCRETE_EXPORT_TARGETS) {
  console.error(
    `✗ only ${concreteTargets.length} concrete export targets in package.json ` +
      `(floor ${MIN_CONCRETE_EXPORT_TARGETS}).\n` +
      '  An exports map that stopped resolving would make this check vacuous.'
  );
  process.exit(1);
}

const missingTargets = concreteTargets.filter((t) => !existsSync(join(ROOT, 'packages/shared', t)));
if (missingTargets.length > 0) {
  console.error(
    `✗ package.json exports point at files the build does not emit (${missingTargets.length}):\n` +
      missingTargets.map((t) => `    ${t}`).join('\n') +
      '\n\n  A consumer importing that subpath gets ERR_MODULE_NOT_FOUND.'
  );
  process.exit(1);
}

// ── Phase 2: import the artifact the way Node would ────────────────────────
const urls = modules.map((m) => pathToFileURL(m).href);
const result = importAll(ROOT, urls);

if (result.attempted !== urls.length) {
  console.error(
    `✗ the import child did not finish: attempted ${result.attempted} of ${urls.length}.\n` +
      (result.failures[0] ? `  ${result.failures[0].code}: ${result.failures[0].message}\n` : '') +
      '  A child that exits without the completion sentinel is a FAILURE. In-process\n' +
      '  this would have looked like a clean pass.'
  );
  process.exit(1);
}

const rel = (url: string) => url.replace(`${pathToFileURL(DIST).href}/`, '');
const needsShim = result.failures.filter(
  (f) => isWorkersSchemeRefusal(f) && rel(f.module) in WORKERS_RUNTIME
);
const otherFailures = result.failures.filter((f) => !needsShim.includes(f));
const deadEntries = Object.keys(WORKERS_RUNTIME).filter(
  (m) => !needsShim.some((f) => rel(f.module) === m)
);
if (deadEntries.length > 0) {
  console.error(
    `✗ WORKERS_RUNTIME names ${deadEntries.length} module(s) that did not fail raw on the cloudflare: scheme:\n` +
      deadEntries.map((m) => `    dist/${m}`).join('\n') +
      '\n\n  Either the build no longer emits it or it now loads on plain Node. Remove the entry from\n' +
      '  scripts/gates/check-shared-esm-resolvable.ts: an entry that excuses nothing is how an allowlist becomes a way to pass.'
  );
  process.exit(1);
}
const shimmed = importAll(
  ROOT,
  needsShim.map((f) => f.module),
  pathToFileURL(join(DIST, SHIM_MODULE)).href
);
if (shimmed.attempted !== needsShim.length || shimmed.failures.length > 0) {
  otherFailures.push(
    ...(shimmed.failures.length > 0
      ? shimmed.failures
      : [
          {
            module: '(shimmed child)',
            code: 'CHILD_DIED',
            message: `attempted ${shimmed.attempted} of ${needsShim.length}`,
          },
        ])
  );
}
result.failures = otherFailures;

if (result.failures.length > 0) {
  const rows = result.failures.map(
    (f) =>
      `    ${f.module.replace(pathToFileURL(DIST).href, 'dist')}\n` +
      `      ${f.code}${f.url ? ` -> ${f.url.replace(pathToFileURL(DIST).href, 'dist')}` : ''}\n` +
      `      ${f.message}`
  );
  console.error(
    `✗ ${result.failures.length} of ${result.attempted} built modules cannot be imported by Node:\n` +
      `${rows.join('\n')}\n\n` +
      '  packages/shared declares "type": "module", so this is the package failing\n' +
      '  exactly as it advertises itself. Every consumer bundles today, which is why\n' +
      '  nothing else catches it. The err.url above names the unresolvable specifier.\n' +
      '  Usual cause: a relative import without its .js extension, or a .json import\n' +
      "  without `with { type: 'json' }`. A Workers-only module (the cloudflare: scheme) belongs in\n" +
      '  WORKERS_RUNTIME with a BLOCKER reason, where it is still imported behind the Node shim.'
  );
  process.exit(1);
}

const shimRows = Object.keys(WORKERS_RUNTIME).map(
  (m) => `    dist/${m} -- ${WORKERS_RUNTIME[m].replace(/^BLOCKER: /, '')}`
);
const summary = `${result.attempted} built modules imported by Node, ${concreteTargets.length} concrete export targets present; 5-arm control fired`;
console.log(
  `✓ shared is importable as declared (${summary})\n` +
    `  ${needsShim.length} Workers-only module(s) imported behind ${SHIM_MODULE}:\n${shimRows.join('\n')}`
);
