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

/** Far too big to copy: pinned tool installs addressed by version, as in quick-clone, plus `.ci/cache/registry`, the one entry that is NOT addressed by version (Docker Hub tag listings whose answers change upstream), linked so every tree reads the single listing the freshness gate refreshes and re-reads on a mismatch. Spelled `ln -sfn`: a plain `ln -s` onto an existing link plants a self-loop. */
const LINKED_CACHES = ['.ci/cache/toolchain', '.ci/cache/bin', '.ci/cache/registry', '.venv'];
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

/** A live `dist` built from dirty source would judge the wrong code, so it is copied only when both the package and `packages/shared`, which its dist was built against, are clean. A copy, not a hard link, because a build in the lease writes in place. */
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
  // Few `.env*` files is normal, and a directory with only other files passes. A directory that lists nothing at all means the path is wrong, so the copy would pass with nothing read.
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

/** Public keys only (the account Ed25519 and X25519 public halves: the cache's version header comment and `ACCOUNT_*_PUBLIC_KEY=` lines are kept, any other line, a comment included, is dropped, so the copy holds nothing secret whatever the source file grows), the offline answer `resolve_renet_account_key` reads before Bitwarden. Without it a renet build in a seeded tree depends on a Bitwarden read, which a drill leg's environment cannot always make (2026-11-21: backup drill leg f in the landing tree, "renet needs ACCOUNT_ED25519_PUBLIC_KEY ... not in the public-key cache, and not readable from Bitwarden"). */
const PUBLIC_KEYS = 'private/account/.cache/public-keys.env';

export function seedPublicKeys(lease: string, live: string): string {
  const source = path.join(live, PUBLIC_KEYS);
  if (!fs.existsSync(source))
    return `${PUBLIC_KEYS}: none in the main checkout, a renet build reads Bitwarden`;
  const dest = path.join(lease, PUBLIC_KEYS);
  if (!fs.existsSync(path.join(lease, 'private', 'account')))
    return `${PUBLIC_KEYS}: no private/account in this tree`;
  const kept = publicKeyLines(fs.readFileSync(source, 'utf8'));
  // tree-write: safe a directory inside the lease tree, which is ignored and never the live tree
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  // tree-write: safe a path inside the lease tree, which is ignored and never the live tree
  fs.writeFileSync(dest, kept.join('\n') + '\n');
  return `${PUBLIC_KEYS}: copied from the main checkout`;
}

/** The lines of a public-key cache that may travel: the version header (`resolve_renet_account_key` reads the first line to accept the cache) and `ACCOUNT_*_PUBLIC_KEY=` assignments. A free comment is dropped, since it could carry anything. */
export function publicKeyLines(text: string): string[] {
  return text
    .split('\n')
    .filter(
      (line) =>
        line.startsWith('# rediacc public-key cache') ||
        /^ACCOUNT_[A-Z0-9_]*_PUBLIC_KEY=/.test(line)
    );
}

export function seedLease(lease: string, live: string, commit: string): string[] {
  try {
    const notes = syncDependencies(lease, live, commit);
    syncBuilds(lease, live);
    linkCaches(lease, live);
    for (const pkg of BUILT_PACKAGES) notes.push(seedDist(lease, live, pkg));
    copyEnvFiles(lease, live);
    notes.push(seedReceipt(lease, live));
    notes.push(seedPublicKeys(lease, live));
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
