#!/usr/bin/env node
/**
 * Check that all dependencies are up-to-date.
 *
 * This script runs `npm outdated` and fails if any dependencies are outdated,
 * unless they are in the blocklist (packages that should NOT be auto-upgraded).
 *
 * Blocklist format (.deps-upgrade-blocklist):
 *   package-name # reason for blocking
 *
 * Usage:
 *   npx tsx scripts/check-deps.ts           # Check for outdated packages
 *   npx tsx scripts/check-deps.ts --upgrade # Upgrade all non-blocked packages
 *   npx tsx scripts/check-deps.ts --help    # Show help
 *
 * Exit codes:
 *   0 - All dependencies are up-to-date (or blocked), or upgrade succeeded
 *   1 - Outdated dependencies found (check mode) or upgrade failed
 */

import { execSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import https from 'node:https';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { BLUE, GREEN, NC, RED, YELLOW } from './utils/console.js';
import { parseBlockeredList, verifyAllBlockers } from './lib/blocker-validator.js';
import { getMinReleaseAgeMs, isWithinFreshnessWindow } from './lib/release-age.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..');
const BLOCKLIST_FILE = path.join(CONSOLE_ROOT, '.deps-upgrade-blocklist');

// Parse command line arguments
const args = process.argv.slice(2);
const showHelp = args.includes('--help') || args.includes('-h');
const upgradeMode = args.includes('--upgrade') || args.includes('-u');

interface ParsedVersion {
  major: number;
  minor: number;
  patch: number;
  prerelease: string | null;
}

interface BlocklistEntry {
  reason: string;
}

interface OutdatedPackageInfo {
  current?: string;
  wanted?: string;
  latest?: string;
  dependent?: string;
  location?: string;
}

interface PackageInfo {
  name: string;
  current: string;
  latest: string;
  wanted?: string;
  reason?: string;
}

/**
 * Categorize outdated packages into must-upgrade vs blocked lists
 */
function categorizePackages(
  outdated: Record<string, OutdatedPackageInfo>,
  blocklist: Map<string, BlocklistEntry>,
): { mustUpgrade: PackageInfo[]; blocked: PackageInfo[] } {
  const mustUpgrade: PackageInfo[] = [];
  const blocked: PackageInfo[] = [];

  for (const [name, info] of Object.entries(outdated)) {
    const current = info.current;
    const latest = info.latest;

    if (!current || current === 'undefined' || !latest || current === latest) continue;

    const blockEntry = blocklist.get(name);
    if (blockEntry) {
      blocked.push({ name, current, latest, reason: blockEntry.reason });
    } else {
      mustUpgrade.push({ name, current, latest, wanted: info.wanted });
    }
  }

  return { mustUpgrade, blocked };
}

// Cache for changelog URLs to avoid duplicate fetches
const changelogCache = new Map<string, string | null>();

/**
 * Find which workspace packages contain a given dependency
 */
function findWorkspacesWithPackage(packageName: string): string[] {
  const workspaces: string[] = [];
  const packagesDir = path.join(CONSOLE_ROOT, 'packages');

  if (!fs.existsSync(packagesDir)) return workspaces;

  for (const dir of fs.readdirSync(packagesDir)) {
    const pkgPath = path.join(packagesDir, dir, 'package.json');
    if (!fs.existsSync(pkgPath)) continue;

    try {
      const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf-8')) as {
        dependencies?: Record<string, string>;
        devDependencies?: Record<string, string>;
        peerDependencies?: Record<string, string>;
      };
      const allDeps = {
        ...pkg.dependencies,
        ...pkg.devDependencies,
        ...pkg.peerDependencies,
      };

      if (packageName in allDeps) {
        workspaces.push(dir);
      }
    } catch {
      // Skip invalid package.json files
    }
  }

  return workspaces;
}

/**
 * Parse a semver version string into components
 */
function parseVersion(version: string): ParsedVersion | null {
  const match = version.match(/^(\d+)\.(\d+)\.(\d+)(?:-(.+))?$/);
  if (!match) return null;
  return {
    major: Number.parseInt(match[1], 10),
    minor: Number.parseInt(match[2], 10),
    patch: Number.parseInt(match[3], 10),
    prerelease: match[4] || null,
  };
}

/**
 * Check if upgrade is a major version bump
 */
function isMajorUpgrade(current: string, latest: string): boolean {
  if (!current || !latest) return false;
  const vc = parseVersion(current);
  const vl = parseVersion(latest);
  if (!vc || !vl) return false;
  return vl.major > vc.major;
}

/**
 * Load and parse the blocklist file. Uses the shared BLOCKER-aware parser
 * and fails loudly if any entry is missing a substantive "# BLOCKER: <reason>"
 * comment (the same rules enforced across every other suppression mechanism
 * in the repo — see scripts/lib/blocker-validator.ts).
 */
function loadBlocklist(): Map<string, BlocklistEntry> {
  const blocklist = new Map<string, BlocklistEntry>();
  if (!fs.existsSync(BLOCKLIST_FILE)) return blocklist;

  const entries = parseBlockeredList(BLOCKLIST_FILE);
  const failures = verifyAllBlockers(entries, BLOCKLIST_FILE);
  if (failures.length > 0) {
    console.error(`${RED}✗${NC} BLOCKER validation failed for ${BLOCKLIST_FILE}:`);
    for (const f of failures) console.error(f);
    console.error(
      `\n${RED}✗${NC} Blocklist entries must carry a substantive '# BLOCKER: <reason>' — strict gate enforced`,
    );
    process.exit(1);
  }
  for (const { entry, blocker } of entries) {
    blocklist.set(entry, { reason: blocker });
  }
  return blocklist;
}

/**
 * Get outdated packages using npm outdated
 */
class DepsProbeError extends Error {}

/**
 * Run `npm outdated --json` and return its parsed report, or THROW.
 *
 * This function exists because every path that used to `return {}` here was a
 * FAIL-OPEN, and it was not theoretical. Proven 2026-08-15 by pointing the gate
 * at a dead registry:
 *
 *   npm_config_registry=http://127.0.0.1:9/ npx tsx scripts/check-deps.ts
 *   -> "All dependencies are up-to-date", exit 0
 *
 * An empty report and an unreachable registry are indistinguishable to the
 * caller, so the gate asserted the STRONGEST possible claim ("everything is
 * current") precisely when it had learned nothing. In CI, one registry blip or
 * rate-limit turned the dependency-freshness gate into a no-op. It was caught
 * only because the gate answered exit 0 and exit 1 two minutes apart with no
 * intervening change.
 *
 * The contract now: a parsed JSON object is the ONLY success. `npm outdated`
 * exits 0 with an empty report when nothing is outdated and 1 with a populated
 * one when something is, so the exit code alone never decides anything here.
 * Anything else -- no stdout, unparseable stdout, a non-object -- throws.
 */
function runNpmOutdated(cwd: string, extraArgs = ''): Record<string, OutdatedPackageInfo> {
  const command = `npm outdated --json${extraArgs ? ` ${extraArgs}` : ''}`;
  let stdout = '';
  let stderr = '';

  // Control seam: forces a failure branch with no network and no waiting, so
  // --selftest can prove this gate is still able to fail. '1' reproduces a probe
  // that produced nothing; 'error-json' reproduces the REAL shape npm emits when
  // it cannot reach the registry (see the error-key check below), which is the
  // one that actually shipped as a fail-open.
  const forceMode = process.env.CHECK_DEPS_FORCE_PROBE_FAILURE ?? '';
  const forced = forceMode === '1';
  const forcedErrorJson = forceMode === 'error-json';

  try {
    if (forcedErrorJson) {
      stdout = JSON.stringify({
        error: { code: 'ECONNREFUSED', summary: 'simulated unreachable registry', detail: '' },
      });
      throw new Error('simulated npm failure');
    }
    stdout = forced
      ? execSync('sh -c \'echo "simulated probe failure" >&2; exit 1\'', {
          cwd,
          encoding: 'utf-8',
          stdio: ['pipe', 'pipe', 'pipe'],
        })
      : execSync(command, { cwd, encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] });
  } catch (error) {
    const execError = error as { stdout?: string; stderr?: string };
    if (!forcedErrorJson) {
      stdout = execError.stdout ?? '';
    }
    stderr = execError.stderr ?? '';
  }

  const trimmed = stdout.trim();
  if (trimmed === '') {
    throw new DepsProbeError(
      `\`${command}\` produced no output in ${path.relative(CONSOLE_ROOT, cwd) || '.'}. ` +
        'That is a probe that did not run, not a clean result. ' +
        `stderr: ${stderr.trim() || '(empty)'}`,
    );
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    throw new DepsProbeError(
      `\`${command}\` returned unparseable output in ${path.relative(CONSOLE_ROOT, cwd) || '.'}. ` +
        `stderr: ${stderr.trim() || '(empty)'}`,
    );
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    throw new DepsProbeError(`\`${command}\` returned ${typeof parsed}, expected a JSON object.`);
  }

  // The one that actually bit us. `npm outdated --json` does NOT fail loudly when
  // it cannot reach the registry: it prints a well-formed object whose only key
  // is `error`, e.g.
  //   {"error":{"code":"ECONNREFUSED","summary":"request to .../typescript failed",...}}
  // That parses fine, contains no outdated packages, and therefore reads as
  // "everything is current" -- the strongest possible claim, made from zero
  // information. Verified against npm 10 with a dead registry, 2026-08-15.
  const errorPayload = (parsed as { error?: { code?: string; summary?: string } }).error;
  if (errorPayload) {
    throw new DepsProbeError(
      `\`${command}\` could not reach the registry from ${path.relative(CONSOLE_ROOT, cwd) || '.'}: ` +
        `${errorPayload.code ?? 'unknown'} ${errorPayload.summary ?? ''}`.trim(),
    );
  }
  return parsed as Record<string, OutdatedPackageInfo>;
}

function getOutdatedPackages(): Record<string, OutdatedPackageInfo> {
  return runNpmOutdated(CONSOLE_ROOT);
}

/**
 * Find private packages that are outside npm workspaces
 */
function getPrivatePackageDirs(): string[] {
  const privateDir = path.join(CONSOLE_ROOT, 'private');
  if (!fs.existsSync(privateDir)) return [];

  const dirs: string[] = [];
  for (const dir of fs.readdirSync(privateDir)) {
    const pkgPath = path.join(privateDir, dir, 'package.json');
    if (fs.existsSync(pkgPath)) {
      dirs.push(path.join(privateDir, dir));
    }
  }
  return dirs;
}

interface PrivateOutdatedResult {
  dir: string;
  name: string;
  packages: Record<string, OutdatedPackageInfo>;
}

/**
 * Get outdated packages from private (non-workspace) packages
 */
function getPrivateOutdatedPackages(): PrivateOutdatedResult[] {
  const results: PrivateOutdatedResult[] = [];

  for (const dir of getPrivatePackageDirs()) {
    // --package-lock-only so the check works in CI where node_modules is not
    // installed for private submodule packages. A failure here THROWS rather
    // than logging and continuing: this loop used to treat an unreachable
    // registry in one directory as "that directory has nothing outdated".
    const packages = runNpmOutdated(dir, '--package-lock-only');
    if (Object.keys(packages).length > 0) {
      results.push({ dir, name: path.relative(CONSOLE_ROOT, dir), packages });
    }
  }

  return results;
}

/**
 * Fetch package info from npm registry and extract changelog URL
 */
async function fetchChangelogUrl(packageName: string): Promise<string | null> {
  // Check cache first
  if (changelogCache.has(packageName)) {
    return changelogCache.get(packageName) ?? null;
  }

  return new Promise((resolve) => {
    const url = `https://registry.npmjs.org/${encodeURIComponent(packageName)}`;

    const req = https.get(url, { timeout: 5000 }, (res) => {
      let data = '';

      res.on('data', (chunk: Buffer) => {
        data += chunk.toString();
      });

      res.on('end', () => {
        try {
          const json = JSON.parse(data) as { repository?: { url?: string } };
          const repoUrl = json.repository?.url ?? '';

          // Transform git URL to GitHub releases URL
          // Examples:
          //   git+https://github.com/owner/repo.git -> https://github.com/owner/repo/releases
          //   git://github.com/owner/repo.git -> https://github.com/owner/repo/releases
          //   https://github.com/owner/repo.git -> https://github.com/owner/repo/releases
          let changelogUrl: string | null = null;

          if (repoUrl.includes('github.com')) {
            const match = repoUrl.match(/github\.com[/:]([\w.-]+)\/([\w.-]+?)(\.git)?$/);
            if (match) {
              changelogUrl = `https://github.com/${match[1]}/${match[2]}/releases`;
            }
          } else if (repoUrl.includes('gitlab.com')) {
            const match = repoUrl.match(/gitlab\.com[/:]([\w.-]+)\/([\w.-]+?)(\.git)?$/);
            if (match) {
              changelogUrl = `https://gitlab.com/${match[1]}/${match[2]}/-/releases`;
            }
          }

          changelogCache.set(packageName, changelogUrl);
          resolve(changelogUrl);
        } catch {
          changelogCache.set(packageName, null);
          resolve(null);
        }
      });
    });

    req.on('error', () => {
      changelogCache.set(packageName, null);
      resolve(null);
    });

    req.on('timeout', () => {
      req.destroy();
      changelogCache.set(packageName, null);
      resolve(null);
    });
  });
}

/**
 * Fetch changelog URLs for multiple packages in parallel
 */
async function fetchChangelogUrls(packages: PackageInfo[]): Promise<Map<string, string | null>> {
  const results = new Map<string, string | null>();
  const promises = packages.map(async (pkg) => {
    const url = await fetchChangelogUrl(pkg.name);
    results.set(pkg.name, url);
  });
  await Promise.all(promises);
  return results;
}

// getMinReleaseAgeMs / startOfNextUtcDay / isWithinFreshnessWindow now live in
// scripts/lib/release-age.ts, shared with the embed-asset freshness gate.

// Cache for version publish timestamps to avoid duplicate registry fetches.
const publishTimeCache = new Map<string, number | null>();

/**
 * Fetch the publish timestamp (epoch ms) of a specific package version from the
 * npm registry's `time` map. Returns null on any failure (treated as installable
 * so a registry hiccup never silently suppresses a real upgrade).
 */
async function fetchVersionPublishTime(packageName: string, version: string): Promise<number | null> {
  const cacheKey = `${packageName}@${version}`;
  if (publishTimeCache.has(cacheKey)) {
    return publishTimeCache.get(cacheKey) ?? null;
  }

  return new Promise((resolve) => {
    const url = `https://registry.npmjs.org/${encodeURIComponent(packageName)}`;
    const req = https.get(url, { timeout: 5000 }, (res) => {
      let data = '';
      res.on('data', (chunk: Buffer) => {
        data += chunk.toString();
      });
      res.on('end', () => {
        try {
          const json = JSON.parse(data) as { time?: Record<string, string> };
          const stamp = json.time?.[version];
          const ms = stamp ? Date.parse(stamp) : Number.NaN;
          const val = Number.isNaN(ms) ? null : ms;
          publishTimeCache.set(cacheKey, val);
          resolve(val);
        } catch {
          publishTimeCache.set(cacheKey, null);
          resolve(null);
        }
      });
    });
    req.on('error', () => {
      publishTimeCache.set(cacheKey, null);
      resolve(null);
    });
    req.on('timeout', () => {
      req.destroy();
      publishTimeCache.set(cacheKey, null);
      resolve(null);
    });
  });
}

/**
 * Split must-upgrade packages into those eligible to bump now vs those still
 * within the freshness window. A version becomes eligible only at the next UTC
 * midnight after it has aged the base window (minimum-release-age), so all of a
 * day's freshly-aged versions surface together the next day rather than hourly.
 * Deferring a still-fresh `latest` avoids churning the tree (and re-failing the
 * gate an hour later) for a version that is only a few hours past the window.
 *
 * Keep this in sync with the bash twin `is_release_deferred` in
 * .ci/scripts/lib/release-age.sh (audit + go gates).
 *
 * Fail-closed: a null publish time (registry hiccup) is treated as too-new/
 * deferred, so a transient lookup failure never becomes a false "must upgrade".
 */
async function partitionByReleaseAge(
  packages: PackageInfo[],
  minReleaseAgeMs: number,
  nowMs: number,
): Promise<{ installable: PackageInfo[]; tooNew: PackageInfo[] }> {
  if (minReleaseAgeMs <= 0 || packages.length === 0) {
    return { installable: packages, tooNew: [] };
  }
  const installable: PackageInfo[] = [];
  const tooNew: PackageInfo[] = [];
  await Promise.all(
    packages.map(async (pkg) => {
      const published = await fetchVersionPublishTime(pkg.name, pkg.latest);
      // Fail-closed: a null publish time (registry hiccup) is treated as too-new.
      if (published === null || isWithinFreshnessWindow(published, nowMs, minReleaseAgeMs)) {
        tooNew.push(pkg);
      } else {
        installable.push(pkg);
      }
    }),
  );
  return { installable, tooNew };
}

/** Format the `name: current -> latest (major)` summary for one package. */
function formatPackage(pkg: PackageInfo): string {
  const majorTag = isMajorUpgrade(pkg.current, pkg.latest) ? ' (major)' : '';
  return `${pkg.name}: ${pkg.current} -> ${pkg.latest}${majorTag}`;
}

/**
 * Print one package line plus its optional reason/changelog. `suffix` annotates
 * the line (e.g. " (blocked)" or " (account)"); `changelogUrls` is omitted in
 * upgrade mode where changelogs aren't fetched.
 */
function printPackage(
  pkg: PackageInfo,
  opts: { suffix?: string; changelogUrls?: Map<string, string | null> } = {},
): void {
  console.log(`  ${formatPackage(pkg)}${opts.suffix ?? ''}`);
  if (pkg.reason) {
    console.log(`    Reason: ${pkg.reason}`);
  }
  const changelog = opts.changelogUrls?.get(pkg.name);
  if (changelog) {
    console.log(`    Changelog: ${changelog}`);
  }
}

/**
 * Print a labeled group of packages (header + each line). Returns early when the
 * group is empty so callers don't need their own length guards.
 */
function printPackageGroup(
  header: string,
  packages: PackageInfo[],
  opts: { suffix?: string; changelogUrls?: Map<string, string | null> } = {},
): void {
  if (packages.length === 0) return;
  console.log(header);
  console.log();
  for (const pkg of packages) {
    printPackage(pkg, opts);
  }
  console.log();
}

/**
 * Upgrade packages using npm install
 *
 * Intelligently handles workspace vs root-only dependencies:
 * - Packages that exist in child package.json files: use -ws to update version specifiers
 * - Packages that only exist in root: install without -ws to avoid corrupting child packages
 */
function upgradePackages(packages: PackageInfo[]): boolean {
  if (packages.length === 0) {
    console.log(`${GREEN}No packages to upgrade${NC}`);
    return true;
  }

  // Separate packages into workspace-wide vs root-only
  const workspacePackages: Array<PackageInfo & { workspaces: string[] }> = [];
  const rootOnlyPackages: PackageInfo[] = [];

  for (const pkg of packages) {
    const workspaces = findWorkspacesWithPackage(pkg.name);
    if (workspaces.length > 0) {
      workspacePackages.push({ ...pkg, workspaces });
    } else {
      rootOnlyPackages.push(pkg);
    }
  }

  let success = true;

  // Upgrade workspace packages (target each workspace individually to avoid polluting others)
  if (workspacePackages.length > 0) {
    console.log(`${BLUE}Upgrading ${workspacePackages.length} workspace package(s)...${NC}\n`);
    for (const pkg of workspacePackages) {
      const majorTag = isMajorUpgrade(pkg.current, pkg.latest) ? ' (major)' : '';
      console.log(`  ${pkg.name}: ${pkg.current} -> ${pkg.latest}${majorTag}`);
      console.log(`    in: ${pkg.workspaces.join(', ')}`);
    }
    console.log();

    // Group by workspace to batch installs
    const byWorkspace = new Map<string, string[]>();
    for (const pkg of workspacePackages) {
      for (const ws of pkg.workspaces) {
        const existing = byWorkspace.get(ws) ?? [];
        existing.push(`${pkg.name}@latest`);
        byWorkspace.set(ws, existing);
      }
    }

    for (const [ws, installArgs] of byWorkspace) {
      const wsResult = spawnSync('npm', ['install', `-w=packages/${ws}`, ...installArgs], {
        cwd: CONSOLE_ROOT,
        stdio: 'inherit',
        shell: true,
      });
      if (wsResult.status !== 0) success = false;
    }
  }

  // Upgrade root-only packages (no -ws flag to avoid corrupting child packages)
  if (rootOnlyPackages.length > 0) {
    console.log(`${BLUE}Upgrading ${rootOnlyPackages.length} root-only package(s)...${NC}\n`);
    for (const pkg of rootOnlyPackages) {
      const majorTag = isMajorUpgrade(pkg.current, pkg.latest) ? ' (major)' : '';
      console.log(`  ${pkg.name}: ${pkg.current} -> ${pkg.latest}${majorTag}`);
    }
    console.log();

    const rootInstallArgs = rootOnlyPackages.map((p) => `${p.name}@latest`);
    const rootResult = spawnSync('npm', ['install', ...rootInstallArgs], {
      cwd: CONSOLE_ROOT,
      stdio: 'inherit',
      shell: true,
    });
    if (rootResult.status !== 0) success = false;
  }

  if (success) {
    console.log(`\n${GREEN}Upgrades completed${NC}`);
  } else {
    console.log(`\n${RED}Some upgrades failed${NC}`);
  }
  return success;
}

/**
 * Upgrade outdated packages in a private (non-workspace) package directory
 */
function upgradePrivatePackages(dir: string, packages: PackageInfo[]): boolean {
  if (packages.length === 0) return true;

  console.log(`${BLUE}Upgrading ${packages.length} package(s) in ${path.relative(CONSOLE_ROOT, dir)}...${NC}\n`);
  for (const pkg of packages) {
    const majorTag = isMajorUpgrade(pkg.current, pkg.latest) ? ' (major)' : '';
    console.log(`  ${pkg.name}: ${pkg.current} -> ${pkg.latest}${majorTag}`);
  }
  console.log();

  const installArgs = packages.map((p) => `${p.name}@latest`);
  const result = spawnSync('npm', ['install', ...installArgs], {
    cwd: dir,
    stdio: 'inherit',
    shell: true,
  });

  return result.status === 0;
}

/**
 * Show help message
 */
function showHelpMessage(): void {
  console.log(`
${BLUE}check-deps.ts${NC} - Dependency version enforcement

${YELLOW}USAGE${NC}
  npx tsx scripts/check-deps.ts [OPTIONS]

${YELLOW}OPTIONS${NC}
  --upgrade, -u   Upgrade all outdated packages (including major versions)
  --help, -h      Show this help message

${YELLOW}DESCRIPTION${NC}
  Checks for outdated npm dependencies and fails if any are found.
  Packages can be blocklisted in .deps-upgrade-blocklist to prevent
  auto-upgrades (e.g., packages requiring manual migration).

${YELLOW}BLOCKLIST FORMAT${NC}
  package-name # reason for blocking

${YELLOW}EXAMPLES${NC}
  npx tsx scripts/check-deps.ts           # Check for outdated packages
  npx tsx scripts/check-deps.ts --upgrade # Upgrade all outdated packages
  npm run check:deps                      # Via npm script
  npm run check:deps -- --upgrade         # Upgrade via npm script
  ./go quality deps                       # Via go script
`);
}

/**
 * Main check function
 */
async function checkDependencies(): Promise<void> {
  if (showHelp) {
    showHelpMessage();
    process.exit(0);
  }

  console.log('Checking dependency versions...\n');

  const outdated = getOutdatedPackages();
  const blocklist = loadBlocklist();

  const { mustUpgrade: mustUpgradeAll, blocked } = categorizePackages(outdated, blocklist);

  // Also check private (non-workspace) packages
  const privateOutdated = getPrivateOutdatedPackages();
  const privateMustUpgradeAll: Array<{ dir: string; name: string; packages: PackageInfo[] }> = [];
  const privateBlocked: Array<{ dir: string; name: string; packages: PackageInfo[] }> = [];

  for (const { dir, name, packages } of privateOutdated) {
    const { mustUpgrade: dirMustUpgrade, blocked: dirBlocked } = categorizePackages(packages, blocklist);
    if (dirMustUpgrade.length > 0) privateMustUpgradeAll.push({ dir, name, packages: dirMustUpgrade });
    if (dirBlocked.length > 0) privateBlocked.push({ dir, name, packages: dirBlocked });
  }

  // Defer packages whose `latest` is still inside the freshness window (aged <
  // 24h, rounded up to the next UTC day): too fresh to be a real "must upgrade".
  // This auto-resolves as a daily batch once the version ages out — no manual
  // blocklist churn for every freshly-published patch.
  const minReleaseAgeMs = getMinReleaseAgeMs();
  const nowMs = Date.now();

  const { installable: mustUpgrade, tooNew } = await partitionByReleaseAge(mustUpgradeAll, minReleaseAgeMs, nowMs);

  const privateMustUpgrade: Array<{ dir: string; name: string; packages: PackageInfo[] }> = [];
  const privateTooNew: Array<{ dir: string; name: string; packages: PackageInfo[] }> = [];
  for (const { dir, name, packages } of privateMustUpgradeAll) {
    const { installable, tooNew: dirTooNew } = await partitionByReleaseAge(packages, minReleaseAgeMs, nowMs);
    if (installable.length > 0) privateMustUpgrade.push({ dir, name, packages: installable });
    if (dirTooNew.length > 0) privateTooNew.push({ dir, name, packages: dirTooNew });
  }

  const totalBlocked = blocked.length + privateBlocked.reduce((s, p) => s + p.packages.length, 0);
  const totalTooNew = tooNew.length + privateTooNew.reduce((s, p) => s + p.packages.length, 0);

  // Helper: one-line summary of the non-failing categories (blocked + too-new).
  const deferredSummary = (): string => {
    const parts: string[] = [];
    if (totalBlocked > 0) parts.push(`${totalBlocked} blocked`);
    if (totalTooNew > 0) parts.push(`${totalTooNew} too new`);
    return parts.length > 0 ? ` (${parts.join(', ')})` : '';
  };

  // In upgrade mode, upgrade all non-blocked, installable packages.
  if (upgradeMode) {
    const allEmpty = mustUpgrade.length === 0 && privateMustUpgrade.length === 0;

    if (allEmpty) {
      console.log(`${GREEN}All dependencies are up-to-date${NC}${deferredSummary()}`);
      for (const pkg of blocked) {
        printPackage(pkg, { suffix: ' (blocked)' });
      }
      for (const { name: dirName, packages: pkgs } of privateBlocked) {
        for (const pkg of pkgs) printPackage(pkg, { suffix: ` (blocked, ${dirName})` });
      }
      for (const pkg of tooNew) {
        printPackage(pkg, { suffix: ' (too new — deferred until next UTC day)' });
      }
      for (const { name: dirName, packages: pkgs } of privateTooNew) {
        for (const pkg of pkgs) printPackage(pkg, { suffix: ` (too new, ${dirName})` });
      }
      process.exit(0);
    }

    let success = true;
    if (mustUpgrade.length > 0) {
      success = upgradePackages(mustUpgrade) && success;
    }
    for (const { dir, packages: pkgs } of privateMustUpgrade) {
      success = upgradePrivatePackages(dir, pkgs) && success;
    }
    process.exit(success ? 0 : 1);
  }

  // Check mode - fetch changelog URLs for all packages that will be displayed.
  const allPrivatePackages = [privateMustUpgrade, privateBlocked, privateTooNew].flatMap((g) =>
    g.flatMap((p) => p.packages),
  );
  const allPackages = [...mustUpgrade, ...blocked, ...tooNew, ...allPrivatePackages];
  const changelogUrls = await fetchChangelogUrls(allPackages);

  // Check mode - output results. Only must-upgrade (installable) packages fail.
  const hasFailure = mustUpgrade.length > 0 || privateMustUpgrade.length > 0;

  printPackageGroup(`${RED}Outdated packages (must upgrade):${NC}`, mustUpgrade, { changelogUrls });
  for (const { name: dirName, packages: pkgs } of privateMustUpgrade) {
    printPackageGroup(`${RED}Outdated packages in ${dirName} (must upgrade):${NC}`, pkgs, { changelogUrls });
  }

  if (hasFailure) {
    console.log(`Run: npm run check:deps -- --upgrade`);
    console.log(`Or:  npx tsx scripts/check-deps.ts --upgrade`);
    console.log();
  }

  // Too-new packages are informational, never a failure: they are still within
  // the freshness window (deferred until the next UTC day after aging 24h) and
  // surface as a batch once eligible.
  if (totalTooNew > 0) {
    console.log(`${YELLOW}Too new — within freshness window, deferred until next UTC day (${totalTooNew}):${NC}`);
    console.log();
    for (const pkg of tooNew) {
      printPackage(pkg, { changelogUrls });
    }
    for (const { name: dirName, packages: pkgs } of privateTooNew) {
      for (const pkg of pkgs) {
        printPackage(pkg, { suffix: ` (${dirName})`, changelogUrls });
      }
    }
    console.log();
  }

  if (totalBlocked > 0) {
    console.log(`${YELLOW}Blocked packages (${totalBlocked}):${NC}`);
    console.log();
    for (const pkg of blocked) {
      printPackage(pkg, { changelogUrls });
    }
    for (const { name: dirName, packages: pkgs } of privateBlocked) {
      for (const pkg of pkgs) {
        printPackage(pkg, { suffix: ` (${dirName})`, changelogUrls });
      }
    }
    console.log();
  }

  if (hasFailure) {
    console.log(`${RED}Dependency check FAILED${NC}`);
    process.exit(1);
  }

  console.log(`${GREEN}All dependencies are up-to-date${NC}${deferredSummary()}`);
  process.exit(0);
}

/**
 * Control: prove this gate can still FAIL.
 *
 * A dependency-freshness gate that silently passes when it cannot reach the
 * registry is worse than no gate, because it answers "everything is current".
 * This re-runs the real script with the probe forced to fail and asserts a
 * non-zero exit, offline and in milliseconds. Run by `--selftest`.
 */
function selftest(): void {
  // Two shapes, because they failed open for two different reasons and only the
  // second one ever shipped. Each must make the gate exit non-zero WITH its own
  // message, so a gate that merely dies for an unrelated reason cannot pass here.
  //
  // process.execArgv carries tsx's own loader flags (--require preflight.cjs,
  // --import loader.mjs). Without them the child is a bare node that cannot
  // resolve this file's .js-suffixed TS imports, and the control would "fire"
  // on a module-resolution error instead of on the thing it is testing.
  const cases = [
    { mode: '1', expect: 'did not run', label: 'a probe that produced no output' },
    {
      mode: 'error-json',
      expect: 'could not reach the registry',
      label: "npm's error-shaped report",
    },
  ];

  for (const { mode, expect, label } of cases) {
    const child = spawnSync(process.execPath, [...process.execArgv, process.argv[1]], {
      cwd: CONSOLE_ROOT,
      encoding: 'utf-8',
      env: { ...process.env, CHECK_DEPS_FORCE_PROBE_FAILURE: mode },
    });
    const output = `${child.stdout ?? ''}${child.stderr ?? ''}`;

    if (child.status === 0) {
      console.error(
        `${RED}\u2717${NC} CONTROL DID NOT FIRE for ${label}: the gate still exited 0.\n` +
          '  That is the exact fail-open this control exists to prevent (see runNpmOutdated).',
      );
      process.exit(1);
    }
    if (!output.includes(expect)) {
      console.error(
        `${RED}\u2717${NC} the gate failed for ${label}, but without the expected message\n` +
          `  (${expect}), so the failure may be incidental. Output was:\n${output}`,
      );
      process.exit(1);
    }
    if (output.includes('All dependencies are up-to-date')) {
      console.error(
        `${RED}\u2717${NC} the gate printed the up-to-date claim while failing on ${label}.`,
      );
      process.exit(1);
    }
  }

  console.log(
    `${GREEN}\u2713${NC} control fired on both shapes: an unrunnable probe and an unreachable ` +
      'registry each fail the gate instead of passing it',
  );
  process.exit(0);
}

// Run the check
if (process.argv.includes('--selftest')) {
  selftest();
} else {
  checkDependencies().catch((error: unknown) => {
    if (error instanceof DepsProbeError) {
      console.error(`${RED}✗${NC} dependency probe failed: ${error.message}`);
      console.error(
        `${RED}✗${NC} Refusing to report "up-to-date" from a check that did not run.\n` +
          '  If the registry is unreachable, fix that and re-run; do not treat this as a pass.',
      );
      process.exit(1);
    }
    throw error;
  });
}
