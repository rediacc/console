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
import { collectActionRefs } from './lib/action-refs.js';
import { parseBlockeredList, verifyAllBlockers } from './lib/blocker-validator.js';
import { getMinReleaseAgeMs, isWithinFreshnessWindow } from './lib/release-age.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const CONSOLE_ROOT = path.resolve(__dirname, '..');
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
  /** ISO8601 from the release payload; absent if the API omitted it. */
  publishedAt?: string;
}

interface ActionResult extends ActionInfo {
  name: string;
  latest?: string;
  releaseUrl?: string;
  reason?: string;
}

/**
 * Is this release too fresh to demand an upgrade to?
 *
 * WHY THIS EXISTS. This gate had no notion of release age, so an action
 * published MINUTES ago turned the build red and the only ways out were to pin
 * a barely-vetted SHA or to blocklist a version that is not actually blocked.
 * Observed 2026-07-28: docker/login-action v4.5.2 was published at 07:04:43Z and
 * had reddened the gate by 07:21Z, seventeen minutes later.
 *
 * Delegates to the SHARED window in ./lib/release-age.js rather than carrying
 * its own copy, so this gate, check-deps and check-embed-asset-freshness all
 * read `minimum-release-age` from .npmrc and all inherit the same round-up to
 * the next UTC day, which batches a day's upgrades into one surfacing instead of
 * trickling them in one at a time. An action pin is the same kind of dependency
 * as an npm one and gets the same treatment.
 *
 * NULL POLICY IS FAIL-CLOSED, matching check-deps: a missing or unparseable
 * timestamp defers, because a lookup hiccup must never manufacture a "you must
 * upgrade now" failure. (check-embed-asset-freshness deliberately chooses the
 * opposite for dateless git tags; the lib leaves the choice to the caller.)
 *
 * `minReleaseAgeMs` is injectable purely so tests can drive both directions:
 * with a zero window nothing defers, which is what proves the deferral is doing
 * one specific thing rather than muting the gate.
 */
export function isReleaseDeferred(
  publishedAt: string | undefined,
  nowMs: number = Date.now(),
  minReleaseAgeMs: number = getMinReleaseAgeMs()
): boolean {
  if (!publishedAt) return true;
  const published = Date.parse(publishedAt);
  if (Number.isNaN(published)) return true;
  return isWithinFreshnessWindow(published, nowMs, minReleaseAgeMs);
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

  // Use the shared BLOCKER parser/validator rather than a bespoke one, so this
  // suppression mechanism is held to the same standard as every other list in
  // the repo (see docs/agent-reference/suppressions.md, "Suppression mechanisms and the BLOCKER
  // convention"). Previously this file accepted any trailing comment — or none
  // at all — as a "reason", which is how it stayed outside the convention.
  // Mirrors loadBlocklist() in check-deps.ts.
  const entries = parseBlockeredList(BLOCKLIST_FILE);
  const failures = verifyAllBlockers(entries, BLOCKLIST_FILE);
  if (failures.length > 0) {
    console.error(`${RED}✗${NC} BLOCKER validation failed for ${BLOCKLIST_FILE}:`);
    for (const f of failures) console.error(f);
    console.error(
      `\n${RED}✗${NC} Blocked actions must carry a substantive '# BLOCKER: <reason>' explaining why the upgrade cannot be taken`
    );
    process.exit(1);
  }
  for (const { entry, blocker } of entries) {
    blocklist.set(entry, { reason: blocker });
  }

  return blocklist;
}

/**
 * Parse workflow files and extract action references
 */
function parseWorkflowFiles(): Map<string, ActionInfo> {
  const actions = new Map<string, ActionInfo>();

  // Scanning is delegated to collectActionRefs(), which covers BOTH
  // .github/workflows and composite actions under .github/actions. Keeping one
  // scanner matters: this gate and scripts/check-suppression-liveness.ts must
  // agree on what "referenced" means, or one will condemn what the other sees.
  //
  // The composite half was a real blind spot — actions/create-github-app-token
  // is pinned only in .github/actions/app-token/action.yml, so the action that
  // mints every CI token in this repo went unchecked for freshness.
  for (const [actionName, refs] of collectActionRefs(CONSOLE_ROOT)) {
    let version: string | null = null;
    let sha: string | null = null;
    const { ref, comment } = refs[0];

    // owner/repo@<40-hex sha>  # vX.Y.Z   (the pinned form used throughout)
    if (/^[a-f0-9]{40}$/i.test(ref)) {
      sha = ref;
      if (comment) {
        const versionMatch = comment.match(/v?\d+(?:\.\d+)*(?:\.\d+)?/);
        if (versionMatch) {
          version = versionMatch[0];
          if (!version.startsWith('v')) version = `v${version}`;
        }
      }
    } else if (ref.startsWith('v') || /^\d+/.test(ref)) {
      version = ref.startsWith('v') ? ref : `v${ref}`;
    } else {
      // A branch name such as "main".
      version = ref;
    }

    actions.set(actionName, {
      version,
      sha,
      locations: refs.map((r) => ({ file: r.file, line: r.line })),
    });
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
              published_at?: string;
            };
            resolve({
              tag: json.tag_name,
              url: json.html_url,
              targetCommit: json.target_commitish,
              publishedAt: json.published_at,
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
  const deferred: ActionResult[] = [];
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

    // Outdated, but possibly TOO FRESH to demand. A release published inside the
    // age window is reported as a notice and does not fail the gate: the upgrade
    // is real, it is simply not yet takeable under this repo's supply-chain
    // posture. It becomes a normal finding once the window passes, so nothing is
    // lost, and no blocklist entry has to be invented for a non-blocked version.
    if (isReleaseDeferred(release.publishedAt)) {
      deferred.push({
        name: actionName,
        ...info,
        latest: latestVersion,
        releaseUrl: release.url,
        reason: release.publishedAt
          ? `published ${release.publishedAt}, inside the shared minimum-release-age window`
          : 'no publish date returned by the API (deferring fail-closed)',
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
    // Output is deliberately SHARP, not comprehensive. Listing every call site
    // produced hundreds of file:line entries per action (actions/checkout alone
    // is pinned at 137 sites), which buried the one thing a reader — human or
    // agent — actually needs: the exact command that fixes it.
    console.log(`${RED}Outdated actions (${mustUpgrade.length}):${NC}\n`);
    for (const action of mustUpgrade) {
      const n = action.locations.length;
      console.log(
        `  ${action.name}  ${action.version} -> ${action.latest}  (${n} pin${n === 1 ? '' : 's'})`
      );
      if (action.sha) console.log(`    ${DIM}current sha: ${action.sha}${NC}`);
      console.log(`    ${DIM}${action.releaseUrl}${NC}`);
    }

    console.log(`\n${YELLOW}To upgrade — resolves the new SHA and rewrites every pin:${NC}\n`);
    for (const action of mustUpgrade) {
      if (!action.sha) continue;
      // repos/<repo>/commits/<tag> resolves to the commit SHA for BOTH
      // lightweight and annotated tags, unlike git/ref/tags which returns the
      // tag object for annotated tags and needs a second dereference.
      console.log(`  NEW=$(gh api repos/${action.name}/commits/${action.latest} --jq .sha) && \\`);
      // Search .github, not .github/workflows: composite actions under
      // .github/actions/*/action.yml pin third-party actions too.
      console.log(`    find .github -name '*.yml' -o -name '*.yaml' | xargs sed -i \\`);
      console.log(
        `      "s|${action.name}@${action.sha}\\( *\\)# ${action.version}|${action.name}@\${NEW}\\1# ${action.latest}|g"`
      );
    }
    console.log(`\n  Then re-run: ${YELLOW}npm run check:actions${NC}`);
    console.log(
      `  Verify nothing was missed: ${DIM}grep -rn "<old-sha>" .github/${NC} should return nothing,`
    );
    console.log(
      `  and every workflow must still parse. A major bump (vN -> vN+1) needs a real CI run.\n`
    );
    console.log(`  ${DIM}If an upgrade genuinely cannot be taken, record it in`);
    console.log(`  .actions-upgrade-blocklist (one per line, BLOCKER reason required):${NC}`);
    console.log(`    ${mustUpgrade[0].name}  # BLOCKER: <why this upgrade is not takeable>`);
    console.log();
  }

  // Deferred, not blocked, and deliberately reported even though the gate
  // passes: a silent defer is indistinguishable from a gate that stopped
  // looking, which is the failure mode this repo keeps finding in its own
  // tooling. Naming them means the next run's "must upgrade" is never a
  // surprise.
  if (deferred.length > 0) {
    console.log(`${BLUE}Deferred upgrades (${deferred.length}) -- too fresh to take yet:${NC}\n`);
    for (const action of deferred) {
      console.log(`  ${action.name}: ${action.version} -> ${action.latest}`);
      console.log(`    ${DIM}${action.reason}${NC}`);
    }
    console.log(
      `\n  ${DIM}These are real upgrades held back by the release-age window, the same one`
    );
    console.log(`  .npmrc enforces with minimum-release-age and the Go/npm gates apply via`);
    console.log(`  is_release_deferred. They become normal findings once the window passes.${NC}\n`);
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

  // ANTI-VACUITY. A gate that passes when it checked NOTHING is broken by
  // definition, and this one did exactly that: with every GitHub API lookup
  // rate-limited it printed "All GitHub Actions are up-to-date (14 unknown)"
  // and exited 0. Fourteen unknown means fourteen unchecked, which is the
  // opposite of up-to-date. Measured 2026-07-28 by running the gate without a
  // token until the anonymous rate limit tripped.
  //
  // An offline or rate-limited CI run would therefore have reported freshness it
  // never verified, indefinitely, which is the same swallowed-failure shape this
  // repo keeps finding in its own tooling: empty evidence rendered as a clean
  // result.
  //
  // Scope is deliberately narrow: only a TOTAL lookup failure is fatal. A
  // partial one still proves something about the actions it did reach, and
  // failing the build for one flaky lookup would make the gate the flakiest
  // thing in CI.
  if (actions.size > 0 && unknown.length === actions.size) {
    console.log(
      `${RED}✗ Could not resolve the latest release for ANY of the ${actions.size} action(s).${NC}`
    );
    console.log(
      `${DIM}  Nothing was verified, so "up-to-date" would be a claim about data this run never saw.`
    );
    console.log('  Most likely the anonymous GitHub API rate limit: set GITHUB_TOKEN (or GH_TOKEN)');
    console.log(`  and re-run. CI already sets one, so this is usually a local-only condition.${NC}`);
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
