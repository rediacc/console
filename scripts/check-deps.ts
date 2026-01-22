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
 * Load and parse the blocklist file
 */
function loadBlocklist(): Map<string, BlocklistEntry> {
  const blocklist = new Map<string, BlocklistEntry>();

  if (!fs.existsSync(BLOCKLIST_FILE)) {
    return blocklist;
  }

  const content = fs.readFileSync(BLOCKLIST_FILE, 'utf-8');
  const lines = content.split('\n');

  for (const line of lines) {
    const trimmed = line.trim();

    // Skip empty lines and comments
    if (!trimmed || trimmed.startsWith('#')) {
      continue;
    }

    // Parse: package-name # reason
    const commentIndex = trimmed.indexOf('#');
    const packageName = commentIndex >= 0 ? trimmed.slice(0, commentIndex).trim() : trimmed;
    const reason = commentIndex >= 0 ? trimmed.slice(commentIndex + 1).trim() : '';

    if (!packageName) {
      continue;
    }

    blocklist.set(packageName, { reason });
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

  // Upgrade workspace-wide packages (updates version specifiers in child package.json)
  if (workspacePackages.length > 0) {
    console.log(`${BLUE}Upgrading ${workspacePackages.length} workspace package(s)...${NC}\n`);
    for (const pkg of workspacePackages) {
      const majorTag = isMajorUpgrade(pkg.current, pkg.latest) ? ' (major)' : '';
      console.log(`  ${pkg.name}: ${pkg.current} -> ${pkg.latest}${majorTag}`);
      console.log(`    in: ${pkg.workspaces.join(', ')}`);
    }
    console.log();

    const wsInstallArgs = workspacePackages.map((p) => `${p.name}@latest`);
    const wsResult = spawnSync('npm', ['install', '-ws', ...wsInstallArgs], {
      cwd: CONSOLE_ROOT,
      stdio: 'inherit',
      shell: true,
    });
    if (wsResult.status !== 0) success = false;
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

  const mustUpgrade: PackageInfo[] = [];
  const blocked: PackageInfo[] = [];

  for (const [name, info] of Object.entries(outdated)) {
    const current = info.current;
    const latest = info.latest;

    // Skip if current equals latest (shouldn't happen, but just in case)
    if (current === latest) {
      continue;
    }

    // Skip optional dependencies that aren't installed (current is undefined)
    if (!current || current === 'undefined') {
      continue;
    }

    if (!latest) {
      continue;
    }

    const blockEntry = blocklist.get(name);

    if (blockEntry) {
      // Package is blocked from upgrading - skip it
      blocked.push({
        name,
        current,
        latest,
        reason: blockEntry.reason,
      });
    } else {
      // Not in blocklist - must upgrade
      mustUpgrade.push({ name, current, latest, wanted: info.wanted });
    }
  }

  // In upgrade mode, upgrade all non-blocked packages
  if (upgradeMode) {
    if (mustUpgrade.length === 0) {
      if (blocked.length > 0) {
        console.log(`${GREEN}All dependencies are up-to-date${NC} (${blocked.length} blocked)\n`);
        for (const pkg of blocked) {
          const majorTag = isMajorUpgrade(pkg.current, pkg.latest) ? ' (major)' : '';
          console.log(`  ${pkg.name}: ${pkg.current} -> ${pkg.latest}${majorTag} (blocked)`);
        }
      } else {
        console.log(`${GREEN}All dependencies are up-to-date${NC}`);
      }
      process.exit(0);
    }

    const success = upgradePackages(mustUpgrade);
    process.exit(success ? 0 : 1);
  }

  // Check mode - fetch changelog URLs for all packages that will be displayed
  const allPackages = [...mustUpgrade, ...blocked];
  const changelogUrls = await fetchChangelogUrls(allPackages);

  // Check mode - output results
  let hasFailure = false;

  if (mustUpgrade.length > 0) {
    hasFailure = true;
    console.log(`${RED}Outdated packages (must upgrade):${NC}\n`);
    for (const pkg of mustUpgrade) {
      const majorTag = isMajorUpgrade(pkg.current, pkg.latest) ? ' (major)' : '';
      console.log(`  ${pkg.name}: ${pkg.current} -> ${pkg.latest}${majorTag}`);
      const changelog = changelogUrls.get(pkg.name);
      if (changelog) {
        console.log(`    Changelog: ${changelog}`);
      }
    }
    console.log();
    console.log(`Run: npm run check:deps -- --upgrade`);
    console.log(`Or:  npx tsx scripts/check-deps.ts --upgrade`);
    console.log();
  }

  if (blocked.length > 0) {
    console.log(`${YELLOW}Blocked packages (${blocked.length}):${NC}\n`);
    for (const pkg of blocked) {
      const majorTag = isMajorUpgrade(pkg.current, pkg.latest) ? ' (major)' : '';
      console.log(`  ${pkg.name}: ${pkg.current} -> ${pkg.latest}${majorTag}`);
      if (pkg.reason) {
        console.log(`    Reason: ${pkg.reason}`);
      }
      const changelog = changelogUrls.get(pkg.name);
      if (changelog) {
        console.log(`    Changelog: ${changelog}`);
      }
    }
    console.log();
  }

  if (hasFailure) {
    console.log(`${RED}Dependency check FAILED${NC}`);
    process.exit(1);
  }

  if (blocked.length > 0) {
    console.log(`${GREEN}All dependencies are up-to-date${NC} (${blocked.length} blocked)`);
  } else {
    console.log(`${GREEN}All dependencies are up-to-date${NC}`);
  }
  process.exit(0);
}

// Run the check
checkDependencies();
