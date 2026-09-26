#!/usr/bin/env node
/**
 * Check that all dependencies are up-to-date.
 *
 * This script runs `npm outdated` in the console root and in every private/ manifest CI also checks out, and fails if any dependency is outdated, unless it is in the blocklist (packages that should NOT be upgraded) or still inside the release-age freshness window.
 *
 * Blocklist format (.ci/policy/.deps-upgrade-blocklist):
 *   package-name  # BLOCKER: reason for blocking
 *
 * BREAKING UPGRADES ARE NEVER APPLIED BY DEFAULT. A version outside the current caret range (a new major, or a new minor on a 0.x line) is reported as a major awaiting a decision, and --upgrade does not install it anywhere, in the root or in a private/ manifest, unless .ci/config/deps-major-allow.json names it with a reason. Before 2026-09-26 no such rule existed: the root looked safe only because every outdated root major happened to carry its own blocklist line, and `--upgrade` took lucide-react 0 -> 1, @vitejs/plugin-react 4 -> 6 and vite 6 -> 8 in private/account/web because nothing there did.
 *
 * WHAT IS SCANNED, AND WHY LOCAL AND CI NOW AGREE. The private/ manifests scanned are the ones inside a git SUBMODULE declared in .gitmodules (plus the nested manifests in NESTED_PRIVATE_PACKAGE_DIRS), which is exactly the set the quality-content job checks out with `submodules: true`. A gitignored local-only directory such as private/growth is never scanned, because a verdict CI never reaches is not a gate. And every `current` version is read from the manifest's committed package-lock.json, because CI installs no node_modules under private/ and `npm outdated --package-lock-only` then reports NO `current` at all: until 2026-09-26 the gate dropped every such entry as "nothing to judge", so CI's private scan examined all of private/account and judged none of it, while a developer's installed node_modules made the same scan judge real packages locally.
 *
 * Usage:
 *   npx tsx scripts/gates/check-deps.ts           # Check for outdated packages
 *   npx tsx scripts/gates/check-deps.ts --upgrade # Upgrade every non-blocked, non-breaking package
 *   npx tsx scripts/gates/check-deps.ts --help    # Show help
 *
 * Exit codes:
 *   0 - All dependencies are up-to-date (or blocked, or too new), or upgrade succeeded with no major left undecided
 *   1 - Outdated dependencies found (check mode), a major awaits a decision, a version could not be determined, an allow entry is dead, or an upgrade failed
 *
 * ---- gate ----
 * step: External dependency freshness
 * needs: node
 * id: check:deps
 * selftest: true
 * lane: quality-content
 * slow: true
 * ---- end gate ----
 */

import { execSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import https from 'node:https';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  parseBlockeredList,
  validateBlockerQuality,
  verifyAllBlockers,
} from '../lib/blocker-validator.js';
import { BLUE, GREEN, joinReport, NC, RED, YELLOW } from '../lib/console.js';
import { policyPath } from '../lib/policy-paths.js';
import { getMinReleaseAgeMs, isWithinFreshnessWindow } from '../lib/release-age.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// CHECK_DEPS_ROOT is the selftest's seam: it points the whole gate (manifests, lockfiles, blocklist, allow file, release-age config) at a synthetic fixture tree so the --upgrade path can be driven end to end without touching the real one. When it is set, changelog lookups are skipped too, because a fixture never needs them and they are the only network call left.
const FIXTURE_ROOT = process.env.CHECK_DEPS_ROOT;
const CONSOLE_ROOT = FIXTURE_ROOT
  ? path.resolve(FIXTURE_ROOT)
  : path.resolve(__dirname, '..', '..');
const BLOCKLIST_FILE = policyPath('.deps-upgrade-blocklist', CONSOLE_ROOT);
const MAJOR_ALLOW_FILE = path.join(CONSOLE_ROOT, '.ci', 'config', 'deps-major-allow.json');
const MAJOR_ALLOW_REL = '.ci/config/deps-major-allow.json';
const RELEASE_AGE_FILE = path.join(CONSOLE_ROOT, '.ci', 'config', 'release-age.json');

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

/** What `npm outdated --json` really emits: an ARRAY per package when several workspaces depend on it. */
type RawOutdated = Record<string, OutdatedPackageInfo | OutdatedPackageInfo[]>;

interface PackageInfo {
  name: string;
  current: string;
  latest: string;
  wanted?: string;
  reason?: string;
  /** The allow key that authorised a breaking upgrade, when one did. */
  allowKey?: string;
}

interface MajorAllowEntry {
  key: string;
  scope: string | null;
  name: string;
  line: string;
  reason: string;
}

interface Categorized {
  mustUpgrade: PackageInfo[];
  blocked: PackageInfo[];
  /** Breaking upgrades no allow entry names: reported, never installed. */
  heldMajor: PackageInfo[];
  /** Allow keys that authorised something in this pass, for the liveness check. */
  allowUsed: Set<string>;
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

/** Numeric order of two versions; unparseable ones sort as equal so a caller keeps its first pick. */
function compareVersions(a: string, b: string): number {
  const va = parseVersion(a);
  const vb = parseVersion(b);
  if (!va || !vb) return 0;
  return va.major - vb.major || va.minor - vb.minor || va.patch - vb.patch;
}

/**
 * The caret line a version belongs to: '8' for 8.x, '0.575' for 0.575.x, '0.0.3' for 0.0.3. Two versions on different lines are a breaking move under npm's own caret semantics, which is why 0.575 -> 1.48 (lucide-react) counts exactly like 6 -> 8 (vite). Null when the version does not parse.
 */
function releaseLine(version: string): string | null {
  const v = parseVersion(version);
  if (!v) return null;
  if (v.major > 0) return String(v.major);
  if (v.minor > 0) return `0.${v.minor}`;
  return `0.0.${v.patch}`;
}

/**
 * True when moving current -> latest leaves the caret range. An unparseable version on either side counts as breaking: the cost of holding a version the gate cannot classify is one manual decision, the cost of applying it blind is a surprise major.
 */
function isBreakingBump(current: string, latest: string): boolean {
  const lc = releaseLine(current);
  const ll = releaseLine(latest);
  if (!lc || !ll) return true;
  return lc !== ll;
}

/** The allow key a reader would add to take this breaking upgrade in this manifest. */
function suggestedAllowKey(pkg: PackageInfo, scope?: string): string {
  const line = releaseLine(pkg.latest) ?? pkg.latest;
  return `${scope ? `${scope}:` : ''}${pkg.name}@${line}`;
}

/**
 * Categorize outdated packages into must-upgrade, blocked and held-major lists.
 *
 * ONE RULE FOR EVERY MANIFEST. The root pass and each private/ pass come through here with the same blocklist and the same allow list; only `scope` differs, and it only selects which SCOPED entries apply. A breaking bump no allow entry names is held, never must-upgrade, so no install plan built from `mustUpgrade` can contain one.
 */
function categorizePackages(
  outdated: Record<string, OutdatedPackageInfo>,
  blocklist: Map<string, BlocklistEntry>,
  scope?: string,
  allow: MajorAllowEntry[] = []
): Categorized {
  const mustUpgrade: PackageInfo[] = [];
  const blocked: PackageInfo[] = [];
  const heldMajor: PackageInfo[] = [];
  const allowUsed = new Set<string>();

  for (const [name, info] of Object.entries(outdated)) {
    const current = info.current;
    const latest = info.latest;

    if (!current || current === 'undefined' || !latest || current === latest) continue;

    // SCOPED ENTRIES, `<dir>:<package>`, and the reason they had to exist. private/account is under an operator freeze, so seven of its dependencies cannot be upgraded here. Blocking them by bare name was the obvious move and is WRONG: this list is keyed on the package name alone, and FOUR of those seven -- @biomejs/biome, typescript, vitest, hono -- are also console's own
    // dependencies. A bare entry would have silently stopped this gate ever reporting them for the console tree again, which is weakening a live check to record a constraint in a different repository.
    //
    // A scoped key is consulted only when categorising that directory, and the root pass (which passes no scope) can never see one. `:` is safe as the separator because an npm package name cannot contain it.
    const blockEntry =
      (scope ? blocklist.get(`${scope}:${name}`) : undefined) ?? blocklist.get(name);
    if (blockEntry) {
      blocked.push({ name, current, latest, reason: blockEntry.reason });
      continue;
    }

    if (isBreakingBump(current, latest)) {
      const line = releaseLine(latest);
      // A scoped allow entry wins over a bare one only in the sense that either is enough; both carry a reason, and the scoped one is reported when present so the output names the narrower decision.
      const grant =
        allow.find(
          (a) =>
            a.scope === (scope ?? null) && a.scope !== null && a.name === name && a.line === line
        ) ?? allow.find((a) => a.scope === null && a.name === name && a.line === line);
      if (!grant) {
        heldMajor.push({ name, current, latest, wanted: info.wanted });
        continue;
      }
      allowUsed.add(grant.key);
      mustUpgrade.push({ name, current, latest, wanted: info.wanted, allowKey: grant.key });
      continue;
    }

    mustUpgrade.push({ name, current, latest, wanted: info.wanted });
  }

  return { mustUpgrade, blocked, heldMajor, allowUsed };
}

// Cache for changelog URLs to avoid duplicate fetches
const changelogCache = new Map<string, string | null>();

/**
 * Find which workspace packages contain a given dependency
 */
function findWorkspacesWithPackage(packageName: string, root: string = CONSOLE_ROOT): string[] {
  const workspaces: string[] = [];
  const packagesDir = path.join(root, 'packages');

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
 * Load and parse the blocklist file. Uses the shared BLOCKER-aware parser
 * and fails loudly if any entry is missing a substantive "# BLOCKER: <reason>"
 * comment (the same rules enforced across every other suppression mechanism
 * in the repo, see scripts/lib/blocker-validator.ts).
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
      `\n${RED}✗${NC} Blocklist entries must carry a substantive '# BLOCKER: <reason>' (strict gate enforced)`
    );
    process.exit(1);
  }
  for (const { entry, blocker } of entries) {
    blocklist.set(entry, { reason: blocker });
  }
  return blocklist;
}

const ALLOW_KEY_RE = /^(?:([^:\s]+):)?((?:@[^@/\s:]+\/)?[^@/\s:]+)@(\d+(?:\.\d+){0,2})$/;

/**
 * Parse the allow list's JSON text into entries, or return the problems with it. Pure, so the selftest can drive it without a file. Reason QUALITY is checked separately (it shells out to the canonical validator).
 */
function parseMajorAllow(text: string): { entries: MajorAllowEntry[]; problems: string[] } {
  const problems: string[] = [];
  const entries: MajorAllowEntry[] = [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (e) {
    return { entries, problems: [`not valid JSON: ${(e as Error).message}`] };
  }
  const allow = (parsed as { allow?: unknown } | null)?.allow;
  if (typeof allow !== 'object' || allow === null || Array.isArray(allow)) {
    return { entries, problems: ['has no "allow" object (an empty one is {})'] };
  }
  for (const [key, reason] of Object.entries(allow as Record<string, unknown>)) {
    const m = key.match(ALLOW_KEY_RE);
    if (!m) {
      problems.push(
        `"${key}" is not '<package>@<line>' or '<dir>:<package>@<line>' (line = major, or 0.<minor> for 0.x)`
      );
      continue;
    }
    if (typeof reason !== 'string') {
      problems.push(`"${key}" has a ${typeof reason} where the reason string belongs`);
      continue;
    }
    entries.push({ key, scope: m[1] ?? null, name: m[2], line: m[3], reason });
  }
  return { entries, problems };
}

/**
 * Load the breaking-upgrade allow list. A MISSING file is a loud failure rather than "nothing allowed": the file is committed, so its absence means the gate is reading the wrong tree.
 */
function loadMajorAllow(): MajorAllowEntry[] {
  if (!fs.existsSync(MAJOR_ALLOW_FILE)) {
    console.error(
      `${RED}✗${NC} ${MAJOR_ALLOW_FILE} is missing. It is committed with an empty "allow": {} object; ` +
        'its absence means this gate is not reading the tree it thinks it is.'
    );
    process.exit(1);
  }
  const { entries, problems } = parseMajorAllow(fs.readFileSync(MAJOR_ALLOW_FILE, 'utf-8'));
  for (const e of entries) {
    const bad = validateBlockerQuality(e.key, e.reason, MAJOR_ALLOW_REL);
    if (bad) problems.push(bad.message);
  }
  if (problems.length > 0) {
    console.error(`${RED}✗${NC} ${MAJOR_ALLOW_REL} is invalid:`);
    for (const p of problems) console.error(`  ${p}`);
    process.exit(1);
  }
  return entries;
}

/** The `packages` map of a manifest's package-lock.json, or null when there is none. */
function readLockPackages(dir: string): Record<string, { version?: string }> | null {
  const lockPath = path.join(dir, 'package-lock.json');
  if (!fs.existsSync(lockPath)) return null;
  try {
    const lock = JSON.parse(fs.readFileSync(lockPath, 'utf-8')) as {
      packages?: Record<string, { version?: string }>;
    };
    return lock.packages ?? null;
  } catch {
    return null;
  }
}

/**
 * Turn one manifest's raw `npm outdated --json` into one entry per package with a KNOWN current version, and list the packages whose current version could not be determined.
 *
 * Two shapes used to vanish here without a word, both through the `!current` skip in categorizePackages:
 *   1. An ARRAY value, which npm emits when several workspaces depend on one package. At the root that hid tsx, vitest, typescript and @types/node on 2026-09-26: `info.current` of an array is undefined.
 *   2. An entry with no `current`, which is EVERY entry when node_modules is not installed, i.e. every private/ manifest in CI.
 * The committed lockfile is consulted first for `current`, so a local tree with stale node_modules and a CI tree with none both judge the version the lock pins; npm's own `current` is the fallback. An entry neither source can place is returned in `unknown`, which the caller treats as a failure: unknown is unchecked, never fine.
 */
function normalizeOutdated(
  raw: RawOutdated,
  dir: string,
  lock: Record<string, { version?: string }> | null
): { entries: Record<string, OutdatedPackageInfo>; unknown: string[] } {
  const entries: Record<string, OutdatedPackageInfo> = {};
  const unknown: string[] = [];

  for (const [name, value] of Object.entries(raw)) {
    const rows = Array.isArray(value) ? value : [value];
    let chosen: OutdatedPackageInfo | null = null;
    for (const row of rows) {
      const lockKey = row.location
        ? path.relative(dir, row.location).split(path.sep).join('/')
        : `node_modules/${name}`;
      const current =
        lock?.[lockKey]?.version ?? lock?.[`node_modules/${name}`]?.version ?? row.current;
      if (!current || current === 'undefined' || !row.latest) continue;
      if (!chosen || compareVersions(current, chosen.current as string) < 0) {
        chosen = { current, latest: row.latest, wanted: row.wanted };
      }
    }
    if (chosen) {
      entries[name] = chosen;
    } else {
      unknown.push(name);
    }
  }
  return { entries, unknown };
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
 *   npm_config_registry=http://127.0.0.1:9/ npx tsx scripts/gates/check-deps.ts
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

  // Control seam: forces a failure branch with no network and no waiting, so --selftest can prove this gate is still able to fail. '1' reproduces a probe
  // that produced nothing; 'error-json' reproduces the REAL shape npm emits when
  // it cannot reach the registry (see the error-key check below), which is the one that actually shipped as a fail-open.
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
        `stderr: ${stderr.trim() || '(empty)'}`
    );
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    throw new DepsProbeError(
      `\`${command}\` returned unparseable output in ${path.relative(CONSOLE_ROOT, cwd) || '.'}. ` +
        `stderr: ${stderr.trim() || '(empty)'}`
    );
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    throw new DepsProbeError(`\`${command}\` returned ${typeof parsed}, expected a JSON object.`);
  }

  // The one that actually bit us. `npm outdated --json` does NOT fail loudly when it cannot reach the registry: it prints a well-formed object whose only key is `error`, e.g.
  //   {"error":{"code":"ECONNREFUSED","summary":"request to .../typescript failed",...}}
  // That parses fine, contains no outdated packages, and therefore reads as "everything is current" -- the strongest possible claim, made from zero information. Verified against npm 10 with a dead registry, 2026-08-15.
  const errorPayload = (parsed as { error?: { code?: string; summary?: string } }).error;
  if (errorPayload) {
    throw new DepsProbeError(
      `\`${command}\` could not reach the registry from ${path.relative(CONSOLE_ROOT, cwd) || '.'}: ` +
        `${errorPayload.code ?? 'unknown'} ${errorPayload.summary ?? ''}`.trim()
    );
  }
  return parsed as Record<string, OutdatedPackageInfo>;
}

/**
 * Nested manifests one level deeper than the private/<dir> scan below reaches.
 * private/account is a submodule whose own sub-packages (the web frontend, the
 * e2e suite) carry INDEPENDENT package.json + package-lock.json and drift on
 * their own schedule. That is exactly how private/account/web ended up on
 * typescript ^6.0.3 and vitest ^4.1.10 while this gate reported "up-to-date":
 * it only ever looked one level into `private/`, so a manifest nested one
 * level further was invisible to it, not merely blocked or deferred.
 *
 * Listed explicitly rather than walked recursively so this never picks up
 * an unrelated nested manifest (a vendored fixture, a dist/ copy) as something
 * this gate should be reporting on. Each entry must sit inside a declared
 * submodule, and is checked with existsSync below.
 */
const NESTED_PRIVATE_PACKAGE_DIRS = ['account/web', 'account/e2e'];

/** The `private/<x>` submodule paths .gitmodules declares, which is the set CI checks out. */
function declaredPrivateSubmodules(root: string): string[] {
  const gm = path.join(root, '.gitmodules');
  if (!fs.existsSync(gm)) return [];
  const out: string[] = [];
  for (const line of fs.readFileSync(gm, 'utf-8').split('\n')) {
    const m = line.match(/^\s*path\s*=\s*(private\/[^/\s]+)\s*$/);
    if (m) out.push(m[1]);
  }
  return out;
}

/**
 * The private manifests this gate judges: every declared private/ SUBMODULE that carries a package.json, plus the nested manifests listed above inside one. A directory under private/ that is not a submodule (private/growth and private/generative are gitignored local checkouts) is never scanned, because CI does not have it and a verdict CI never reaches is not a gate.
 *
 * `uninitialized` names declared submodules with no checkout (no `.git` inside). Locally that is tolerated and PRINTED; in CI the caller refuses it, since the quality-content job checks submodules out and an empty one there means the checkout failed.
 *
 * `root` defaults to CONSOLE_ROOT and exists so --selftest can point this at a synthetic tree.
 */
function getPrivatePackageDirs(root: string = CONSOLE_ROOT): {
  dirs: string[];
  uninitialized: string[];
} {
  const dirs: string[] = [];
  const uninitialized: string[] = [];
  for (const rel of declaredPrivateSubmodules(root)) {
    const abs = path.join(root, rel);
    if (!fs.existsSync(path.join(abs, '.git'))) {
      uninitialized.push(rel);
      continue;
    }
    if (fs.existsSync(path.join(abs, 'package.json'))) dirs.push(abs);
    const base = rel.slice('private/'.length);
    for (const nested of NESTED_PRIVATE_PACKAGE_DIRS) {
      if (!nested.startsWith(`${base}/`)) continue;
      const nestedAbs = path.join(root, 'private', nested);
      if (fs.existsSync(path.join(nestedAbs, 'package.json'))) dirs.push(nestedAbs);
    }
  }
  return { dirs, uninitialized };
}

interface ManifestResult {
  dir: string;
  /** '' for the console root, else the path from the root, e.g. private/account/web. */
  name: string;
  entries: Record<string, OutdatedPackageInfo>;
  unknown: string[];
}

/** Probe one manifest. --package-lock-only for private/ ones, whose node_modules CI never installs. */
function probeManifest(dir: string, isPrivate: boolean): ManifestResult {
  const raw = runNpmOutdated(dir, isPrivate ? '--package-lock-only' : '') as RawOutdated;
  const { entries, unknown } = normalizeOutdated(raw, dir, readLockPackages(dir));
  return { dir, name: isPrivate ? path.relative(CONSOLE_ROOT, dir) : '', entries, unknown };
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

          // Transform git URL to GitHub releases URL Examples: git+https://github.com/owner/repo.git -> https://github.com/owner/repo/releases git://github.com/owner/repo.git -> https://github.com/owner/repo/releases https://github.com/owner/repo.git -> https://github.com/owner/repo/releases
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

// getMinReleaseAgeMs / startOfNextUtcDay / isWithinFreshnessWindow now live in scripts/lib/release-age.ts, shared with the embed-asset freshness gate.

// Cache for version publish timestamps to avoid duplicate registry fetches.
const publishTimeCache = new Map<string, number | null>();

/**
 * Fetch the publish timestamp (epoch ms) of a specific package version from the
 * npm registry's `time` map. Returns null on any failure (treated as installable
 * so a registry hiccup never silently suppresses a real upgrade).
 */
async function fetchVersionPublishTime(
  packageName: string,
  version: string
): Promise<number | null> {
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
 * midnight after it has aged the base window (.ci/config/release-age.json), so all of a
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
  nowMs: number
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
    })
  );
  return { installable, tooNew };
}

/** Format the `name: current -> latest (major)` summary for one package. */
function formatPackage(pkg: PackageInfo): string {
  const majorTag = isBreakingBump(pkg.current, pkg.latest) ? ' (major)' : '';
  return `${pkg.name}: ${pkg.current} -> ${pkg.latest}${majorTag}`;
}

/**
 * Print one package line plus its optional reason/changelog. `suffix` annotates
 * the line (e.g. " (blocked)" or " (account)"); `changelogUrls` is omitted in
 * upgrade mode where changelogs aren't fetched.
 */
function printPackage(
  pkg: PackageInfo,
  opts: { suffix?: string; changelogUrls?: Map<string, string | null> } = {}
): void {
  console.log(`  ${formatPackage(pkg)}${opts.suffix ?? ''}`);
  if (pkg.reason) {
    console.log(`    Reason: ${pkg.reason}`);
  }
  if (pkg.allowKey) {
    console.log(`    Allowed by: ${MAJOR_ALLOW_REL} "${pkg.allowKey}"`);
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
  opts: { suffix?: string; changelogUrls?: Map<string, string | null> } = {}
): void {
  if (packages.length === 0) return;
  console.log(header);
  console.log();
  for (const pkg of packages) {
    printPackage(pkg, opts);
  }
  console.log();
}

interface InstallStep {
  cwd: string;
  args: string[];
  label: string;
  packages: PackageInfo[];
}

/**
 * Build the `npm install` invocations for the packages cleared to upgrade. Pure apart from reading workspace manifests, so the selftest can assert what WOULD run.
 *
 * Every spec pins the exact `latest` this run judged (`name@1.2.3`), never `name@latest`: the freshness window was checked against that version, and `@latest` would install whatever the registry says at install time, which can be a version published after the check. The input is only ever `mustUpgrade`, which categorizePackages never lets a held major into.
 *
 * Root packages found in child package.json files install per workspace (`-w=packages/<ws>`) so they do not pollute the others; packages only the root declares install without `-w`, so child manifests are not rewritten.
 */
function planInstalls(
  root: string,
  rootPackages: PackageInfo[],
  privateGroups: Array<{ dir: string; name: string; packages: PackageInfo[] }>
): InstallStep[] {
  const steps: InstallStep[] = [];
  const spec = (p: PackageInfo) => `${p.name}@${p.latest}`;

  const byWorkspace = new Map<string, PackageInfo[]>();
  const rootOnly: PackageInfo[] = [];
  for (const pkg of rootPackages) {
    const workspaces = findWorkspacesWithPackage(pkg.name, root);
    if (workspaces.length === 0) {
      rootOnly.push(pkg);
      continue;
    }
    for (const ws of workspaces) {
      const existing = byWorkspace.get(ws) ?? [];
      existing.push(pkg);
      byWorkspace.set(ws, existing);
    }
  }
  for (const [ws, pkgs] of byWorkspace) {
    steps.push({
      cwd: root,
      args: ['install', `-w=packages/${ws}`, ...pkgs.map(spec)],
      label: `packages/${ws}`,
      packages: pkgs,
    });
  }
  if (rootOnly.length > 0) {
    steps.push({
      cwd: root,
      args: ['install', ...rootOnly.map(spec)],
      label: 'root',
      packages: rootOnly,
    });
  }
  for (const { dir, name, packages } of privateGroups) {
    if (packages.length === 0) continue;
    steps.push({ cwd: dir, args: ['install', ...packages.map(spec)], label: name, packages });
  }
  return steps;
}

/** Run the planned installs, printing what each one takes. */
function executeInstalls(steps: InstallStep[]): boolean {
  if (steps.length === 0) {
    console.log(`${GREEN}No packages to upgrade${NC}`);
    return true;
  }
  let success = true;
  for (const step of steps) {
    console.log(`${BLUE}Upgrading ${step.packages.length} package(s) in ${step.label}...${NC}\n`);
    for (const pkg of step.packages) printPackage(pkg);
    console.log();
    const result = spawnSync('npm', step.args, { cwd: step.cwd, stdio: 'inherit', shell: true });
    if (result.status !== 0) success = false;
  }
  console.log(success ? `\n${GREEN}Upgrades completed${NC}` : `\n${RED}Some upgrades failed${NC}`);
  return success;
}

/**
 * Show help message
 */
function showHelpMessage(): void {
  console.log(`
${BLUE}check-deps.ts${NC} - Dependency version enforcement

${YELLOW}USAGE${NC}
  npx tsx scripts/gates/check-deps.ts [OPTIONS]

${YELLOW}OPTIONS${NC}
  --upgrade, -u   Upgrade every outdated package that is not blocked and not breaking
  --help, -h      Show this help message

${YELLOW}DESCRIPTION${NC}
  Checks for outdated npm dependencies in the console root and in the private/
  submodule manifests, and fails if any are found.
  Packages can be blocklisted in .ci/policy/.deps-upgrade-blocklist to hold them.
  A breaking upgrade (new major, or new minor on 0.x) is never applied by
  --upgrade unless ${MAJOR_ALLOW_REL} names it with a reason.

${YELLOW}BLOCKLIST FORMAT${NC}
  package-name  # BLOCKER: reason for blocking

${YELLOW}EXAMPLES${NC}
  npx tsx scripts/gates/check-deps.ts           # Check for outdated packages
  npx tsx scripts/gates/check-deps.ts --upgrade # Upgrade non-breaking outdated packages
  npm run check:deps                      # Via npm script
  npm run check:deps -- --upgrade         # Upgrade via npm script
  ./go quality deps                       # Via go script
`);
}

interface ManifestGroup {
  dir: string;
  /** '' for the root. */
  name: string;
  mustUpgrade: PackageInfo[];
  heldMajor: PackageInfo[];
  blocked: PackageInfo[];
  tooNew: PackageInfo[];
}

const where = (name: string) => (name ? ` (${name})` : '');

/**
 * Main check function
 */
async function checkDependencies(): Promise<void> {
  if (showHelp) {
    showHelpMessage();
    process.exit(0);
  }

  console.log('Checking dependency versions...\n');

  const blocklist = loadBlocklist();
  const allow = loadMajorAllow();

  const scan = getPrivatePackageDirs();
  if (scan.uninitialized.length > 0) {
    const list = scan.uninitialized.join(', ');
    if (process.env.GITHUB_ACTIONS === 'true') {
      console.error(
        `${RED}✗${NC} declared submodule(s) not checked out: ${list}. The quality-content job checks submodules out, ` +
          'so an empty one here means the checkout failed and this gate would judge less than it claims.'
      );
      process.exit(1);
    }
    console.log(`${YELLOW}Not checked out, so not judged here (CI judges them): ${list}${NC}\n`);
  }

  const manifests: ManifestResult[] = [probeManifest(CONSOLE_ROOT, false)];
  for (const dir of scan.dirs) manifests.push(probeManifest(dir, true));

  // Unknown is unchecked. Refused before anything is categorised or installed.
  const unknown = manifests.flatMap((m) => m.unknown.map((n) => `${n}${where(m.name)}`));
  if (unknown.length > 0) {
    console.error(
      `${RED}✗${NC} ${unknown.length} package(s) have no installed or locked version, so they cannot be judged:`
    );
    for (const u of unknown) console.error(`  ${u}`);
    console.error(
      '  Each is declared but absent from package-lock.json and node_modules. Regenerate the lockfile in that\n' +
        '  directory (npx -y npm@<NPM_VERSION> install --package-lock-only --ignore-scripts), then re-run.'
    );
    process.exit(1);
  }

  const minReleaseAgeMs = getMinReleaseAgeMs(RELEASE_AGE_FILE);
  const nowMs = Date.now();
  const groups: ManifestGroup[] = [];
  const allowUsed = new Set<string>();
  let judged = 0;
  for (const m of manifests) {
    judged += Object.keys(m.entries).length;
    const cat = categorizePackages(m.entries, blocklist, m.name || undefined, allow);
    for (const k of cat.allowUsed) allowUsed.add(k);
    // Defer versions still inside the freshness window (aged < 24h, rounded up to the next UTC day): too fresh to be a real "must upgrade" or a real decision. This auto-resolves as a daily batch once the version ages out.
    const must = await partitionByReleaseAge(cat.mustUpgrade, minReleaseAgeMs, nowMs);
    const held = await partitionByReleaseAge(cat.heldMajor, minReleaseAgeMs, nowMs);
    groups.push({
      dir: m.dir,
      name: m.name,
      mustUpgrade: must.installable,
      heldMajor: held.installable,
      blocked: cat.blocked,
      tooNew: [...must.tooNew, ...held.tooNew],
    });
  }

  // Allow-list liveness, in-gate: an entry that authorised nothing in this run is either a major that has already landed or one that never matched. Either way it would silently authorise the NEXT surprise if left, so it fails in both modes, before anything is installed.
  const dead = allow.filter((a) => !allowUsed.has(a.key));
  if (dead.length > 0) {
    console.error(
      `${RED}✗${NC} ${dead.length} entry(ies) in ${MAJOR_ALLOW_REL} authorise nothing in this run:`
    );
    for (const a of dead) {
      console.error(
        `  "${a.key}": no scanned manifest${a.scope ? ` at ${a.scope}` : ''} has ${a.name} outdated with a ${a.line}.x latest ` +
          'outside its current range (or a blocklist line holds it). Delete the entry.'
      );
    }
    process.exit(1);
  }

  const sum = (pick: (g: ManifestGroup) => PackageInfo[]) =>
    groups.reduce((s, g) => s + pick(g).length, 0);
  const totalMust = sum((g) => g.mustUpgrade);
  const totalHeld = sum((g) => g.heldMajor);
  const totalBlocked = sum((g) => g.blocked);
  const totalTooNew = sum((g) => g.tooNew);
  const shape =
    `judged ${judged} package(s) across ${manifests.length} manifest(s) ` +
    `(${manifests.map((m) => m.name || 'root').join(', ')})`;

  const deferredSummary = (): string => {
    const parts: string[] = [];
    if (totalBlocked > 0) parts.push(`${totalBlocked} blocked`);
    if (totalTooNew > 0) parts.push(`${totalTooNew} too new`);
    return parts.length > 0 ? ` (${parts.join(', ')})` : '';
  };

  const printHeld = (changelogUrls?: Map<string, string | null>) => {
    if (totalHeld === 0) return;
    console.log(
      `${RED}Major upgrades awaiting a decision (${totalHeld}); --upgrade never applies these:${NC}\n`
    );
    for (const g of groups) {
      for (const pkg of g.heldMajor) {
        printPackage(pkg, { suffix: where(g.name), changelogUrls });
        console.log(
          `    Take it:  add "${suggestedAllowKey(pkg, g.name || undefined)}": "<why now>" to ${MAJOR_ALLOW_REL}`
        );
      }
    }
    console.log(
      `\n  Or hold it: add a '<package>  # BLOCKER: <reason>' line to .ci/policy/.deps-upgrade-blocklist.\n`
    );
  };

  if (upgradeMode) {
    const rootGroup = groups[0];
    const steps = planInstalls(
      CONSOLE_ROOT,
      rootGroup.mustUpgrade,
      groups.slice(1).map((g) => ({ dir: g.dir, name: g.name, packages: g.mustUpgrade }))
    );
    if (steps.length === 0 && totalHeld === 0) {
      console.log(`${GREEN}All dependencies are up-to-date${NC}${deferredSummary()}; ${shape}`);
      for (const g of groups) {
        for (const pkg of g.blocked)
          printPackage(pkg, { suffix: ` (blocked${g.name ? `, ${g.name}` : ''})` });
        for (const pkg of g.tooNew)
          printPackage(pkg, {
            suffix: ` (too new, deferred until next UTC day${g.name ? `, ${g.name}` : ''})`,
          });
      }
      process.exit(0);
    }
    const success = executeInstalls(steps);
    printHeld();
    if (totalHeld > 0) {
      console.log(
        `${RED}${totalHeld} major upgrade(s) held; check:deps stays red until each is taken or blocklisted.${NC}`
      );
      process.exit(1);
    }
    process.exit(success ? 0 : 1);
  }

  // Check mode - fetch changelog URLs for all packages that will be displayed (never for a fixture root).
  const allPackages = groups.flatMap((g) => [
    ...g.mustUpgrade,
    ...g.heldMajor,
    ...g.blocked,
    ...g.tooNew,
  ]);
  const changelogUrls = FIXTURE_ROOT
    ? new Map<string, string | null>()
    : await fetchChangelogUrls(allPackages);

  const hasFailure = totalMust > 0 || totalHeld > 0;

  for (const g of groups) {
    const header = g.name
      ? `${RED}Outdated packages in ${g.name} (must upgrade):${NC}`
      : `${RED}Outdated packages (must upgrade):${NC}`;
    printPackageGroup(header, g.mustUpgrade, { changelogUrls });
  }
  if (totalMust > 0) {
    console.log(`Run: npm run check:deps -- --upgrade`);
    console.log(`Or:  npx tsx scripts/gates/check-deps.ts --upgrade`);
    console.log();
  }
  printHeld(changelogUrls);

  // Too-new packages are informational, never a failure: they are still within the freshness window (deferred until the next UTC day after aging 24h) and surface as a batch once eligible.
  if (totalTooNew > 0) {
    console.log(
      `${YELLOW}Too new, within freshness window, deferred until next UTC day (${totalTooNew}):${NC}`
    );
    console.log();
    for (const g of groups) {
      for (const pkg of g.tooNew) printPackage(pkg, { suffix: where(g.name), changelogUrls });
    }
    console.log();
  }

  if (totalBlocked > 0) {
    console.log(`${YELLOW}Blocked packages (${totalBlocked}):${NC}`);
    console.log();
    for (const g of groups) {
      for (const pkg of g.blocked) printPackage(pkg, { suffix: where(g.name), changelogUrls });
    }
    console.log();
  }

  if (hasFailure) {
    console.log(
      `${RED}Dependency check FAILED${NC}: ${totalMust} must upgrade, ${totalHeld} major(s) awaiting a decision; ${shape}`
    );
    process.exit(1);
  }

  console.log(`${GREEN}All dependencies are up-to-date${NC}${deferredSummary()}; ${shape}`);
  process.exit(0);
}

// ---------------------------------------------------------------------------
// Selftest
// ---------------------------------------------------------------------------

interface FixtureSpec {
  /** Canned `npm outdated --json` per manifest, keyed '' for the root or 'private/account/web'. */
  outdated: Record<string, RawOutdated>;
  /** Lockfile `packages` maps per manifest, same keys. */
  locks: Record<string, Record<string, { version: string }>>;
  allow?: Record<string, string>;
  blocklist?: string;
}

/**
 * A synthetic console tree the real script can be run against: a .gitmodules declaring private/account, a checked-out marker for it, the manifests and lockfiles in `spec`, a local-only private/growth that is NOT a submodule, a zero release-age window (so nothing reaches the network), and a stub `npm` on PATH that serves the canned `outdated` JSON and records every `install` instead of running it.
 */
function buildFixture(spec: FixtureSpec): { root: string; log: string; env: NodeJS.ProcessEnv } {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'check-deps-fixture-'));
  const write = (rel: string, text: string) => {
    const p = path.join(root, rel);
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, text);
  };
  write(
    '.gitmodules',
    '[submodule "private/account"]\n\tpath = private/account\n\turl = https://example.invalid/account.git\n'
  );
  write('private/account/.git', 'gitdir: ../../.git/modules/private/account\n');
  write('.ci/config/release-age.json', '{"minimum_release_age_minutes": 0}\n');
  write('.ci/config/deps-major-allow.json', JSON.stringify({ allow: spec.allow ?? {} }));
  write(
    path.relative(root, policyPath('.deps-upgrade-blocklist', root)),
    spec.blocklist ?? '# fixture blocklist\n'
  );
  // Local-only, NOT a submodule: must never be scanned, and its canned report would be a must-upgrade if it were.
  write('private/growth/package.json', '{}');
  write(
    'private/growth/.fixture-outdated.json',
    JSON.stringify({ leftpad: { current: '1.0.0', latest: '1.0.1' } })
  );
  for (const rel of new Set(['', ...Object.keys(spec.outdated), ...Object.keys(spec.locks)])) {
    write(path.join(rel, 'package.json'), '{}');
    write(path.join(rel, '.fixture-outdated.json'), JSON.stringify(spec.outdated[rel] ?? {}));
    if (spec.locks[rel])
      write(path.join(rel, 'package-lock.json'), JSON.stringify({ packages: spec.locks[rel] }));
  }
  const log = path.join(root, 'npm-install.log');
  write(
    'bin/npm',
    [
      '#!/bin/sh',
      'case "$1" in',
      '  outdated) if [ -f .fixture-outdated.json ]; then cat .fixture-outdated.json; else echo "{}"; fi; exit 1 ;;',
      `  install) echo "$(pwd) :: $*" >> "${log}"; exit 0 ;;`,
      '  *) echo "fixture npm stub: unexpected: $*" >&2; exit 2 ;;',
      'esac',
      '',
    ].join('\n')
  );
  fs.chmodSync(path.join(root, 'bin', 'npm'), 0o755);
  fs.writeFileSync(log, '');
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    CHECK_DEPS_ROOT: root,
    PATH: `${path.join(root, 'bin')}${path.delimiter}${process.env.PATH ?? ''}`,
  };
  delete env.CHECK_DEPS_FORCE_PROBE_FAILURE;
  return { root, log, env };
}

function runFixture(
  spec: FixtureSpec,
  mode: 'check' | 'upgrade'
): { status: number | null; output: string; installs: string[]; root: string } {
  const fx = buildFixture(spec);
  try {
    const child = spawnSync(
      process.execPath,
      [...process.execArgv, process.argv[1], ...(mode === 'upgrade' ? ['--upgrade'] : [])],
      { cwd: fx.root, encoding: 'utf-8', env: fx.env }
    );
    const installs = fs
      .readFileSync(fx.log, 'utf-8')
      .split('\n')
      .filter(Boolean)
      .map((l) => l.replace(fx.root, '<root>'));
    return {
      status: child.status,
      output: `${child.stdout ?? ''}${child.stderr ?? ''}`,
      installs,
      root: fx.root,
    };
  } finally {
    fs.rmSync(fx.root, { recursive: true, force: true });
  }
}

/**
 * Controls: prove this gate can still FAIL, and that its --upgrade path holds a breaking bump in EVERY manifest while still applying the safe ones. Run by `--selftest`.
 */
function selftest(): void {
  let checks = 0;
  const fail = (what: string, detail = ''): never => {
    console.error(`${RED}✗${NC} selftest control failed: ${what}${detail ? `\n${detail}` : ''}`);
    process.exit(1);
  };
  const expect = (what: string, ok: boolean, detail = '') => {
    checks++;
    if (!ok) fail(what, detail);
  };

  // 1. PROBE FAIL-CLOSED. Two shapes, because they failed open for two different reasons and only the second one ever shipped. Each must make the gate exit non-zero WITH its own message, so a gate that merely dies for an unrelated reason cannot pass here.
  //
  // process.execArgv carries tsx's own loader flags (--require preflight.cjs, --import loader.mjs). Without them the child is a bare node that cannot resolve this file's .js-suffixed TS imports, and the control would "fire" on a module-resolution error instead of on the thing it is testing.
  const probeCases = [
    { mode: '1', want: 'did not run', label: 'a probe that produced no output' },
    {
      mode: 'error-json',
      want: 'could not reach the registry',
      label: "npm's error-shaped report",
    },
  ];
  for (const { mode, want, label } of probeCases) {
    const child = spawnSync(process.execPath, [...process.execArgv, process.argv[1]], {
      cwd: CONSOLE_ROOT,
      encoding: 'utf-8',
      env: { ...process.env, CHECK_DEPS_FORCE_PROBE_FAILURE: mode },
    });
    const output = `${child.stdout ?? ''}${child.stderr ?? ''}`;
    expect(
      `${label}: the gate must exit non-zero (the fail-open runNpmOutdated exists to prevent)`,
      child.status !== 0
    );
    expect(
      `${label}: the failure must carry "${want}", or it may be incidental`,
      output.includes(want),
      output
    );
    expect(
      `${label}: no up-to-date claim while failing`,
      !output.includes('All dependencies are up-to-date'),
      output
    );
  }

  // 2. BREAKING-BUMP CLASSIFICATION. lucide-react's 0.575 -> 1.48 is the case that shipped; 0.x minors are breaking under caret semantics; an unparseable version is held rather than guessed.
  const bumps: [string, string, boolean][] = [
    ['0.575.0', '1.48.0', true],
    ['6.4.2', '8.0.1', true],
    ['4.7.0', '6.0.1', true],
    ['0.3.270', '0.4.0', true],
    ['0.3.270', '0.3.283', false],
    ['7.88.0', '7.89.0', false],
    ['1.0.0-beta.3', '1.0.0', false],
    ['git', '2.0.0', true],
  ];
  for (const [c, l, want] of bumps) {
    expect(`isBreakingBump(${c}, ${l}) === ${want}`, isBreakingBump(c, l) === want);
  }

  // 3. ONE RULE IN EVERY MANIFEST, on the pure categoriser. The fixture mirrors 2026-09-26: majors in private/account/web beside a minor.
  const webOutdated: Record<string, OutdatedPackageInfo> = {
    vite: { current: '6.4.2', latest: '8.0.1' },
    'lucide-react': { current: '0.575.0', latest: '1.48.0' },
    'react-hook-form': { current: '7.88.0', latest: '7.89.0' },
  };
  const noBlock = new Map<string, BlocklistEntry>();
  const webScope = 'private/account/web';
  const plain = categorizePackages(webOutdated, noBlock, webScope, []);
  const names = (l: PackageInfo[]) =>
    l
      .map((p) => p.name)
      .sort()
      .join(',');
  expect(
    'a sub-manifest major is HELD, not must-upgrade',
    names(plain.heldMajor) === 'lucide-react,vite',
    names(plain.heldMajor)
  );
  expect(
    'the sub-manifest minor is must-upgrade',
    names(plain.mustUpgrade) === 'react-hook-form',
    names(plain.mustUpgrade)
  );
  const atRootToo = categorizePackages(webOutdated, noBlock, undefined, []);
  expect(
    'the SAME rule at the root: majors held there as well',
    names(atRootToo.heldMajor) === 'lucide-react,vite'
  );
  const allowVite: MajorAllowEntry = {
    key: `${webScope}:vite@8`,
    scope: webScope,
    name: 'vite',
    line: '8',
    reason: 'x',
  };
  const allowed = categorizePackages(webOutdated, noBlock, webScope, [allowVite]);
  expect(
    'a scoped allow entry clears exactly its own major',
    names(allowed.mustUpgrade) === 'react-hook-form,vite' && allowed.allowUsed.has(allowVite.key)
  );
  expect(
    'CONTROL: a scoped allow entry does not reach another manifest',
    names(categorizePackages(webOutdated, noBlock, 'private/account', [allowVite]).heldMajor) ===
      'lucide-react,vite'
  );
  const allowVite7: MajorAllowEntry = { ...allowVite, key: 'vite@7', scope: null, line: '7' };
  expect(
    'CONTROL: an allow entry for another line does not clear this major',
    names(categorizePackages(webOutdated, noBlock, webScope, [allowVite7]).heldMajor) ===
      'lucide-react,vite'
  );
  const blockVite = new Map<string, BlocklistEntry>([['vite', { reason: 'BLOCKER: fixture' }]]);
  const both = categorizePackages(webOutdated, blockVite, webScope, [allowVite]);
  expect(
    'a blocklist line wins over an allow entry, which then counts as unused',
    both.blocked.some((p) => p.name === 'vite') && !both.allowUsed.has(allowVite.key)
  );

  // 4. SCOPED BLOCKLIST ENTRIES, both directions. The whole reason `<dir>:<pkg>` exists is that a BARE entry for a package private/account shares with console would stop this gate reporting it for CONSOLE too.
  const probe = new Map<string, BlocklistEntry>([
    ['private/account:typescript', { reason: 'BLOCKER: scoped fixture' }],
    ['glob', { reason: 'BLOCKER: bare fixture' }],
  ]);
  const outdatedFixture: Record<string, OutdatedPackageInfo> = {
    typescript: { current: '6.0.3', latest: '7.0.2', wanted: '7.0.2' },
    glob: { current: '11.1.0', latest: '13.0.6', wanted: '13.0.6' },
  };
  const atRoot = categorizePackages(outdatedFixture, probe);
  const inAccount = categorizePackages(outdatedFixture, probe, 'private/account');
  expect(
    'a scoped entry blocks inside its own directory',
    inAccount.blocked.some((p) => p.name === 'typescript')
  );
  expect(
    'CONTROL: the SAME package is still reported at the root (held as a major, not blocked)',
    atRoot.heldMajor.some((p) => p.name === 'typescript') &&
      !atRoot.blocked.some((p) => p.name === 'typescript')
  );
  expect(
    'CONTROL: a bare entry still blocks everywhere, root included',
    atRoot.blocked.some((p) => p.name === 'glob') &&
      inAccount.blocked.some((p) => p.name === 'glob')
  );
  expect(
    'CONTROL: a scope that matches nothing blocks nothing extra',
    categorizePackages(outdatedFixture, probe, 'private/elite').blocked.length === 1
  );

  // 5. NORMALISATION: the two shapes that used to vanish silently.
  const norm = normalizeOutdated(
    {
      tsx: [
        { current: '4.22.1', latest: '4.23.15', dependent: 'cli', location: '/r/node_modules/tsx' },
        {
          current: '4.22.1',
          latest: '4.23.15',
          dependent: 'console',
          location: '/r/node_modules/tsx',
        },
      ],
      vite: { wanted: '6.4.2', latest: '8.0.1' },
      ghost: { latest: '1.0.0' },
    },
    '/r',
    { 'node_modules/vite': { version: '6.4.2' } }
  );
  expect(
    'an ARRAY entry (several workspaces) is judged, not dropped',
    norm.entries.tsx?.current === '4.22.1'
  );
  expect(
    'an entry with no `current` (CI, no node_modules) takes it from the lockfile',
    norm.entries.vite?.current === '6.4.2'
  );
  expect(
    'an entry neither source can place is reported unknown',
    norm.unknown.join(',') === 'ghost'
  );

  // 6. ALLOW FILE PARSING.
  const pa = parseMajorAllow(
    JSON.stringify({
      allow: {
        'private/account/web:vite@8': 'r',
        '@vitejs/plugin-react@6': 'r',
        'lucide-react@1': 'r',
        'bad key': 'r',
        'x@0.4': 'r',
      },
    })
  );
  expect(
    'allow keys parse (scoped, npm-scoped, 0.x line) and a malformed key is refused',
    pa.entries.length === 4 &&
      pa.problems.length === 1 &&
      pa.entries.some(
        (e) => e.name === '@vitejs/plugin-react' && e.line === '6' && e.scope === null
      ) &&
      pa.entries.some((e) => e.scope === webScope && e.name === 'vite'),
    JSON.stringify(pa)
  );
  expect(
    'an allow file without an "allow" object is refused',
    parseMajorAllow('{}').problems.length === 1
  );

  // 7. SCAN SET = WHAT CI CHECKS OUT. Driven on a synthetic tree, not the real checkout.
  const scanRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'check-deps-scan-'));
  try {
    const w = (rel: string, t: string) => {
      fs.mkdirSync(path.dirname(path.join(scanRoot, rel)), { recursive: true });
      fs.writeFileSync(path.join(scanRoot, rel), t);
    };
    w(
      '.gitmodules',
      '[submodule "private/account"]\n\tpath = private/account\n[submodule "private/renet"]\n\tpath = private/renet\n[submodule "private/elite"]\n\tpath = private/elite\n'
    );
    for (const rel of ['account', 'account/web', 'account/e2e', 'renet', 'growth'])
      w(`private/${rel}/package.json`, '{}');
    w('private/account/.git', 'gitdir: x\n');
    w('private/renet/.git', 'gitdir: x\n');
    const got = getPrivatePackageDirs(scanRoot);
    const found = got.dirs.map((d) => path.relative(path.join(scanRoot, 'private'), d));
    expect('top-level private/account is found', found.includes('account'));
    expect(
      'nested private/account/web and private/account/e2e are found',
      found.includes('account/web') && found.includes('account/e2e')
    );
    expect('a checked-out submodule with a manifest (renet) is found', found.includes('renet'));
    expect(
      'a local-only directory that is NOT a submodule (growth) is never scanned',
      !found.includes('growth'),
      found.join(',')
    );
    expect(
      'a declared but unchecked-out submodule (elite) is reported, not silently skipped',
      got.uninitialized.join(',') === 'private/elite'
    );
    fs.rmSync(path.join(scanRoot, 'private', 'account', '.git'));
    const absent = getPrivatePackageDirs(scanRoot);
    expect(
      'an uninitialised private/account reports none of its nested dirs',
      !absent.dirs.some((d) => d.includes(`${path.sep}account`)) &&
        absent.uninitialized.includes('private/account')
    );
  } finally {
    fs.rmSync(scanRoot, { recursive: true, force: true });
  }

  // 8. END TO END, the real script on a fixture tree with a recording npm stub. The web manifest is CI-shaped: `npm outdated` gives NO `current`, only the lockfile knows it. This is the control for the 2026-09-26 incident: the major must be reported and NOT installed, the minor beside it must be installed.
  const webLock = {
    'node_modules/vite': { version: '6.4.2' },
    'node_modules/lucide-react': { version: '0.575.0' },
    'node_modules/react-hook-form': { version: '7.88.0' },
    'node_modules/clsx': { version: '2.1.1' },
  };
  const incident: FixtureSpec = {
    outdated: {
      '': {
        tsx: [
          { current: '4.22.1', latest: '4.23.15', dependent: 'cli' },
          { current: '4.22.1', latest: '4.23.15', dependent: 'console' },
        ],
      },
      'private/account': {},
      'private/account/web': {
        vite: { wanted: '6.4.2', latest: '8.0.1' },
        'lucide-react': { wanted: '0.575.0', latest: '1.48.0' },
        'react-hook-form': { wanted: '7.89.0', latest: '7.89.0' },
        clsx: { wanted: '2.1.1', latest: '2.1.1' },
      },
    },
    locks: { '': {}, 'private/account': {}, 'private/account/web': webLock },
  };
  const up = runFixture(incident, 'upgrade');
  const inst = up.installs.join('\n');
  const detail = `installs:\n${inst}\noutput:\n${up.output}`;
  expect(
    'e2e --upgrade: the sub-manifest minor IS applied',
    /<root>\/private\/account\/web :: install .*react-hook-form@7\.89\.0/.test(inst),
    detail
  );
  expect(
    'e2e --upgrade: the sub-manifest majors are NOT applied',
    !/vite@|lucide-react@/.test(inst),
    detail
  );
  expect(
    'e2e --upgrade: the majors are reported as awaiting a decision',
    up.output.includes('awaiting a decision') &&
      up.output.includes('vite: 6.4.2 -> 8.0.1 (major) (private/account/web)'),
    detail
  );
  expect(
    'e2e --upgrade: the root array-shaped minor is applied',
    inst.includes('<root> :: install tsx@4.23.15'),
    detail
  );
  expect(
    'e2e --upgrade: nothing is installed in the local-only private/growth',
    !inst.includes('growth'),
    detail
  );
  expect('e2e --upgrade: exits non-zero while a major is undecided', up.status === 1, detail);

  const reason = 'vite 8 is taken with the plugin-react 6 migration in the same change';
  const taken = runFixture(
    { ...incident, allow: { 'private/account/web:vite@8': reason } },
    'upgrade'
  );
  const takenInst = taken.installs.join('\n');
  expect(
    'e2e --upgrade: an allow-listed major IS applied, at the exact version judged',
    /private\/account\/web :: install .*vite@8\.0\.1/.test(takenInst) &&
      takenInst.includes('react-hook-form@7.89.0'),
    `${takenInst}\n${taken.output}`
  );
  expect(
    'e2e --upgrade: CONTROL: the other major is still held',
    !takenInst.includes('lucide-react@'),
    takenInst
  );

  const chk = runFixture(incident, 'check');
  expect(
    'e2e check: fails, names the held majors and prints the shape',
    chk.status === 1 &&
      chk.output.includes('awaiting a decision') &&
      chk.output.includes('across 3 manifest(s) (root, private/account, private/account/web)'),
    chk.output
  );
  expect(
    'e2e check: judges the CI-shaped web manifest (4 there + 1 root)',
    chk.output.includes('judged 5 package(s)'),
    chk.output
  );

  const deadAllow = runFixture({ ...incident, allow: { 'left-pad@2': reason } }, 'check');
  expect(
    'e2e check: an allow entry that authorises nothing fails the gate',
    deadAllow.status === 1 && deadAllow.output.includes('authorise nothing'),
    deadAllow.output
  );

  const unknownCase = runFixture(
    {
      ...incident,
      outdated: {
        ...incident.outdated,
        'private/account/web': { ghost: { wanted: '1.0.0', latest: '1.0.0' } },
      },
    },
    'check'
  );
  expect(
    'e2e check: a version neither npm nor the lockfile knows fails as unchecked',
    unknownCase.status === 1 && unknownCase.output.includes('ghost (private/account/web)'),
    unknownCase.output
  );

  const clean = runFixture(
    {
      outdated: {
        '': {},
        'private/account': {},
        'private/account/web': { clsx: { wanted: '2.1.1', latest: '2.1.1' } },
      },
      locks: { '': {}, 'private/account': {}, 'private/account/web': webLock },
    },
    'check'
  );
  expect(
    'e2e check: CONTROL: a tree with nothing outdated passes',
    clean.status === 0 &&
      clean.output.includes('All dependencies are up-to-date') &&
      clean.output.includes('judged 1 package(s) across 3 manifest(s)'),
    clean.output
  );

  console.log(
    joinReport(
      `${GREEN}✓${NC} ${checks} selftest checks: the probe fails closed on both shapes; a breaking bump is held in `,
      'every manifest and applied only when allow-listed, while a minor beside it is applied (end to end, CI-shaped ',
      'lockfile input); array and lockfile-only reports are judged, not dropped; dead allow entries and unknown ',
      'versions fail; the scan set is exactly the checked-out submodules'
    )
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
          '  If the registry is unreachable, fix that and re-run; do not treat this as a pass.'
      );
      process.exit(1);
    }
    throw error;
  });
}
