/**
 * The seed of one lease tree (agent/plans/PLAN-worktree-lease.md Design 2 step 5), called by `.ci/rediacc_ci/dev/worktree_lease.py`:
 *
 *   tsx scripts/ci-runner/lease-seed.ts <lease> <live> <commit>
 *
 * Dependencies and builds go through quick-clone's own `syncDependencies` and `syncBuilds`, so a lease and the kept clone judge a live install by one rule. Their state files sit beside the tree, and a lease is seeded once, so they go when the seed ends. Exit 1 names the reason; the caller removes the tree.
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { isEntryPoint } from '../lib/entry-point.js';
import { assertNoSelfLoop, syncBuilds, syncDependencies } from './quick-clone.js';

/** Far too big to copy and addressed by version, as in quick-clone. Spelled `ln -sfn`: a plain `ln -s` onto an existing link plants a self-loop. */
const LINKED_CACHES = ['.ci/cache/toolchain', '.ci/cache/bin', '.venv'];
/** The workspace packages other packages import from `dist`: without it their tests cannot load in a lease (measured 2026-11-04: 19 CLI test files, on `@rediacc/provisioning`). */
const BUILT_PACKAGES = ['packages/shared', 'packages/provisioning', 'packages/json'];
const E2E = 'packages/e2e-tests';
const RECEIPT = '.ci/cache/prepush-receipt.json';

function run(cmd: string, args: readonly string[], cwd: string): string {
  const env = { ...process.env };
  for (const key of ['GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_PREFIX', 'GIT_COMMON_DIR'])
    delete env[key];
  const done = spawnSync(cmd, [...args], {
    cwd,
    env,
    encoding: 'utf8',
    maxBuffer: 1 << 28,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  if (done.error !== undefined) throw new Error(`${cmd}: ${done.error.message}`);
  if (done.status !== 0) {
    const tail = (done.stderr || done.stdout).trim().split('\n').slice(-3).join(' | ');
    throw new Error(`${cmd} ${args.join(' ')} exited ${done.status}: ${tail}`);
  }
  return done.stdout.trim();
}

function linkCaches(lease: string, live: string): void {
  for (const rel of LINKED_CACHES) {
    const source = path.join(live, rel);
    if (!fs.existsSync(source)) continue;
    const dest = path.join(lease, rel);
    // tree-write: safe a directory inside the lease tree, which is ignored and never the live tree
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    run('ln', ['-sfn', source, dest], lease);
  }
}

/** A live `dist` built from dirty source would judge the wrong code, so it is copied only from a clean package. A copy, not a hard link, because a build in the lease writes in place. */
function seedDist(lease: string, live: string, pkg: string): string {
  const manifest = path.join(lease, pkg, 'package.json');
  if (!fs.existsSync(manifest)) return `${pkg}: not in this commit`;
  const source = path.join(live, pkg, 'dist');
  // The dependants of `packages/shared` were built against it, so its dirt taints their dist too.
  const dirty = run('git', ['status', '--porcelain', '--', pkg, 'packages/shared'], live);
  if (dirty === '' && fs.existsSync(source)) {
    run('cp', ['-a', source, path.join(lease, pkg, 'dist')], lease);
    return `${pkg}/dist: copied from a clean live package`;
  }
  const scripts = (
    JSON.parse(fs.readFileSync(manifest, 'utf8')) as { scripts?: Record<string, string> }
  ).scripts;
  if (scripts?.build === undefined) return `${pkg}: no build script`;
  run('npm', ['run', 'build'], path.join(lease, pkg));
  return `${pkg}/dist: built in the lease`;
}

/** The ignored credentials an e2e run reads. A tracked name is already in the tree and stays as committed. */
function copyEnvFiles(lease: string, live: string): void {
  const source = path.join(live, E2E);
  if (!fs.existsSync(source)) return;
  const entries = fs.readdirSync(source);
  // Few `.env*` files is normal; an empty package directory means the path is wrong, so the copy would pass with nothing read.
  if (entries.length === 0) throw new Error(`VACUOUS: ${source} lists no entry at all`);
  for (const name of entries) {
    if (!name.startsWith('.env')) continue;
    const from = path.join(source, name);
    const to = path.join(lease, E2E, name);
    const stat = fs.lstatSync(from);
    if (!stat.isFile() || fs.existsSync(to)) continue;
    // tree-write: safe a path inside the lease tree, which is ignored and never the live tree
    fs.mkdirSync(path.dirname(to), { recursive: true });
    // tree-write: safe a path inside the lease tree, which is ignored and never the live tree
    fs.copyFileSync(from, to);
    // tree-write: safe a path inside the lease tree, which is ignored and never the live tree
    fs.chmodSync(to, stat.mode & 0o7777);
  }
}

/** `npm run ci -- --narrow` reads the last receipt and writes none, and a lease cannot make one because `ci:quick` is refused there. The copy serves that read only: the push guards are refused from a lease, so it authorises nothing. */
export function seedReceipt(lease: string, live: string): string {
  const source = path.join(live, RECEIPT);
  if (!fs.existsSync(source)) return `${RECEIPT}: none in the main checkout, --narrow will say so`;
  const dest = path.join(lease, RECEIPT);
  // tree-write: safe a directory inside the lease tree, which is ignored and never the live tree
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  // tree-write: safe a path inside the lease tree, which is ignored and never the live tree
  fs.copyFileSync(source, dest);
  return `${RECEIPT}: copied from the main checkout for --narrow`;
}

export function seedLease(lease: string, live: string, commit: string): string[] {
  try {
    const notes = syncDependencies(lease, live, commit);
    syncBuilds(lease, live);
    linkCaches(lease, live);
    for (const pkg of BUILT_PACKAGES) notes.push(seedDist(lease, live, pkg));
    copyEnvFiles(lease, live);
    notes.push(seedReceipt(lease, live));
    assertNoSelfLoop(live);
    assertNoSelfLoop(lease);
    return notes;
  } finally {
    for (const suffix of ['.deps.json', '.builds.json']) {
      // tree-write: safe quick-clone's state file beside the lease tree, under the ignored holder
      fs.rmSync(`${lease}${suffix}`, { force: true });
    }
  }
}

if (isEntryPoint(import.meta.filename)) {
  const [lease, live, commit, ...rest] = process.argv.slice(2);
  if (lease === undefined || live === undefined || commit === undefined || rest.length > 0) {
    process.stderr.write('Usage: lease-seed.ts <lease> <live> <commit>\n');
    process.exit(2);
  }
  try {
    for (const note of seedLease(lease, live, commit))
      process.stderr.write(`lease-seed: ${note}\n`);
  } catch (err) {
    process.stderr.write(`lease-seed: ${(err as Error).message}\n`);
    process.exit(1);
  }
}
