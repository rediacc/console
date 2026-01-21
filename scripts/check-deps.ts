#!/usr/bin/env node
/**
 * Check that all dependencies are up-to-date.
 *
 * This script runs `npm outdated` and fails if any dependencies are outdated,
 * unless they are in the allowlist with a valid version constraint.
 *
 * Allowlist format (.deps-outdated-allowlist):
 *   package-name@<max-version # reason
 *
 * Usage:
 *   npx tsx scripts/check-deps.ts           # Check for outdated packages
 *   npx tsx scripts/check-deps.ts --upgrade # Upgrade outdated packages
 *   npx tsx scripts/check-deps.ts --help    # Show help
 *
 * Exit codes:
 *   0 - All dependencies are up-to-date (or allowlisted), or upgrade succeeded
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
const ALLOWLIST_FILE = path.join(CONSOLE_ROOT, '.deps-outdated-allowlist');

// Parse command line arguments
const args = process.argv.slice(2);
const showHelp = args.includes('--help') || args.includes('-h');
const upgradeMode = args.includes('--upgrade') || args.includes('-u');
const forceMode = args.includes('--force') || args.includes('-f');

interface ParsedVersion {
  major: number;
  minor: number;
  patch: number;
  prerelease: string | null;
}

interface AllowlistEntry {
  constraint: string;
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
  constraint?: string;
  reason?: string;
}

// Cache for changelog URLs to avoid duplicate fetches
const changelogCache = new Map<string, string | null>();

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
 * Compare two versions: returns -1 if a < b, 0 if a == b, 1 if a > b
 */
function compareVersions(a: string, b: string): number {
  const va = parseVersion(a);
  const vb = parseVersion(b);

  if (!va || !vb) return 0;

  if (va.major !== vb.major) return va.major < vb.major ? -1 : 1;
  if (va.minor !== vb.minor) return va.minor < vb.minor ? -1 : 1;
  if (va.patch !== vb.patch) return va.patch < vb.patch ? -1 : 1;

  // Prerelease versions are less than release versions
  if (va.prerelease && !vb.prerelease) return -1;
  if (!va.prerelease && vb.prerelease) return 1;

  return 0;
}

/**
 * Check if version satisfies constraint (e.g., "<3.0.0")
 */
function satisfiesConstraint(version: string, constraint: string): boolean {
  if (!constraint.startsWith('<')) {
    console.error(`Invalid constraint format: ${constraint} (must start with '<')`);
    return false;
  }

  const maxVersion = constraint.slice(1);
  return compareVersions(version, maxVersion) < 0;
}

/**
 * Load and parse the allowlist file
 */
function loadAllowlist(): Map<string, AllowlistEntry> {
  const allowlist = new Map<string, AllowlistEntry>();

  if (!fs.existsSync(ALLOWLIST_FILE)) {
    return allowlist;
  }

  const content = fs.readFileSync(ALLOWLIST_FILE, 'utf-8');
  const lines = content.split('\n');

  for (const line of lines) {
    const trimmed = line.trim();

    // Skip empty lines and comments
    if (!trimmed || trimmed.startsWith('#')) {
      continue;
    }

    // Parse: package-name@<version # reason
    const commentIndex = trimmed.indexOf('#');
    const spec = commentIndex >= 0 ? trimmed.slice(0, commentIndex).trim() : trimmed;
    const reason = commentIndex >= 0 ? trimmed.slice(commentIndex + 1).trim() : '';

    // Find the @ that separates package name from version constraint
    // Handle scoped packages like @scope/package@<1.0.0
    const atIndex = spec.lastIndexOf('@');
    if (atIndex <= 0) {
      console.error(`Invalid allowlist entry: ${trimmed}`);
      continue;
    }

    const packageName = spec.slice(0, atIndex);
    const constraint = spec.slice(atIndex + 1);

    if (!constraint.startsWith('<')) {
      console.error(`Invalid constraint in allowlist: ${constraint} (must start with '<')`);
      continue;
    }

    allowlist.set(packageName, { constraint, reason });
  }

  return allowlist;
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
 * Upgrade packages using npm install (npm update doesn't update to latest within semver range)
 */
function upgradePackages(packages: PackageInfo[], forceMajor = false): boolean {
  if (packages.length === 0) {
    console.log(`${GREEN}No packages to upgrade${NC}`);
    return true;
  }

  // Separate minor/patch updates from major updates
  const minorUpdates = packages.filter((p) => !isMajorUpgrade(p.current, p.latest));
  const majorUpdates = packages.filter((p) => isMajorUpgrade(p.current, p.latest));

  let success = true;

  // Run npm install for minor/patch updates (npm update doesn't update to latest within semver)
  if (minorUpdates.length > 0) {
    console.log(`${BLUE}Upgrading ${minorUpdates.length} package(s) (minor/patch)...${NC}\n`);

    const installArgs = minorUpdates.map((p) => `${p.name}@latest`);
    const result = spawnSync('npm', ['install', '-ws', ...installArgs], {
      cwd: CONSOLE_ROOT,
      stdio: 'inherit',
      shell: true,
    });

    if (result.status !== 0) {
      console.log(`\n${RED}Minor/patch upgrade failed${NC}`);
      success = false;
    } else {
      console.log(`\n${GREEN}Minor/patch upgrades completed${NC}`);
    }
  }

  // Handle major updates
  if (majorUpdates.length > 0) {
    console.log();
    if (forceMajor) {
      console.log(`${BLUE}Upgrading ${majorUpdates.length} package(s) (major)...${NC}\n`);

      // Use npm install package@latest for major updates
      const installArgs = majorUpdates.map((p) => `${p.name}@latest`);
      const result = spawnSync('npm', ['install', '-ws', ...installArgs], {
        cwd: CONSOLE_ROOT,
        stdio: 'inherit',
        shell: true,
      });

      if (result.status !== 0) {
        console.log(`\n${RED}Major upgrade failed${NC}`);
        success = false;
      } else {
        console.log(`\n${GREEN}Major upgrades completed${NC}`);
      }
    } else {
      console.log(`${YELLOW}Major version upgrades available (${majorUpdates.length}):${NC}\n`);
      for (const pkg of majorUpdates) {
        console.log(`  ${pkg.name}: ${pkg.current} -> ${pkg.latest}`);
      }
      console.log();
      console.log(`These require manual review. To upgrade, run:`);
      console.log(`  npx tsx scripts/check-deps.ts --upgrade --force`);
      console.log(
        `Or manually: npm install ${majorUpdates.map((p) => `${p.name}@latest`).join(' ')}`
      );
    }
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
  --upgrade, -u   Upgrade outdated packages (minor/patch only)
  --force, -f     With --upgrade: also upgrade major versions
  --help, -h      Show this help message

${YELLOW}DESCRIPTION${NC}
  Checks for outdated npm dependencies and fails if any are found.
  Packages can be allowlisted in .deps-outdated-allowlist with a
  max version constraint to defer upgrades.

${YELLOW}ALLOWLIST FORMAT${NC}
  package-name@<max-version # reason

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
  const allowlist = loadAllowlist();

  const mustUpgrade: PackageInfo[] = [];
  const constraintExceeded: PackageInfo[] = [];
  const allowed: PackageInfo[] = [];

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

    const allowEntry = allowlist.get(name);

    if (allowEntry) {
      // Check if latest version exceeds the constraint
      if (satisfiesConstraint(latest, allowEntry.constraint)) {
        // Allowed - latest is still under the max version
        allowed.push({
          name,
          current,
          latest,
          constraint: allowEntry.constraint,
          reason: allowEntry.reason,
        });
      } else {
        // Constraint exceeded - latest version is at or above max
        constraintExceeded.push({
          name,
          current,
          latest,
          constraint: allowEntry.constraint,
          reason: allowEntry.reason,
        });
      }
    } else {
      // Not in allowlist - must upgrade
      mustUpgrade.push({ name, current, latest, wanted: info.wanted });
    }
  }

  // In upgrade mode, upgrade all outdated packages (except allowlisted)
  if (upgradeMode) {
    const packagesToUpgrade = [...mustUpgrade, ...constraintExceeded];

    if (packagesToUpgrade.length === 0) {
      if (allowed.length > 0) {
        console.log(
          `${GREEN}All dependencies are up-to-date${NC} (${allowed.length} allowlisted)\n`
        );
        for (const pkg of allowed) {
          console.log(
            `  ${pkg.name}: ${pkg.current} -> ${pkg.latest} (allowed: ${pkg.constraint})`
          );
        }
      } else {
        console.log(`${GREEN}All dependencies are up-to-date${NC}`);
      }
      process.exit(0);
    }

    console.log(`Found ${packagesToUpgrade.length} package(s) to upgrade:\n`);
    for (const pkg of packagesToUpgrade) {
      const majorTag = isMajorUpgrade(pkg.current, pkg.latest) ? ' (major)' : '';
      console.log(`  ${pkg.name}: ${pkg.current} -> ${pkg.latest}${majorTag}`);
    }
    console.log();

    const success = upgradePackages(packagesToUpgrade, forceMode);
    process.exit(success ? 0 : 1);
  }

  // Check mode - fetch changelog URLs for all packages that will be displayed
  const allPackages = [...mustUpgrade, ...constraintExceeded, ...allowed];
  const changelogUrls = await fetchChangelogUrls(allPackages);

  // Check mode - output results
  let hasFailure = false;

  if (constraintExceeded.length > 0) {
    hasFailure = true;
    console.log(`${RED}Allowlist constraint exceeded:${NC}\n`);
    for (const pkg of constraintExceeded) {
      console.log(`  ${pkg.name}: ${pkg.current} -> ${pkg.latest}`);
      console.log(`    Allowed: ${pkg.constraint}, but latest is ${pkg.latest}`);
      console.log(`    Action: Review allowlist, package may now be compatible`);
      if (pkg.reason) {
        console.log(`    Original reason: ${pkg.reason}`);
      }
      const changelog = changelogUrls.get(pkg.name);
      if (changelog) {
        console.log(`    Changelog: ${changelog}`);
      }
      console.log();
    }
  }

  if (mustUpgrade.length > 0) {
    hasFailure = true;
    console.log(`${RED}Outdated packages (must upgrade):${NC}\n`);
    for (const pkg of mustUpgrade) {
      console.log(`  ${pkg.name}: ${pkg.current} -> ${pkg.latest}`);
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

  if (allowed.length > 0) {
    console.log(`${YELLOW}Allowlisted packages (${allowed.length}):${NC}\n`);
    for (const pkg of allowed) {
      console.log(`  ${pkg.name}: ${pkg.current} -> ${pkg.latest} (allowed: ${pkg.constraint})`);
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

  if (allowed.length > 0) {
    console.log(`${GREEN}All dependencies are up-to-date${NC} (${allowed.length} allowlisted)`);
  } else {
    console.log(`${GREEN}All dependencies are up-to-date${NC}`);
  }
  process.exit(0);
}

// Run the check
checkDependencies();
