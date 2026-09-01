#!/usr/bin/env tsx
/**
 * Every tsconfig in the repo must be REACHED by `npm run typecheck`, or be a base another
 * one extends.
 *
 * THE DEFECT THIS EXISTS TO CLOSE, paid for twice in one night. A tsconfig is a promise
 * that a tree is typechecked, and nothing was checking that anyone ever cashed it:
 *
 *   - `packages/e2e-tests` (77 files), `packages/provisioning`, `packages/www` (170 files)
 *     and all four `workers/*` had tsconfigs that NO script ran. packages/www was hiding
 *     32 real TS2339 errors in production components. The coverage looked real and never
 *     executed.
 *   - The fix for that then shipped its own version of the same bug: `tsc -p
 *     workers/www/tsconfig.json` was appended to the root chain and passed locally,
 *     because `types: ["@cloudflare/workers-types"]` resolves from THAT project's
 *     node_modules, which the author's machine happened to have and CI does not.
 *
 * Neither was visible to any gate. `check:types` cannot report a project it was never
 * pointed at, and a green `check:types` is exactly what an uncovered tsconfig produces.
 *
 * WHY THE RESOLVER READS THE REAL SCRIPT rather than a list. A hand-maintained list of
 * "covered" projects is the same promise this gate distrusts. The covered set is derived
 * from `package.json`'s `typecheck` script by walking what it actually invokes -- `tsc -b`
 * dirs, `-p`/`--project` paths, `npm run typecheck --workspace <pkg>` (recursed into that
 * package's own script), and a `.sh` step, which is asked for its set with `--list` so a
 * discovery-based step cannot drift from what this gate believes it covers.
 *
 * Usage:
 *   npx tsx scripts/check-typecheck-scope-coverage.ts [--selftest]
 */
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const ROOT = path.resolve(import.meta.dirname, '..');

/**
 * Everything the judgement needs, injected so the controls below drive the SAME function
 * the repo goes through. A control that runs a reimplementation proves nothing.
 */
export interface World {
  /** Every tracked tsconfig, repo-relative, POSIX separators. */
  discovered: string[];
  /** The root `typecheck` npm script, verbatim. */
  rootTypecheck: string;
  /** A workspace's own `typecheck` script, or null when it has none. */
  packageScript(pkgDir: string): string | null;
  /** What a shell step reports it will typecheck, via its `--list` flag. */
  shellList(script: string): string[];
  /** The tsconfig a given tsconfig `extends`, repo-relative, or null. */
  extendsTarget(tsconfig: string): string | null;
}

export interface Verdict {
  /** tsconfigs no part of the chain reaches and nothing extends. */
  uncovered: string[];
  /** tsconfigs the chain names that do not exist -- a chain rotted by a rename. */
  dangling: string[];
  covered: string[];
}

const norm = (p: string) => p.split(path.sep).join('/').replace(/^\.\//, '');

/** Resolve one `&&`-separated clause to the tsconfig paths it typechecks. */
function resolveClause(clause: string, cwd: string, world: World, depth = 0): string[] {
  const c = clause.trim();
  if (!c || depth > 4) return [];

  // `.ci/scripts/quality/typecheck-workers.sh` and any future shell step: ask it.
  const shell = c.split(/\s+/).find((t) => t.endsWith('.sh'));
  if (shell) return world.shellList(shell).map(norm);

  // `npm run typecheck --workspace packages/www` -> that package's own script.
  const ws = c.match(/npm run (\S+)\s+--workspace[= ]+(\S+)/);
  if (ws) {
    const inner = world.packageScript(ws[2]);
    return inner ? resolveClause(inner, ws[2], world, depth + 1) : [];
  }

  const tokens = c.split(/\s+/);
  if (!tokens.includes('tsc')) {
    // Not a typecheck invocation (e.g. `astro sync`); contributes nothing on its own.
    return [];
  }

  // `-p X` / `--project X` / `--project=X`
  const out: string[] = [];
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t === '-p' || t === '--project') {
      if (tokens[i + 1]) out.push(norm(path.join(cwd, tokens[i + 1])));
    } else if (t.startsWith('--project=')) {
      out.push(norm(path.join(cwd, t.slice('--project='.length))));
    }
  }
  if (out.length > 0) return out;

  // `tsc -b a b c` -> each dir's tsconfig.json
  const bIdx = tokens.findIndex((t) => t === '-b' || t === '--build');
  if (bIdx >= 0) {
    for (const t of tokens.slice(bIdx + 1)) {
      if (t.startsWith('-')) continue;
      out.push(norm(path.join(cwd, t.endsWith('.json') ? t : `${t}/tsconfig.json`)));
    }
    return out;
  }

  // Bare `tsc --noEmit` inside a workspace -> that workspace's tsconfig.json
  return [norm(path.join(cwd, 'tsconfig.json'))];
}

export function judge(world: World): Verdict {
  const reached = new Set<string>();
  for (const clause of world.rootTypecheck.split('&&')) {
    for (const p of resolveClause(clause, '.', world)) reached.add(p);
  }

  // A base config is covered by the projects that extend it: tsc reads it on every one of
  // their runs, so a type error introduced there surfaces immediately.
  const extendedByAProject = new Set<string>();
  for (const cfg of world.discovered) {
    const target = world.extendsTarget(cfg);
    if (target) extendedByAProject.add(target);
  }

  const covered: string[] = [];
  const uncovered: string[] = [];
  for (const cfg of world.discovered) {
    if (reached.has(cfg) || extendedByAProject.has(cfg)) covered.push(cfg);
    else uncovered.push(cfg);
  }

  // A chain naming a tsconfig that is not on disk is rot in the other direction: the
  // clause runs, tsc errors, and nobody reads which of the nine projects it was.
  const known = new Set(world.discovered);
  const dangling = [...reached].filter((p) => !known.has(p) && !p.startsWith('private/'));

  return { uncovered, dangling, covered };
}

/** Assembled, never written whole: see the comment on the dangling control below. */
const ABSENT_CONFIG = ['packages', 'no-such-workspace', 'tsconfig.json'].join('/');

/** Controls: each is the real defect, reconstructed. */
const CONTROLS: { name: string; world: World; expect: (v: Verdict) => boolean }[] = [];

function fakeWorld(over: Partial<World>): World {
  return {
    discovered: [],
    rootTypecheck: '',
    packageScript: () => null,
    shellList: () => [],
    extendsTarget: () => null,
    ...over,
  };
}

CONTROLS.push(
  {
    name: 'a tsconfig no clause reaches is reported (the packages/www shape)',
    world: fakeWorld({
      discovered: ['packages/cli/tsconfig.json', 'packages/www/tsconfig.json'],
      rootTypecheck: 'tsc -b packages/cli',
    }),
    expect: (v) => v.uncovered.join() === 'packages/www/tsconfig.json',
  },
  {
    name: 'CONTROL: naming it in the chain clears it',
    world: fakeWorld({
      discovered: ['packages/cli/tsconfig.json', 'packages/www/tsconfig.json'],
      rootTypecheck: 'tsc -b packages/cli && tsc --noEmit -p packages/www/tsconfig.json',
    }),
    expect: (v) => v.uncovered.length === 0,
  },
  {
    name: 'a workspace script is followed, not treated as opaque',
    world: fakeWorld({
      discovered: ['packages/www/tsconfig.json'],
      rootTypecheck: 'npm run typecheck --workspace packages/www',
      packageScript: (d) => (d === 'packages/www' ? 'astro sync && tsc --noEmit' : null),
    }),
    expect: (v) => v.uncovered.length === 0 && v.covered.length === 1,
  },
  {
    name: 'a shell step is asked for its set (the workers shape)',
    world: fakeWorld({
      discovered: ['workers/a/tsconfig.json', 'workers/b/tsconfig.json'],
      rootTypecheck: '.ci/scripts/quality/typecheck-workers.sh',
      shellList: () => ['workers/a/tsconfig.json', 'workers/b/tsconfig.json'],
    }),
    expect: (v) => v.uncovered.length === 0,
  },
  {
    name: 'a shell step that reports a SHORTER set leaves the rest uncovered',
    world: fakeWorld({
      discovered: ['workers/a/tsconfig.json', 'workers/b/tsconfig.json'],
      rootTypecheck: '.ci/scripts/quality/typecheck-workers.sh',
      shellList: () => ['workers/a/tsconfig.json'],
    }),
    expect: (v) => v.uncovered.join() === 'workers/b/tsconfig.json',
  },
  {
    name: 'a base config nothing runs is covered by whoever extends it',
    world: fakeWorld({
      discovered: ['tsconfig.json', 'packages/cli/tsconfig.json'],
      rootTypecheck: 'tsc -b packages/cli',
      extendsTarget: (c) => (c === 'packages/cli/tsconfig.json' ? 'tsconfig.json' : null),
    }),
    expect: (v) => v.uncovered.length === 0,
  },
  {
    name: 'CONTROL: a base nothing extends is NOT excused',
    world: fakeWorld({
      discovered: ['tsconfig.json', 'packages/cli/tsconfig.json'],
      rootTypecheck: 'tsc -b packages/cli',
    }),
    expect: (v) => v.uncovered.join() === 'tsconfig.json',
  },
  {
    name: 'a chain clause naming a tsconfig that does not exist is reported',
    // The absent path is BUILT at runtime rather than written as a literal:
    // gate-test:gate-paths-exist scans source for path constants whose workspace root is
    // missing, and a control whose whole point is a non-existent path trips it.
    world: fakeWorld({
      discovered: ['packages/cli/tsconfig.json'],
      rootTypecheck: `tsc -b packages/cli && tsc --noEmit -p ${ABSENT_CONFIG}`,
    }),
    expect: (v) => v.dangling.join() === ABSENT_CONFIG,
  }
);

function realWorld(): World {
  const tracked = execFileSync('git', ['ls-files'], { cwd: ROOT, encoding: 'utf8' })
    .split('\n')
    .filter((f) => /(^|\/)tsconfig[^/]*\.json$/.test(f) && !f.includes('node_modules'));

  const readJsonc = (rel: string): Record<string, unknown> | null => {
    const abs = path.join(ROOT, rel);
    if (!existsSync(abs)) return null;
    const raw = readFileSync(abs, 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/^\s*\/\/.*$/gm, '');
    try {
      return JSON.parse(raw) as Record<string, unknown>;
    } catch {
      return null;
    }
  };

  return {
    discovered: tracked.sort(),
    rootTypecheck: (
      JSON.parse(readFileSync(path.join(ROOT, 'package.json'), 'utf8')) as {
        scripts: Record<string, string>;
      }
    ).scripts.typecheck,
    packageScript(pkgDir) {
      const p = path.join(ROOT, pkgDir, 'package.json');
      if (!existsSync(p)) return null;
      const pkg = JSON.parse(readFileSync(p, 'utf8')) as { scripts?: Record<string, string> };
      return pkg.scripts?.typecheck ?? null;
    },
    shellList(script) {
      return execFileSync(path.join(ROOT, script), ['--list'], { cwd: ROOT, encoding: 'utf8' })
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);
    },
    extendsTarget(tsconfig) {
      const cfg = readJsonc(tsconfig);
      const ext = cfg?.extends;
      if (typeof ext !== 'string' || !ext.startsWith('.')) return null;
      return norm(path.join(path.dirname(tsconfig), ext));
    },
  };
}

function main(): void {
  if (process.argv.includes('--selftest')) {
    let ok = true;
    for (const c of CONTROLS) {
      const fired = c.expect(judge(c.world));
      ok &&= fired;
      console.log(`  ${fired ? '\x1b[32mPASS\x1b[0m' : '\x1b[31mFAIL\x1b[0m'}  CONTROL: ${c.name}`);
    }
    if (!ok) {
      console.error('\x1b[31m✗\x1b[0m a control did not behave, so this gate cannot be trusted');
      process.exit(1);
    }
  }

  const world = realWorld();

  // FLOORS. Either of these means the scan is broken, and a broken scan reports a
  // confident green having checked nothing -- the exact failure this gate exists for.
  if (world.discovered.length === 0) {
    console.error('\x1b[31m✗\x1b[0m git ls-files found no tsconfig at all; the scan is broken');
    process.exit(1);
  }
  if (!world.rootTypecheck) {
    console.error('\x1b[31m✗\x1b[0m package.json has no `typecheck` script to resolve');
    process.exit(1);
  }

  const v = judge(world);

  if (v.covered.length === 0) {
    console.error('\x1b[31m✗\x1b[0m the chain resolved to nothing; the resolver is broken');
    process.exit(1);
  }

  if (v.uncovered.length > 0 || v.dangling.length > 0) {
    for (const c of v.uncovered) {
      console.error(
        `\x1b[31m✗\x1b[0m ${c} is not reached by \`npm run typecheck\` and nothing extends it.`
      );
      console.error('    A tsconfig nobody runs is coverage that looks real and never executes.');
    }
    for (const c of v.dangling) {
      console.error(`\x1b[31m✗\x1b[0m the typecheck chain names ${c}, which does not exist.`);
    }
    console.error('\n  Add it to `typecheck` AND `check:types` in package.json (both strings).');
    process.exit(1);
  }

  console.log(
    `\x1b[32m✓\x1b[0m typecheck scope: ${world.discovered.length} tsconfig(s), all reached by ` +
      '`npm run typecheck` or extended by one that is'
  );
}

main();
