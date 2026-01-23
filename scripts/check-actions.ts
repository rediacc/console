#!/usr/bin/env node
/**
 * Check that all GitHub Actions are up-to-date.
 *
 * This script parses workflow files and checks if actions are outdated,
 * unless they are in the blocklist (actions that should NOT be upgraded).
 *
 * Blocklist format (.actions-upgrade-blocklist):
 *   owner/repo # reason for blocking
 *
 * Usage:
 *   npx tsx scripts/check-actions.ts           # Check for outdated actions
 *   npx tsx scripts/check-actions.ts --verbose # Show all actions
 *   npx tsx scripts/check-actions.ts --help    # Show help
 *
 * Exit codes:
 *   0 - All actions are up-to-date (or blocked)
 *   1 - Outdated actions found
 */

import fs from 'node:fs';
import https from 'node:https';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { BLUE, DIM, GREEN, NC, RED, YELLOW } from './utils/console.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..');
const WORKFLOWS_DIR = path.join(CONSOLE_ROOT, '.github', 'workflows');
const BLOCKLIST_FILE = path.join(CONSOLE_ROOT, '.actions-upgrade-blocklist');

// Parse command line arguments
const args = process.argv.slice(2);
const showHelp = args.includes('--help') || args.includes('-h');
const verboseMode = args.includes('--verbose') || args.includes('-v');

// GitHub token from environment (optional, increases rate limit)
const GITHUB_TOKEN = process.env.GITHUB_TOKEN ?? process.env.GH_TOKEN;

interface ParsedVersion {
  major: number;
  minor: number;
  patch: number;
  full: string;
}

interface ActionLocation {
  file: string;
  line: number;
}

interface ActionInfo {
  version: string | null;
  sha: string | null;
  locations: ActionLocation[];
}

interface BlocklistEntry {
  reason: string;
}

interface GitHubRelease {
  tag: string;
  url: string;
  targetCommit: string;
}

interface ActionResult extends ActionInfo {
  name: string;
  latest?: string;
  releaseUrl?: string;
  reason?: string;
}

/**
 * Parse a version string (e.g., "v5", "v5.1.0") into components
 */
function parseVersion(version: string): ParsedVersion | null {
  if (!version) return null;

  // Remove 'v' prefix if present
  const v = version.replace(/^v/, '');

  // Handle simple major version (e.g., "5")
  if (/^\d+$/.test(v)) {
    return { major: Number.parseInt(v, 10), minor: 0, patch: 0, full: version };
  }

  // Handle semver (e.g., "5.1.0")
  const match = v.match(/^(\d+)(?:\.(\d+))?(?:\.(\d+))?/);
  if (!match) return null;

  return {
    major: Number.parseInt(match[1], 10),
    minor: match[2] ? Number.parseInt(match[2], 10) : 0,
    patch: match[3] ? Number.parseInt(match[3], 10) : 0,
    full: version,
  };
}

/**
 * Compare two versions: returns -1 if a < b, 0 if a == b, 1 if a > b
 *
 * If the current version is a major-only version (e.g., "v3"), only compare major versions.
 * This handles floating major version tags used in GitHub Actions.
 */
function compareVersions(a: string, b: string): number {
  const va = parseVersion(a);
  const vb = parseVersion(b);

  if (!va || !vb) return 0;

  // Check if 'a' is a major-only version (e.g., "v3" vs "v3.1.0")
  // Major-only versions are considered floating tags that track latest in that major line
  const aIsMajorOnly = /^v?\d+$/.test(a.replace(/^v/, ''));

  if (va.major !== vb.major) return va.major < vb.major ? -1 : 1;

  // If 'a' is major-only, consider it equal if majors match
  if (aIsMajorOnly) return 0;

  if (va.minor !== vb.minor) return va.minor < vb.minor ? -1 : 1;
  if (va.patch !== vb.patch) return va.patch < vb.patch ? -1 : 1;

  return 0;
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

    // Parse: owner/repo # reason
    const commentIndex = trimmed.indexOf('#');
    const actionName = commentIndex >= 0 ? trimmed.slice(0, commentIndex).trim() : trimmed;
    const reason = commentIndex >= 0 ? trimmed.slice(commentIndex + 1).trim() : '';

    if (!actionName) {
      continue;
    }

    blocklist.set(actionName, { reason });
  }

  return blocklist;
}

/**
 * Parse workflow files and extract action references
 */
function parseWorkflowFiles(): Map<string, ActionInfo> {
  const actions = new Map<string, ActionInfo>();

  if (!fs.existsSync(WORKFLOWS_DIR)) {
    console.error(`Workflows directory not found: ${WORKFLOWS_DIR}`);
    return actions;
  }

  const files = fs
    .readdirSync(WORKFLOWS_DIR)
    .filter((f) => f.endsWith('.yml') || f.endsWith('.yaml'));

  for (const file of files) {
    const filePath = path.join(WORKFLOWS_DIR, file);
    const content = fs.readFileSync(filePath, 'utf-8');
    const lines = content.split('\n');

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const lineNum = i + 1;

      // Match: uses: owner/repo@ref  # optional comment
      const match = line.match(/uses:\s*([\w.-]+\/[\w.-]+)@(\S+)(?:\s+#\s*(.+))?/);
      if (!match) continue;

      const [, actionName, ref, comment] = match;

      // Skip local actions (./path) and actions from this repo
      if (actionName.startsWith('.') || actionName.startsWith('rediacc/')) {
        continue;
      }

      // Determine version from comment or ref
      // Common formats:
      //   owner/repo@sha  # v5
      //   owner/repo@v5
      //   owner/repo@v5.1.0
      let version: string | null = null;
      let sha: string | null = null;

      // Check if ref looks like a SHA (40 hex chars)
      if (/^[a-f0-9]{40}$/i.test(ref)) {
        sha = ref;
        // Try to get version from comment
        if (comment) {
          const versionMatch = comment.match(/v?\d+(?:\.\d+)*(?:\.\d+)?/);
          if (versionMatch) {
            version = versionMatch[0];
            if (!version.startsWith('v')) version = `v${version}`;
          }
        }
      } else if (ref.startsWith('v') || /^\d+/.test(ref)) {
        // ref is a version tag
        version = ref.startsWith('v') ? ref : `v${ref}`;
      } else {
        // ref might be a branch name (e.g., "main")
        version = ref;
      }

      const location: ActionLocation = { file, line: lineNum };

      if (actions.has(actionName)) {
        const existing = actions.get(actionName)!;
        existing.locations.push(location);
      } else {
        actions.set(actionName, {
          version,
          sha,
          locations: [location],
        });
      }
    }
  }

  return actions;
}

/**
 * Fetch latest release for an action from GitHub API
 */
async function fetchLatestRelease(owner: string, repo: string): Promise<GitHubRelease | null> {
  return new Promise((resolve) => {
    const url = `/repos/${owner}/${repo}/releases/latest`;

    const options: https.RequestOptions = {
      hostname: 'api.github.com',
      path: url,
      method: 'GET',
      headers: {
        'User-Agent': 'check-actions-script',
        Accept: 'application/vnd.github.v3+json',
      },
      timeout: 10000,
    };

    if (GITHUB_TOKEN) {
      options.headers = {
        ...options.headers,
        Authorization: `Bearer ${GITHUB_TOKEN}`,
      };
    }

    const req = https.request(options, (res) => {
      let data = '';

      res.on('data', (chunk: Buffer) => {
        data += chunk.toString();
      });

      res.on('end', () => {
        if (res.statusCode === 200) {
          try {
            const json = JSON.parse(data) as {
              tag_name: string;
              html_url: string;
              target_commitish: string;
            };
            resolve({
              tag: json.tag_name,
              url: json.html_url,
              targetCommit: json.target_commitish,
            });
          } catch {
            resolve(null);
          }
        } else if (res.statusCode === 404) {
          // No releases, try to get latest tag
          resolve(null);
        } else if (res.statusCode === 403) {
          // Rate limited
          console.error(
            `${YELLOW}Rate limited by GitHub API. Set GITHUB_TOKEN for higher limits.${NC}`
          );
          resolve(null);
        } else {
          resolve(null);
        }
      });
    });

    req.on('error', () => {
      resolve(null);
    });

    req.on('timeout', () => {
      req.destroy();
      resolve(null);
    });

    req.end();
  });
}

/**
 * Fetch latest releases for multiple actions in parallel
 */
async function fetchLatestReleases(
  actions: Map<string, ActionInfo>
): Promise<Map<string, GitHubRelease | null>> {
  const results = new Map<string, GitHubRelease | null>();
  const promises: Promise<void>[] = [];

  for (const [actionName] of actions) {
    const [owner, repo] = actionName.split('/');
    promises.push(
      fetchLatestRelease(owner, repo).then((release) => {
        results.set(actionName, release);
      })
    );
  }

  await Promise.all(promises);
  return results;
}

/**
 * Show help message
 */
function showHelpMessage(): void {
  console.log(`
${BLUE}check-actions.ts${NC} - GitHub Actions version enforcement

${YELLOW}USAGE${NC}
  npx tsx scripts/check-actions.ts [OPTIONS]

${YELLOW}OPTIONS${NC}
  --verbose, -v  Show all actions including up-to-date ones
  --help, -h     Show this help message

${YELLOW}ENVIRONMENT${NC}
  GITHUB_TOKEN   GitHub token for higher API rate limits (optional)

${YELLOW}DESCRIPTION${NC}
  Checks for outdated GitHub Actions in workflow files and fails if any
  are found. Actions can be blocklisted in .actions-upgrade-blocklist to
  prevent upgrade enforcement (e.g., actions requiring workflow changes).

${YELLOW}BLOCKLIST FORMAT${NC}
  owner/repo # reason for blocking

${YELLOW}EXAMPLES${NC}
  npx tsx scripts/check-actions.ts           # Check for outdated actions
  npx tsx scripts/check-actions.ts --verbose # Show all actions
  npm run check:actions                      # Via npm script
  ./go quality actions                       # Via go script
`);
}

/**
 * Main check function
 */
async function checkActions(): Promise<void> {
  if (showHelp) {
    showHelpMessage();
    process.exit(0);
  }

  console.log('Checking GitHub Actions versions...\n');

  const actions = parseWorkflowFiles();
  const blocklist = loadBlocklist();

  if (actions.size === 0) {
    console.log(`${GREEN}No external actions found in workflow files${NC}`);
    process.exit(0);
  }

  console.log(`Found ${actions.size} unique action(s). Fetching latest versions...\n`);

  const latestReleases = await fetchLatestReleases(actions);

  const mustUpgrade: ActionResult[] = [];
  const blocked: ActionResult[] = [];
  const upToDate: ActionResult[] = [];
  const unknown: ActionResult[] = [];

  for (const [actionName, info] of actions) {
    const release = latestReleases.get(actionName);
    const blockEntry = blocklist.get(actionName);

    if (!release) {
      unknown.push({ name: actionName, ...info });
      continue;
    }

    const latestVersion = release.tag;
    const currentVersion = info.version;

    // Skip if we couldn't determine the current version
    if (!currentVersion) {
      unknown.push({ name: actionName, ...info, latest: latestVersion, releaseUrl: release.url });
      continue;
    }

    // Compare versions
    const comparison = compareVersions(currentVersion, latestVersion);

    if (comparison >= 0) {
      // Up to date
      upToDate.push({
        name: actionName,
        ...info,
        latest: latestVersion,
        releaseUrl: release.url,
      });
      continue;
    }

    // Outdated - check blocklist
    if (blockEntry) {
      // Action is blocked from upgrading
      blocked.push({
        name: actionName,
        ...info,
        latest: latestVersion,
        releaseUrl: release.url,
        reason: blockEntry.reason,
      });
    } else {
      // Not in blocklist - must upgrade
      mustUpgrade.push({
        name: actionName,
        ...info,
        latest: latestVersion,
        releaseUrl: release.url,
      });
    }
  }

  // Output results
  let hasFailure = false;

  if (mustUpgrade.length > 0) {
    hasFailure = true;
    console.log(`${RED}Outdated actions (must upgrade):${NC}\n`);
    for (const action of mustUpgrade) {
      console.log(`  ${action.name}: ${action.version} -> ${action.latest}`);
      if (action.sha) {
        console.log(`    Current SHA: ${action.sha}`);
      }
      console.log(`    Release: ${action.releaseUrl}`);
      console.log(`    Files: ${action.locations.map((l) => `${l.file}:${l.line}`).join(', ')}`);
    }
    console.log();
    console.log(`To upgrade, update the action reference in the workflow file(s).`);
    console.log(`For pinned SHAs, visit the release page to get the new SHA.`);
    console.log();
  }

  if (blocked.length > 0) {
    console.log(`${YELLOW}Blocked actions (${blocked.length}):${NC}\n`);
    for (const action of blocked) {
      console.log(`  ${action.name}: ${action.version} -> ${action.latest}`);
      if (action.reason) {
        console.log(`    Reason: ${action.reason}`);
      }
      console.log(`    Release: ${action.releaseUrl}`);
    }
    console.log();
  }

  if (unknown.length > 0 && verboseMode) {
    console.log(`${DIM}Unknown actions (${unknown.length}):${NC}\n`);
    for (const action of unknown) {
      console.log(`  ${action.name}: ${action.version ?? 'unknown'}`);
      console.log(`    Could not fetch latest release (may not use GitHub Releases)`);
      console.log(`    Files: ${action.locations.map((l) => `${l.file}:${l.line}`).join(', ')}`);
    }
    console.log();
  }

  if (upToDate.length > 0 && verboseMode) {
    console.log(`${GREEN}Up-to-date actions (${upToDate.length}):${NC}\n`);
    for (const action of upToDate) {
      console.log(`  ${action.name}: ${action.version}`);
    }
    console.log();
  }

  if (hasFailure) {
    console.log(`${RED}GitHub Actions check FAILED${NC}`);
    process.exit(1);
  }

  const summary: string[] = [];
  if (upToDate.length > 0) summary.push(`${upToDate.length} up-to-date`);
  if (blocked.length > 0) summary.push(`${blocked.length} blocked`);
  if (unknown.length > 0) summary.push(`${unknown.length} unknown`);

  console.log(
    `${GREEN}All GitHub Actions are up-to-date${NC}${summary.length > 0 ? ` (${summary.join(', ')})` : ''}`
  );
  process.exit(0);
}

// Run the check
checkActions();
