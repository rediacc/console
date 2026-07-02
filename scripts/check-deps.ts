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
function getOutdatedPackages(): Record<string, OutdatedPackageInfo> {
  try {
    // npm outdated returns exit code 1 if there are outdated packages
    execSync('npm outdated --json', {
      cwd: CONSOLE_ROOT,
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    // If we get here, no outdated packages
    return {};
  } catch (error) {
    // npm outdated returns exit code 1 when packages are outdated
    const execError = error as { stdout?: string };
    if (execError.stdout) {
      try {
        return JSON.parse(execError.stdout) as Record<string, OutdatedPackageInfo>;
      } catch {
        console.error('Failed to parse npm outdated output');
        return {};
      }
    }
    return {};
  }
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
    try {
      // Use --package-lock-only so the check works in CI where node_modules
      // is not installed for private submodule packages. npm reads installed
      // versions from package-lock.json and queries the registry for latest.
      execSync('npm outdated --json --package-lock-only', {
        cwd: dir,
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe'],
      });
    } catch (error) {
      const execError = error as { stdout?: string; stderr?: string };
      if (execError.stdout) {
        try {
          const packages = JSON.parse(execError.stdout) as Record<string, OutdatedPackageInfo>;
          if (Object.keys(packages).length > 0) {
            const dirName = path.relative(CONSOLE_ROOT, dir);
            results.push({ dir, name: dirName, packages });
          }
        } catch (jsonError) {
          console.error(`Failed to parse 'npm outdated' output for ${dir}:`, jsonError);
        }
      } else {
        console.error(`'npm outdated' failed in ${dir}:`, execError.stderr || error);
      }
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

const NPMRC_FILE = path.join(CONSOLE_ROOT, '.npmrc');

/**
 * Read the `minimum-release-age` setting (in minutes) from .npmrc and return it
 * in milliseconds — the base freshness window for this CI gate (pinned to 1440 =
 * 24h). NOTE: `minimum-release-age` is our CI-gate knob, NOT npm's native install
 * guard (npm's real key is `min-release-age`, in days); see the .npmrc comment.
 * The actual deferral rounds this up to the next UTC day (see startOfNextUtcDay).
 * Returns 0 when the setting is absent (feature disabled — no deferral).
 */
function getMinReleaseAgeMs(): number {
  try {
    const content = fs.readFileSync(NPMRC_FILE, 'utf-8');
    const m = content.match(/^\s*minimum-release-age\s*=\s*(\d+)/m);
    if (m) return Number(m[1]) * 60 * 1000;
  } catch {
    // No .npmrc — feature disabled.
  }
  return 0;
}

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
 * Epoch ms of 00:00:00 UTC on the day AFTER the day that contains `ms`. Used to
 * batch freshness deferral onto a daily boundary: a version that ages past the
 * base window on a given UTC day becomes eligible together with every other such
 * version at the following midnight, so a day's upgrades surface as one batch
 * instead of trickling in one-at-a-time as each crosses its own T+24h moment.
 */
function startOfNextUtcDay(ms: number): number {
  const d = new Date(ms);
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + 1);
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
      if (published === null || nowMs < startOfNextUtcDay(published + minReleaseAgeMs)) {
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

// Run the check
checkDependencies();
