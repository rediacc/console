#!/usr/bin/env node
/**
 * Check that all dependencies are up-to-date.
 *
 * This script runs `npm outdated` in the console root, in the four workers/ manifests and in every private/ manifest CI also checks out, and fails if any dependency is outdated, unless it is in the blocklist (packages that should NOT be upgraded) or still inside the release-age freshness window.
 *
 * Blocklist format (.ci/policy/.deps-upgrade-blocklist):
 *   package-name  # BLOCKER: reason for blocking
 *
 * BREAKING UPGRADES ARE NEVER APPLIED BY DEFAULT. A version outside the current caret range (a new major, or a new minor on a 0.x line) is reported as a major awaiting a decision, and the pins command (`npm run pins -- bump npm`) does not install it anywhere, in the root, a workers/ manifest or a private/ manifest, unless `bump npm --to <package>@<line> --major --reason "<why now>"` names it. Before 2026-09-26 no such rule existed: the root looked safe only because every outdated root major happened to carry its own blocklist line, and the old `--upgrade` took lucide-react 0 -> 1, @vitejs/plugin-react 4 -> 6 and vite 6 -> 8 in private/account/web because nothing there did.
 *
 * WHAT IS SCANNED, AND WHY LOCAL AND CI NOW AGREE. The private/ manifests scanned are the ones inside a git SUBMODULE declared in .gitmodules (plus the nested manifests in NESTED_PRIVATE_PACKAGE_DIRS), which is exactly the set the quality-content job checks out with `submodules: true`. A gitignored local-only directory such as private/growth is never scanned, because a verdict CI never reaches is not a gate. And every `current` version is read from the manifest's committed package-lock.json, because CI installs no node_modules under private/ and `npm outdated` then reports NO `current` at all: until 2026-09-26 the gate dropped every such entry as "nothing to judge", so CI's private scan examined all of private/account and judged none of it, while a developer's installed node_modules made the same scan judge real packages locally. Without node_modules `npm outdated` also OMITS every devDependency, optionalDependency and peerDependency outright (it reads the installed tree whatever flag it is given), so until 2026-10-01 CI never judged private/account's dev tooling at all and a fresh clone advised deleting valid held-major exceptions; those are now judged from the lockfile and the registry (see blindEdges), and an uninstalled root refuses the run.
 *
 * A BLOCKLIST LINE HOLDS A MAJOR FOR 90 DAYS, NOT FOREVER (operator ruling 2026-10-01). A blocklisted breaking bump is aged from the first stable, non-deprecated release of the first line past `current` (not from `latest`, whose line restarts at every new major). At 60 days it warns; at 90 it fails unless .ci/policy/deps-major-exceptions.json excuses it with an owner, a reason and exactly one of a mechanical blocker re-checked against the registry on every run (peer-range, engine-floor) or an expiry at most 30 days out. An exception that has expired, whose blocker has lifted, or that excuses nothing fails the gate. Before this, a blocklist line excused a major with no time limit, the oldest for 477 days.
 *
 * Usage:
 *   npx tsx scripts/gates/check-deps.ts           # Check for outdated packages
 *   npm run pins -- bump npm                      # Upgrade every non-blocked, non-breaking package
 *   npx tsx scripts/gates/check-deps.ts --help    # Show help
 *
 * Exit codes:
 *   0 - All dependencies are up-to-date (or blocked, or too new)
 *   1 - Outdated dependencies found (check mode), a major awaits a decision, a blocklisted major is past 90 days and unexcused (or cannot be dated), a held-major exception is invalid, expired, stale or dead, a version could not be determined, or an allow entry is dead
 *
 * ASKS THE NPM REGISTRY (`npm outdated`, and registry.npmjs.org for the
 * packuments of uninstalled edges), so it is an external gate: the
 * `no-external-quality` label on a pull request holds it (`when:` below) and
 * quality-content's announcer names it. It is hard on every cadence; a registry
 * that does not answer is a DepsProbeError, red.
 *
 * ---- gate ----
 * step: External dependency freshness
 * needs: node
 * id: check:deps
 * selftest: true
 * lane: quality-content
 * slow: true
 * when: inputs.external_quality != 'skip'
 * ---- end gate ----
 */

import { exec, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import https from 'node:https';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import { WK_GH_ORIGIN } from '../../packages/shared/src/config/well-known.generated.js';
import {
  parseBlockeredList,
  validateBlockerQuality,
  verifyAllBlockers,
} from '../lib/blocker-validator.js';
import { BLUE, GREEN, joinReport, NC, RED, YELLOW } from '../lib/console.js';
import { pinningHolders, updateMismatches, verifyUpdatedVersions } from '../lib/deps/execute.js';
import { planPinSync } from '../lib/deps/pin-sync.js';
import {
  freshnessCutoffMs,
  type InstallStep,
  planInstalls,
  satisfiesRange,
} from '../lib/deps/plan.js';
import {
  CONSOLE_ROOT,
  compareVersions,
  DAY_MS,
  FIXTURE_ROOT,
  isBreakingBump,
  type LockEntry,
  MAJOR_ALLOW_REL,
  MUTANT,
  type PackageInfo,
  parseRange,
  parseVersion,
  printPackage,
  rangeAdmits,
  rangeFloorMajor,
  readLockPackages,
  releaseLine,
  utcDay,
} from '../lib/deps/shared.js';
import { policyPath } from '../lib/policy-paths.js';
import { getMinReleaseAgeMs, isWithinFreshnessWindow } from '../lib/release-age.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
/** The pinned npm the fixture trees declare in .devcontainer/toolchain.env. */
const FIXTURE_NPM_VERSION = '11.20.0';
const BLOCKLIST_FILE = policyPath('.deps-upgrade-blocklist', CONSOLE_ROOT);
const MAJOR_ALLOW_FILE = path.join(CONSOLE_ROOT, MAJOR_ALLOW_REL);
const RELEASE_AGE_FILE = path.join(CONSOLE_ROOT, '.ci', 'config', 'release-age.json');
const MAJOR_EXCEPTIONS_FILE = policyPath('deps-major-exceptions.json', CONSOLE_ROOT);
/** The blocklist as the fixture runs name it: repo-relative, from the one seam. */
const BLOCKLIST_REL = path.relative(CONSOLE_ROOT, BLOCKLIST_FILE).split(path.sep).join('/');
const MAJOR_EXCEPTIONS_REL = path
  .relative(CONSOLE_ROOT, MAJOR_EXCEPTIONS_FILE)
  .split(path.sep)
  .join('/');
// The selftest's mutant seam: `ignore-clock` skips the held-major clock, so the selftest can prove its 91-day control goes green WITHOUT the clock (i.e. the control depends on it); `split-update` restores the pre-2026-10-02 planner, one `npm update` per manifest instead of one per lockfile, so the selftest can prove its lockstep case goes red without the grouping; `update-first` restores the pre-2026-10-08 step order, every lockfile's `npm update` before its out-of-range `npm install` steps, so the selftest can prove its exact-pinned-sibling case goes red without the reorder; `skip-pin-sync` skips the .syncpackrc.json pinVersion rewrite after an upgrade (worklist #3b831146), so the selftest can prove its syncpack-style check finds the group left behind; `ambient-npm` makes the pins npm driver plan its commands for the ambient `npm` instead of `npx -y npm@<NPM_VERSION>`, so the selftest can prove its pinned-npm case goes red without the pin; `peer-split` restores the pre-2026-10-22 planner, an in-range sibling of an installing package waiting for the later `npm update`, so the selftest can prove its peer-family case goes red with ERESOLVE. Honoured only under CHECK_DEPS_ROOT; on a real tree it is refused loudly, so it can never weaken a real run.
const MUTANTS = [
  'ignore-clock',
  'split-update',
  'update-first',
  'skip-pin-sync',
  'ambient-npm',
  'peer-split',
];
/** A blocklisted major fails at this age, measured from the first release of the first line past `current`. */
const HOLD_DEADLINE_DAYS = 90;
/** ... and warns from this age. */
const HOLD_WARN_DAYS = 60;
/** An `expires` exception may reach at most this far ahead of the run judging it. */
const EXCEPTION_MAX_DAYS = 30;

// Parse command line arguments
const args = process.argv.slice(2);
const showHelp = args.includes('--help') || args.includes('-h');
/** `--plan-json`: print the read-only plan the pins npm driver consumes (scripts/lib/pins/drivers/npm.ts) as one `PLAN-JSON <json>` line and exit 0; nothing is installed or written, and the held-major clock is not judged. */
const planJson = args.includes('--plan-json');
/** `--allow <key>`: treat that allow entry as present for this plan only (the transient entry of a `--major` bump). */
const planAllow = args.flatMap((a, i) => (a === '--allow' ? [args[i + 1]] : []));
/** `--unblock <key>`: treat that blocklist line as absent for this plan only. */
const planUnblock = args.flatMap((a, i) => (a === '--unblock' ? [args[i + 1]] : []));

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

const execAsync = promisify(exec);

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
async function runNpmOutdated(
  cwd: string,
  extraArgs = ''
): Promise<Record<string, OutdatedPackageInfo>> {
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
    // Async so the four manifests' probes (each about a second or three of npm talking to the registry) overlap instead of queueing; the failure contract is unchanged, a rejected exec carries the same stdout and stderr as the thrown execSync did.
    stdout = (
      await execAsync(forced ? 'sh -c \'echo "simulated probe failure" >&2; exit 1\'' : command, {
        cwd,
        encoding: 'utf-8',
        maxBuffer: 64 * 1024 * 1024,
      })
    ).stdout;
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

/** The four Worker projects in the console tree, each with its own package.json and package-lock.json and none a workspace of the root, so the root's report never reaches them (until 2026-10-14 nothing judged their freshness). Judged from the lockfile and the registry like the private/ manifests. */
const WORKER_PACKAGE_DIRS = ['account', 'mta-sts', 'proxy', 'www'];

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
 * The non-root manifests this gate judges: the workers/ projects, then every declared private/ SUBMODULE that carries a package.json, plus the nested manifests listed above inside one. A directory under private/ that is not a submodule (private/growth and private/generative are gitignored local checkouts) is never scanned, because CI does not have it and a verdict CI never reaches is not a gate.
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
  for (const w of WORKER_PACKAGE_DIRS) {
    const wAbs = path.join(root, 'workers', w);
    if (fs.existsSync(path.join(wAbs, 'package.json'))) dirs.push(wAbs);
  }
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
  /** Root only: declared non-prod dependencies that are not installed, so npm never judged them. The caller refuses the run. */
  uninstalled: string[];
  /** Private only: uninstalled dependencies that neither the lockfile nor the registry could place. The caller refuses the run. */
  unjudgeable: string[];
  /** Private only: how many uninstalled dependencies were judged from the lockfile and the registry. */
  blindJudged: number;
}

/** The manifest sections `npm outdated` drops when the package is not on disk. Only `dependencies` survives a missing install. */
const NON_PROD_SECTIONS = ['devDependencies', 'optionalDependencies', 'peerDependencies'] as const;

/** The non-prod dependencies a manifest declares, by name, with their specs. Empty when the manifest is missing or unreadable. */
function readNonProdDeclared(dir: string): Array<{ name: string; spec: string }> {
  try {
    const pkg = JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf-8')) as Record<
      string,
      Record<string, string> | undefined
    >;
    const out = new Map<string, string>();
    for (const section of NON_PROD_SECTIONS) {
      for (const [name, spec] of Object.entries(pkg[section] ?? {})) {
        if (!out.has(name)) out.set(name, spec);
      }
    }
    return [...out].map(([name, spec]) => ({ name, spec }));
  } catch {
    return [];
  }
}

/** A spec npm resolves from the registry. npm skips the rest (`file:`, `link:`, `workspace:`, git, URLs, `user/repo`) in `outdated` whether or not they are installed, and so does this gate. An `npm:` alias IS a registry spec, under another name. */
function isRegistrySpec(spec: string): boolean {
  if (spec.startsWith('npm:')) return true;
  return !spec.includes(':') && !spec.includes('/');
}

/**
 * THE BLIND SPOT OF `npm outdated` (worklist #1feb4717). It loads the INSTALLED tree whatever flag it is given (npm 11.20.0, lib/commands/outdated.js calls `arb.loadActual()`; `--package-lock-only` changes nothing there), and it skips every devDependency, optionalDependency and peerDependency that is not on disk. With no node_modules a manifest's dev tooling therefore reads as current: on 2026-10-01 private/account/web reported `{}` for its typescript, the blocklisted hold vanished, and the gate printed "excuses nothing ... Delete the entry" for a valid exception.
 *
 * Returns the declared non-prod registry dependencies of `dir` that npm did not report and that are not installed under any of `nodeModulesRoots` (a package on disk was judged by npm, and its absence from the report means it is current).
 */
function blindEdges(
  dir: string,
  reported: Set<string>,
  nodeModulesRoots: string[]
): Array<{ name: string; spec: string }> {
  return readNonProdDeclared(dir).filter(
    ({ name, spec }) =>
      isRegistrySpec(spec) &&
      !reported.has(name) &&
      !nodeModulesRoots.some((r) =>
        fs.existsSync(path.join(r, 'node_modules', name, 'package.json'))
      )
  );
}

/**
 * Judge one uninstalled dependency the way `npm outdated` would have: `current` from the committed lockfile, `latest` from the registry's `latest` tag, `wanted` the highest stable version the declared range admits. Returns the entry (null when current), or a refusal line when either source cannot answer: unknown is unchecked, never fine.
 */
async function judgeBlindEdge(
  manifest: string,
  edge: { name: string; spec: string },
  lock: Record<string, { version?: string }> | null
): Promise<{ entry: OutdatedPackageInfo | null } | { refusal: string }> {
  const label = `${edge.name} (${manifest})`;
  if (edge.spec.startsWith('npm:')) {
    return {
      refusal: `${label}: not installed, so npm outdated skips it, and an npm: alias ("${edge.spec}") is not judged from the registry here`,
    };
  }
  const current = lock?.[`node_modules/${edge.name}`]?.version;
  if (!current) {
    return {
      refusal: `${label}: not installed, so npm outdated skips it, and package-lock.json pins no node_modules/${edge.name}`,
    };
  }
  const doc = await fetchPackument(edge.name);
  const latest = doc?.['dist-tags']?.latest;
  if (!doc || !latest) {
    return {
      refusal: `${label}: not installed, so npm outdated skips it, and the registry returned no document with a latest tag`,
    };
  }
  if (current === latest) return { entry: null };
  const sets = parseRange(edge.spec);
  const wanted = sets
    ? stableVersions(doc)
        .filter((v) => rangeAdmits(sets, v))
        .pop()
    : undefined;
  return { entry: { current, latest, wanted } };
}

/**
 * Probe one manifest. `npm outdated` runs WITHOUT `--package-lock-only`: that flag never changed what `outdated` reads (see blindEdges), and keeping it would claim a lockfile-only probe that does not exist.
 *
 * The root is always installed where the gate runs (CI's setup-workspace restores or installs it, and tsx itself comes from it), so an uninstalled root dependency is a tree that was never set up and is refused by the caller. A private manifest is NOT installed in CI (quality-content runs setup-workspace without `account: 'true'`), so its uninstalled dependencies are judged here from the lockfile and the registry instead, which is what makes CI and a developer's installed tree reach the same verdict.
 */
async function probeManifest(dir: string, isPrivate: boolean): Promise<ManifestResult> {
  const raw = (await runNpmOutdated(dir)) as RawOutdated;
  const lock = readLockPackages(dir);
  const { entries, unknown } = normalizeOutdated(raw, dir, lock);
  const name = isPrivate ? path.relative(CONSOLE_ROOT, dir).split(path.sep).join('/') : '';
  const reported = new Set(Object.keys(raw));
  const result: ManifestResult = {
    dir,
    name,
    entries,
    unknown,
    uninstalled: [],
    unjudgeable: [],
    blindJudged: 0,
  };
  if (!isPrivate) {
    // The root's report covers its workspaces too, and a workspace dependency may sit in the workspace's own node_modules or hoisted to the root's.
    for (const e of blindEdges(dir, reported, [dir])) result.uninstalled.push(`${e.name} (root)`);
    const packagesDir = path.join(dir, 'packages');
    const workspaces = fs.existsSync(packagesDir) ? fs.readdirSync(packagesDir).sort() : [];
    for (const ws of workspaces) {
      const wsDir = path.join(packagesDir, ws);
      if (!fs.existsSync(path.join(wsDir, 'package.json'))) continue;
      for (const e of blindEdges(wsDir, reported, [wsDir, dir])) {
        result.uninstalled.push(`${e.name} (packages/${ws})`);
      }
    }
    return result;
  }
  const blind = blindEdges(dir, reported, [dir]);
  result.blindJudged = blind.length;
  const judged = await Promise.all(blind.map((e) => judgeBlindEdge(name, e, lock)));
  blind.forEach((e, i) => {
    const j = judged[i];
    if ('refusal' in j) result.unjudgeable.push(j.refusal);
    else if (j.entry) result.entries[e.name] = j.entry;
  });
  return result;
}

/**
 * Fetch package info from npm registry and extract changelog URL
 */
async function fetchChangelogUrl(packageName: string): Promise<string | null> {
  // Check cache first
  if (changelogCache.has(packageName)) {
    return changelogCache.get(packageName) ?? null;
  }

  // The same registry document the release-age and clock reads already fetched: one download per package per run, shared through packumentCache.
  const doc = await fetchPackument(packageName);
  const repo = doc?.repository;
  const repoUrl = (typeof repo === 'string' ? repo : repo?.url) ?? '';

  // Transform git URL to GitHub releases URL Examples: git+https://github.com/owner/repo.git -> https://github.com/owner/repo/releases git://github.com/owner/repo.git -> https://github.com/owner/repo/releases https://github.com/owner/repo.git -> https://github.com/owner/repo/releases
  let changelogUrl: string | null = null;
  if (repoUrl.includes('github.com')) {
    const match = repoUrl.match(/github\.com[/:]([\w.-]+)\/([\w.-]+?)(\.git)?$/);
    if (match) {
      changelogUrl = `${WK_GH_ORIGIN}/${match[1]}/${match[2]}/releases`;
    }
  } else if (repoUrl.includes('gitlab.com')) {
    const match = repoUrl.match(/gitlab\.com[/:]([\w.-]+)\/([\w.-]+?)(\.git)?$/);
    if (match) {
      changelogUrl = `https://gitlab.com/${match[1]}/${match[2]}/-/releases`;
    }
  }
  changelogCache.set(packageName, changelogUrl);
  return changelogUrl;
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

/** The parts of a registry document (packument) this gate reads. */
interface Packument {
  'dist-tags'?: Record<string, string>;
  versions?: Record<
    string,
    { deprecated?: unknown; peerDependencies?: Record<string, string> } | undefined
  >;
  time?: Record<string, string>;
  repository?: { url?: string } | string;
}

// One registry document per package, cached as the PROMISE so parallel callers share one fetch.
const packumentCache = new Map<string, Promise<Packument | null>>();

/**
 * The registry document of `name`, or null on any failure. Under CHECK_DEPS_ROOT it is read from `<root>/.fixture-registry/<encodeURIComponent(name)>.json` and the network is never touched; a missing fixture document is null, exactly like an unreachable registry. Callers decide what null means: the freshness window reads it as too new, the held-major clock as CANNOT DATE.
 */
/** At most this many registry documents in flight at once. Unbounded fan-out stalls every transfer behind the slowest and trips the idle timeout, which reads as a null document and refuses the run. */
const REGISTRY_POOL_SIZE = 8;
let registryInFlight = 0;
const registryWaiters: Array<() => void> = [];

async function withRegistrySlot<T>(task: () => Promise<T>): Promise<T> {
  if (registryInFlight >= REGISTRY_POOL_SIZE) {
    await new Promise<void>((resolve) => registryWaiters.push(resolve));
  } else {
    registryInFlight++;
  }
  try {
    return await task();
  } finally {
    // Hand the slot straight to the next waiter, or free it.
    const next = registryWaiters.shift();
    if (next) next();
    else registryInFlight--;
  }
}

function fetchPackument(name: string): Promise<Packument | null> {
  const cached = packumentCache.get(name);
  if (cached) return cached;
  const loaded = FIXTURE_ROOT
    ? withRegistrySlot(async () => {
        // A fixture still goes through the pool, with a tick of latency, so the selftest drives the same concurrency path a real run does.
        await new Promise((r) => setTimeout(r, 2));
        return readFixturePackument(name);
      })
    : withRegistrySlot(
        () =>
          new Promise<Packument | null>((resolve) => {
            const url = `https://registry.npmjs.org/${encodeURIComponent(name)}`;
            const req = https.get(url, { timeout: 5000 }, (res) => {
              const chunks: Buffer[] = [];
              res.on('data', (chunk: Buffer) => {
                chunks.push(chunk);
              });
              res.on('end', () => {
                try {
                  const json = JSON.parse(Buffer.concat(chunks).toString('utf-8')) as unknown;
                  resolve(
                    typeof json === 'object' && json !== null && !Array.isArray(json)
                      ? (json as Packument)
                      : null
                  );
                } catch {
                  resolve(null);
                }
              });
            });
            req.on('error', () => resolve(null));
            req.on('timeout', () => {
              req.destroy();
              resolve(null);
            });
          })
      );
  packumentCache.set(name, loaded);
  return loaded;
}

function readFixturePackument(name: string): Packument | null {
  const p = path.join(CONSOLE_ROOT, '.fixture-registry', `${encodeURIComponent(name)}.json`);
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, 'utf-8')) as Packument;
  } catch {
    return null;
  }
}

/**
 * Fetch the publish timestamp (epoch ms) of a specific package version from the
 * npm registry's `time` map. Returns null on any failure (the freshness window
 * treats that as too new, so a hiccup never becomes a false "must upgrade").
 */
async function fetchVersionPublishTime(
  packageName: string,
  version: string
): Promise<number | null> {
  const doc = await fetchPackument(packageName);
  const stamp = doc?.time?.[version];
  const ms = stamp ? Date.parse(stamp) : Number.NaN;
  return Number.isNaN(ms) ? null : ms;
}

/** Every stable (no prerelease), non-deprecated version a registry document lists, ascending. */
function stableVersions(doc: Packument): string[] {
  return Object.entries(doc.versions ?? {})
    .filter(([v, meta]) => {
      const pv = parseVersion(v);
      return pv !== null && !pv.prerelease && !meta?.deprecated;
    })
    .map(([v]) => v)
    .sort(compareVersions);
}

/**
 * The CLOCK LINE of a held major: the line of the lowest stable, non-deprecated version above `current` that leaves current's line (and is not above `latest`). Not latest's line: that would restart the clock at every new major, which is the "free forever" hole (eslint-plugin-unicorn reads 11 days on line 76 and 108 on line 66). A skipped line (@types/node 23 was never published) is skipped here too, and 0.x lines follow releaseLine, so lucide-react 0.575 clocks from 0.576.0. Null when no such version exists.
 */
function clockLine(doc: Packument, current: string, latest: string): string | null {
  const lc = releaseLine(current);
  for (const v of stableVersions(doc)) {
    if (compareVersions(v, current) <= 0) continue;
    if (parseVersion(latest) && compareVersions(v, latest) > 0) break;
    const l = releaseLine(v);
    if (l && l !== lc) return l;
  }
  return null;
}

/** The lowest stable, non-deprecated version on `line` and its publish time; null when there is none or it carries no time. @eslint/js 10.0.0 (2024, deprecated "This version should not be used") is skipped, so line 10 starts at 10.0.1. */
function firstReleaseOfLine(doc: Packument, line: string): { version: string; ms: number } | null {
  for (const v of stableVersions(doc)) {
    if (releaseLine(v) !== line) continue;
    const stamp = doc.time?.[v];
    const ms = stamp ? Date.parse(stamp) : Number.NaN;
    return Number.isNaN(ms) ? null : { version: v, ms };
  }
  return null;
}

// ---------------------------------------------------------------------------
// Held-major exceptions (.ci/policy/deps-major-exceptions.json).
// ---------------------------------------------------------------------------

type MajorBlocker =
  | { kind: 'peer-range'; package: string; peer: string; excludes: string }
  | { kind: 'engine-floor'; engine: 'node' };

interface MajorException {
  key: string;
  scope: string | null;
  name: string;
  owner: string;
  reason: string;
  blocker?: MajorBlocker;
  /** YYYY-MM-DD, at most EXCEPTION_MAX_DAYS ahead of the run. */
  expires?: string;
}

const EXCEPTION_KEY_RE = /^(?:([^:\s]+):)?((?:@[^@/\s:]+\/)?[^@/\s:]+)$/;
const OWNER_RE = /^[A-Za-z0-9._@-]{3,}$/;
const LINE_RE = /^\d+(?:\.\d+){0,2}$/;
const ENTRY_FIELDS = new Set(['owner', 'reason', 'blocker', 'expires']);

const isoDate = (ms: number) => new Date(ms).toISOString().slice(0, 10);

/**
 * Parse the exceptions file's JSON text, refusing every entry that is not a complete, current decision. Pure apart from `nowMs`, so the selftest drives it without a file. Reason QUALITY is checked by the loader (it goes through the canonical validator). Each problem is prefixed with the file and key, ready to print.
 */
function parseMajorExceptions(
  text: string,
  nowMs: number
): { entries: MajorException[]; problems: string[] } {
  const entries: MajorException[] = [];
  const problems: string[] = [];
  const say = (key: string, msg: string) =>
    problems.push(`✗ ${MAJOR_EXCEPTIONS_REL} "${key}": ${msg}`);
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (e) {
    return {
      entries,
      problems: [`✗ ${MAJOR_EXCEPTIONS_REL}: not valid JSON: ${(e as Error).message}`],
    };
  }
  const table = (parsed as { exceptions?: unknown } | null)?.exceptions;
  if (typeof table !== 'object' || table === null || Array.isArray(table)) {
    return {
      entries,
      problems: [`✗ ${MAJOR_EXCEPTIONS_REL}: has no "exceptions" object (an empty one is {})`],
    };
  }
  const today = utcDay(nowMs);
  for (const [key, raw] of Object.entries(table as Record<string, unknown>)) {
    const km = key.match(EXCEPTION_KEY_RE);
    if (!km) {
      say(key, "key is not '<package>' or '<dir>:<package>' (blocklist grammar)");
      continue;
    }
    if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) {
      say(key, 'entry is not an object');
      continue;
    }
    const e = raw as Record<string, unknown>;
    const before = problems.length;
    for (const f of Object.keys(e)) {
      if (!ENTRY_FIELDS.has(f))
        say(key, `unknown field "${f}" (allowed: ${[...ENTRY_FIELDS].join(', ')})`);
    }
    const owner = typeof e.owner === 'string' ? e.owner.trim() : '';
    if (owner === '') say(key, 'no owner');
    else if (!OWNER_RE.test(owner)) say(key, `owner "${owner}" does not match ${OWNER_RE.source}`);
    const reason = typeof e.reason === 'string' ? e.reason.trim() : '';
    if (reason === '') say(key, 'no reason');
    const hasBlocker = e.blocker !== undefined;
    const hasExpires = e.expires !== undefined;
    let blocker: MajorBlocker | undefined;
    let expires: string | undefined;
    if (hasBlocker === hasExpires) {
      say(
        key,
        'free-text-only entries are refused; give exactly one of "blocker" (re-checked every run) or "expires" (YYYY-MM-DD, at most 30 days out)'
      );
    } else if (hasExpires) {
      const d = typeof e.expires === 'string' ? e.expires : '';
      const ms = /^\d{4}-\d{2}-\d{2}$/.test(d) ? Date.parse(`${d}T00:00:00Z`) : Number.NaN;
      if (Number.isNaN(ms) || isoDate(ms) !== d) {
        say(key, `expires "${String(e.expires)}" is not a YYYY-MM-DD date`);
      } else if (ms < today) {
        say(key, `expired on ${d}; the hold is unexcused again`);
      } else {
        const out = Math.round((ms - today) / DAY_MS);
        if (out > EXCEPTION_MAX_DAYS)
          say(key, `expires ${d} is ${out} days out; the limit is ${EXCEPTION_MAX_DAYS}`);
        else expires = d;
      }
    } else {
      const b = e.blocker as Record<string, unknown> | null;
      const kind = typeof b === 'object' && b !== null ? b.kind : undefined;
      if (kind === 'peer-range') {
        const pkg = b?.package;
        const peer = b?.peer;
        const excl = b?.excludes;
        if (
          typeof pkg !== 'string' ||
          !pkg ||
          typeof peer !== 'string' ||
          !peer ||
          typeof excl !== 'string' ||
          !LINE_RE.test(excl)
        ) {
          say(
            key,
            'a peer-range blocker needs "package", "peer" and "excludes" (a release line, e.g. "7")'
          );
        } else {
          blocker = { kind: 'peer-range', package: pkg, peer, excludes: excl };
        }
      } else if (kind === 'engine-floor') {
        if (b?.engine !== 'node') say(key, 'an engine-floor blocker needs "engine": "node"');
        else blocker = { kind: 'engine-floor', engine: 'node' };
      } else {
        say(key, `unknown blocker.kind "${String(kind)}" (known: peer-range, engine-floor)`);
      }
    }
    if (problems.length > before) continue;
    entries.push({ key, scope: km[1] ?? null, name: km[2], owner, reason, blocker, expires });
  }
  return { entries, problems };
}

/**
 * Load the exceptions file and refuse it whole on any problem, before anything is probed or installed. A MISSING file is a loud failure, as with the allow list: it is committed, so its absence means the gate is reading the wrong tree. A key must name a blocklist line: a scoped key its own scoped line or the bare one, a bare key the bare line.
 */
function loadMajorExceptions(
  blocklist: Map<string, BlocklistEntry>,
  nowMs: number
): MajorException[] {
  if (!fs.existsSync(MAJOR_EXCEPTIONS_FILE)) {
    console.error(
      `${RED}✗${NC} ${MAJOR_EXCEPTIONS_FILE} is missing. It is committed (with an empty "exceptions": {} object at the least); ` +
        'its absence means this gate is not reading the tree it thinks it is.'
    );
    process.exit(1);
  }
  const { entries, problems } = parseMajorExceptions(
    fs.readFileSync(MAJOR_EXCEPTIONS_FILE, 'utf-8'),
    nowMs
  );
  for (const e of entries) {
    const bad = validateBlockerQuality(e.key, e.reason, MAJOR_EXCEPTIONS_REL);
    if (bad) problems.push(bad.message);
    if (!blocklist.has(e.key) && !(e.scope && blocklist.has(e.name))) {
      problems.push(
        `✗ ${MAJOR_EXCEPTIONS_REL} "${e.key}": no matching line in .ci/policy/.deps-upgrade-blocklist, so there is no hold to excuse. Delete the entry.`
      );
    }
  }
  if (problems.length > 0) {
    console.error(`${RED}✗${NC} ${MAJOR_EXCEPTIONS_REL} is invalid:`);
    for (const p of problems) console.error(`  ${p}`);
    process.exit(1);
  }
  return entries;
}

interface HeldBlocked {
  pkg: PackageInfo;
  /** '' for the root. */
  manifest: string;
  dir: string;
}

interface ClockResult {
  warn: string[];
  fail: string[];
  excused: string[];
  cannotDate: string[];
}

/** The engines.node range a manifest declares, or undefined. */
function readEnginesNode(dir: string): string | undefined {
  try {
    const pkg = JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf-8')) as {
      engines?: { node?: unknown };
    };
    return typeof pkg.engines?.node === 'string' ? pkg.engines.node : undefined;
  } catch {
    return undefined;
  }
}

/**
 * Is a mechanical blocker still true? `live` with the evidence for the excused line, or `lifted` with the stale message, or `cannot` when the registry or the range cannot answer (refused, never passed).
 */
async function evaluateBlocker(
  b: MajorBlocker,
  held: HeldBlocked,
  line: string
): Promise<{ state: 'live' | 'lifted' | 'cannot'; text: string }> {
  if (b.kind === 'engine-floor') {
    const where = `${held.manifest ? `${held.manifest}/` : ''}package.json`;
    const r = readEnginesNode(held.dir);
    if (r === undefined) {
      return {
        state: 'lifted',
        text: `blocker lifted: ${where} declares no engines.node, so nothing holds ${line}.x. Delete the entry.`,
      };
    }
    const sets = parseRange(r);
    if (!sets) {
      return {
        state: 'cannot',
        text: `cannot evaluate blocker: ${where} engines.node "${r}" is not a range this gate can read; refused rather than passed`,
      };
    }
    const lineMajor = Number.parseInt(line.split('.')[0], 10);
    if (rangeFloorMajor(sets) < lineMajor) {
      return { state: 'live', text: `engine-floor: engines.node "${r}"` };
    }
    return {
      state: 'lifted',
      text: `blocker lifted: ${where} engines.node "${r}" now admits ${line}.x. Delete the entry.`,
    };
  }
  const pDoc = await fetchPackument(b.package);
  const qDoc = await fetchPackument(b.peer);
  const pv = pDoc?.['dist-tags']?.latest;
  if (!pDoc || !qDoc || !pv) {
    return {
      state: 'cannot',
      text: `cannot evaluate blocker: no registry document for ${!pDoc || !pv ? b.package : b.peer}; refused rather than passed`,
    };
  }
  const range = pDoc.versions?.[pv]?.peerDependencies?.[b.peer];
  if (range === undefined) {
    return {
      state: 'lifted',
      text: `blocker lifted: ${b.package}@${pv} no longer declares peer ${b.peer}. Delete the entry.`,
    };
  }
  const sets = parseRange(range);
  if (!sets) {
    return {
      state: 'cannot',
      text: `cannot evaluate blocker: ${b.package}@${pv} declares peer ${b.peer} "${range}", which this gate cannot parse; refused rather than passed`,
    };
  }
  const admitted = stableVersions(qDoc).find(
    (w) => releaseLine(w) === b.excludes && rangeAdmits(sets, w)
  );
  if (admitted) {
    return {
      state: 'lifted',
      text: `blocker lifted: ${b.package}@${pv} declares peer ${b.peer} "${range}", which admits ${b.peer}@${admitted}. Delete the entry.`,
    };
  }
  return {
    state: 'live',
    text: `peer-range: ${b.package}@${pv} declares peer ${b.peer} "${range}"`,
  };
}

/**
 * THE HELD-MAJOR CLOCK. Every blocklisted breaking bump is aged from the first release of its clock line: silent under 60 days, a warning from 60, a failure from 90 unless an exception excuses it. Every exception is judged too, on every run: one whose mechanical blocker has lifted is stale, one that matches no blocklist-held major in this run is dead, and both fail. Unknown age is refused, never treated as young, which is the fail-closed contract of runNpmOutdated.
 *
 * `unjudged` names the declared submodules that are not checked out here: an exception that could only match there is reported as not judged rather than as dead (CI checks them out, and refuses an empty one).
 */
async function ageHeldMajors(
  held: HeldBlocked[],
  exceptions: MajorException[],
  nowMs: number,
  unjudged: string[]
): Promise<ClockResult> {
  const out: ClockResult = { warn: [], fail: [], excused: [], cannotDate: [] };
  const used = new Set<string>();
  const exPrefix = (key: string) => `✗ ${MAJOR_EXCEPTIONS_REL} "${key}": `;
  const staleSeen = new Set<string>();
  const results = await Promise.all(
    held.map(async (h) => {
      const doc = await fetchPackument(h.pkg.name);
      return { h, doc };
    })
  );
  for (const { h, doc } of results) {
    const m = h.manifest || 'root';
    const { name, current, latest } = h.pkg;
    const exception =
      (h.manifest
        ? exceptions.find((e) => e.scope === h.manifest && e.name === name)
        : undefined) ?? exceptions.find((e) => e.scope === null && e.name === name);
    if (exception) used.add(exception.key);
    const line = doc ? clockLine(doc, current, latest) : null;
    const first = doc && line ? firstReleaseOfLine(doc, line) : null;
    if (!doc || !line || !first) {
      const lineText = line ?? `past ${releaseLine(current) ?? current}`;
      out.cannotDate.push(
        doc
          ? `✗ cannot date held major ${name} (${m}): no stable, non-deprecated release on line ${lineText} in the registry document. Unknown age is unchecked, not young.`
          : `✗ cannot date held major ${name} (${m}): no registry document for ${name}. Unknown age is unchecked, not young.`
      );
      continue;
    }
    const days = Math.floor((nowMs - first.ms) / DAY_MS);
    const deadlineMs = first.ms + HOLD_DEADLINE_DAYS * DAY_MS;
    const firstText = `line ${line} first released ${isoDate(first.ms)} (${first.version}), ${days} days ago`;

    // Every exception that matches is re-checked whatever the age: a lifted blocker is stale on a young hold too.
    let excuse: string | null = null;
    if (exception?.blocker) {
      const ev = await evaluateBlocker(exception.blocker, h, line);
      if (ev.state === 'live') {
        excuse = ev.text;
      } else {
        const msg = `${exPrefix(exception.key)}${ev.text}`;
        if (!staleSeen.has(msg)) {
          staleSeen.add(msg);
          out.fail.push(msg);
        }
      }
    } else if (exception?.expires) {
      excuse = `expires ${exception.expires}`;
    }

    if (nowMs >= deadlineMs) {
      if (excuse && exception) {
        out.excused.push(
          `  ${name} (${m}), ${days} days: excused by deps-major-exceptions.json "${exception.key}" (owner ${exception.owner}): ${excuse}`
        );
      } else {
        out.fail.push(
          `✗ Held major past ${HOLD_DEADLINE_DAYS} days: ${name} ${current} -> ${latest} (${m}): ${firstText}; deadline ${isoDate(deadlineMs)} passed. ` +
            `A .ci/policy/.deps-upgrade-blocklist line alone no longer excuses it: take it (npm run pins -- bump npm --to ${suggestedAllowKey(h.pkg, h.manifest || undefined)} --major --reason "<why now>", which drops the blocklist line) ` +
            `or add an entry to ${MAJOR_EXCEPTIONS_REL} with a mechanical blocker or an expiry at most ${EXCEPTION_MAX_DAYS} days out.`
        );
      }
    } else if (days >= HOLD_WARN_DAYS) {
      out.warn.push(
        `Held major aging: ${name} ${current} -> ${latest} (${m}): ${firstText}. Deadline ${isoDate(deadlineMs)} (${HOLD_DEADLINE_DAYS} days); after it a blocklist line no longer excuses it.`
      );
    }
  }
  for (const e of exceptions) {
    if (used.has(e.key)) continue;
    const couldBeUnjudged =
      unjudged.length > 0 &&
      (e.scope === null || unjudged.some((u) => e.scope === u || e.scope?.startsWith(`${u}/`)));
    if (couldBeUnjudged) {
      out.warn.push(
        `Not judged here: ${MAJOR_EXCEPTIONS_REL} "${e.key}" matched no hold, but ${unjudged.join(', ')} is not checked out (CI judges it).`
      );
      continue;
    }
    out.fail.push(
      `${exPrefix(e.key)}excuses nothing in this run (no blocklist-held major matches). Delete the entry.`
    );
  }
  return out;
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
  nowMs: number,
  publishTime: (name: string, version: string) => Promise<number | null> = fetchVersionPublishTime
): Promise<{ installable: PackageInfo[]; tooNew: PackageInfo[] }> {
  if (minReleaseAgeMs <= 0 || packages.length === 0) {
    return { installable: packages, tooNew: [] };
  }
  // The lookups run concurrently, but the partition keeps the input order, so two runs over the same tree print the same lines in the same order whatever order the registry answers in.
  const fresh = await Promise.all(
    packages.map(async (pkg) => {
      const published = await publishTime(pkg.name, pkg.latest);
      // Fail-closed: a null publish time (registry hiccup) is treated as too-new.
      return published === null || isWithinFreshnessWindow(published, nowMs, minReleaseAgeMs);
    })
  );
  return {
    installable: packages.filter((_pkg, i) => !fresh[i]),
    tooNew: packages.filter((_pkg, i) => fresh[i]),
  };
}

/** Each package with the peerDependencies its TARGET version declares, read from the registry document the freshness partition already fetched (the cache serves it, so no extra request). The install planner folds an in-range package into an install when an out-of-range one peer-requires a version of it the tree lacks. A package whose document or version is missing carries no `peers` and is never folded. */
async function withTargetPeers(packages: PackageInfo[]): Promise<PackageInfo[]> {
  return Promise.all(
    packages.map(async (pkg) => {
      const peers = (await fetchPackument(pkg.name))?.versions?.[pkg.latest]?.peerDependencies;
      return peers && Object.keys(peers).length > 0 ? { ...pkg, peers } : pkg;
    })
  );
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

/**
 * Show help message
 */
function showHelpMessage(): void {
  console.log(`
${BLUE}check-deps.ts${NC} - Dependency version enforcement

${YELLOW}USAGE${NC}
  npx tsx scripts/gates/check-deps.ts [OPTIONS]

${YELLOW}OPTIONS${NC}
  --plan-json     Print the read-only npm plan the pins command consumes (one PLAN-JSON line)
  --help, -h      Show this help message

${YELLOW}DESCRIPTION${NC}
  Checks for outdated npm dependencies in the console root, the workers/
  manifests and the private/ submodule manifests, and fails if any are found.
  The fix is \`npm run pins -- bump npm\`; this gate never installs anything.
  Packages can be blocklisted in .ci/policy/.deps-upgrade-blocklist to hold them.
  A breaking upgrade (new major, or new minor on 0.x) is never applied by
  \`pins -- bump npm\` unless \`--to <package>@<line> --major --reason\` names it.
  A blocklisted major is aged from the first release of the first line past
  its current version: it warns at ${HOLD_WARN_DAYS} days and fails at ${HOLD_DEADLINE_DAYS} unless
  ${MAJOR_EXCEPTIONS_REL} excuses it (owner, reason, and exactly
  one of a re-checked peer-range/engine-floor blocker or an expiry at most
  ${EXCEPTION_MAX_DAYS} days out).

${YELLOW}BLOCKLIST FORMAT${NC}
  package-name  # BLOCKER: reason for blocking

${YELLOW}EXCEPTION FORMAT${NC} (${MAJOR_EXCEPTIONS_REL})
  {"exceptions": {"<pkg>" or "<dir>:<pkg>": {"owner": "...", "reason": "...",
    "blocker": {"kind": "peer-range", "package": P, "peer": Q, "excludes": "<line>"}
             | {"kind": "engine-floor", "engine": "node"}
    or "expires": "YYYY-MM-DD"}}}

${YELLOW}EXAMPLES${NC}
  npx tsx scripts/gates/check-deps.ts           # Check for outdated packages
  npm run pins -- bump npm                # Upgrade non-breaking outdated packages
  npm run check:deps                      # Via npm script
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

  if (MUTANT !== undefined && MUTANT !== '') {
    if (!FIXTURE_ROOT || !MUTANTS.includes(MUTANT)) {
      console.error(
        `${RED}✗${NC} CHECK_DEPS_MUTANT=${MUTANT} refused: the mutants are ${MUTANTS.map((m) => `"${m}"`).join(', ')}, honoured only under ` +
          'CHECK_DEPS_ROOT (a selftest fixture). On a real tree they would switch the held-major clock off, split a lockstep update, run an update before the install that unpins it, leave a syncpack pin group behind or plan an unpinned npm, so they are never honoured there.'
      );
      process.exit(1);
    }
    console.log(
      MUTANT === 'ignore-clock'
        ? `${YELLOW}MUTANT ignore-clock: the held-major clock is OFF for this fixture run${NC}\n`
        : MUTANT === 'split-update'
          ? `${YELLOW}MUTANT split-update: one npm update per manifest for this fixture run${NC}\n`
          : MUTANT === 'skip-pin-sync'
            ? `${YELLOW}MUTANT skip-pin-sync: the .syncpackrc.json pin groups are NOT rewritten for this fixture run${NC}\n`
            : MUTANT === 'ambient-npm'
              ? `${YELLOW}MUTANT ambient-npm: the pins npm driver plans the ambient npm for this fixture run${NC}\n`
              : MUTANT === 'peer-split'
                ? `${YELLOW}MUTANT peer-split: an in-range peer sibling is left to the later npm update for this fixture run${NC}\n`
                : `${YELLOW}MUTANT update-first: every npm update runs before the npm install steps for this fixture run${NC}\n`
    );
  }
  const clockOff = MUTANT === 'ignore-clock' || planJson;

  console.log('Checking dependency versions...\n');

  const startMs = Date.now();
  const blocklist = loadBlocklist();
  const heldKeys = new Set(blocklist.keys());
  const allow = loadMajorAllow();
  const exceptions = loadMajorExceptions(blocklist, startMs);
  // The transient entries of a `--major` plan (--plan-json only): an allow entry that exists for this plan alone, and a blocklist line that is treated as absent. Nothing is written; the pins driver removes the real blocklist line and exception in the same transaction as the install.
  if (planJson) {
    for (const key of planUnblock) blocklist.delete(key);
    for (const key of planAllow) {
      const m = key.match(ALLOW_KEY_RE);
      if (!m) {
        console.error(
          `${RED}✗${NC} --allow "${key}" is not '<package>@<line>' or '<dir>:<package>@<line>'`
        );
        process.exit(1);
      }
      allow.push({
        key,
        scope: m[1] ?? null,
        name: m[2],
        line: m[3],
        reason: 'transient: a pins --major plan',
      });
    }
  } else if (planAllow.length > 0 || planUnblock.length > 0) {
    console.error(`${RED}✗${NC} --allow and --unblock are honoured only with --plan-json`);
    process.exit(1);
  }

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

  // The probes are independent (each reads its own tree and lockfile), so they run together; Promise.all keeps the manifest order and rejects on the first failed probe, which is the same refusal the serial loop gave.
  const manifests: ManifestResult[] = await Promise.all([
    probeManifest(CONSOLE_ROOT, false),
    ...scan.dirs.map((dir) => probeManifest(dir, true)),
  ]);

  // An uninstalled dependency is unjudged, never current. Refused here, before anything is categorised, so no verdict below (above all the clock's "excuses nothing ... Delete the entry") is ever reached from a manifest npm could not see.
  const uninstalledRoot = manifests.flatMap((m) => m.uninstalled);
  if (uninstalledRoot.length > 0) {
    console.error(
      `${RED}✗${NC} ${uninstalledRoot.length} declared dev/optional/peer dependency(ies) of the root are not installed, so npm outdated skips them and this gate cannot judge them:`
    );
    for (const u of uninstalledRoot) console.error(`  ${u}`);
    console.error(
      '  Install the root tree, then re-run: npm ci && npm run install:natives\n' +
        '  (CI restores or installs it in setup-workspace, so this means a tree that was never set up.)'
    );
    process.exit(1);
  }
  const unjudgeable = manifests.flatMap((m) => m.unjudgeable);
  if (unjudgeable.length > 0) {
    console.error(
      `${RED}✗${NC} ${unjudgeable.length} uninstalled dependency(ies) could not be judged, so the run is refused rather than read as current:`
    );
    for (const u of unjudgeable) console.error(`  ${u}`);
    console.error(
      '  Fix the source named on each line (an unreachable registry, a lockfile missing the package), or install\n' +
        '  that manifest (npm ci in its directory) so npm judges it from disk, then re-run.'
    );
    process.exit(1);
  }
  const blindJudged = manifests.reduce((s, m) => s + m.blindJudged, 0);

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
  const heldBlocked: HeldBlocked[] = [];
  let judged = 0;
  // Registry reads start here for every manifest at once (bounded by the pool in fetchPackument), so the release-age partitions overlap instead of queueing manifest after manifest.
  const partitions = manifests.map((m) => {
    const cat = categorizePackages(m.entries, blocklist, m.name || undefined, allow);
    return {
      cat,
      must: partitionByReleaseAge(cat.mustUpgrade, minReleaseAgeMs, nowMs),
      held: partitionByReleaseAge(cat.heldMajor, minReleaseAgeMs, nowMs),
    };
  });
  for (const [mi, m] of manifests.entries()) {
    judged += Object.keys(m.entries).length;
    const cat = partitions[mi].cat;
    for (const k of cat.allowUsed) allowUsed.add(k);
    // The blocked branch runs BEFORE the breaking-bump test in categorizePackages, so a blocklisted major lands here and never in heldMajor. The clock below is what stops that line excusing it forever; minor holds (playwright) are outside it.
    for (const p of cat.blocked) {
      if (isBreakingBump(p.current, p.latest))
        heldBlocked.push({ pkg: p, manifest: m.name, dir: m.dir });
    }
    // Defer versions still inside the freshness window (aged < 24h, rounded up to the next UTC day): too fresh to be a real "must upgrade" or a real decision. This auto-resolves as a daily batch once the version ages out.
    const must = await partitions[mi].must;
    const held = await partitions[mi].held;
    groups.push({
      dir: m.dir,
      name: m.name,
      mustUpgrade: await withTargetPeers(must.installable),
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

  const clock: ClockResult = clockOff
    ? { warn: [], fail: [], excused: [], cannotDate: [] }
    : await ageHeldMajors(heldBlocked, exceptions, nowMs, scan.uninitialized);
  const clockFailures = clock.fail.length + clock.cannotDate.length;
  /** The clock's verdicts: warnings and excused lines on stdout every run (never silent), failures on stderr. */
  const printClock = () => {
    for (const w of clock.warn) console.log(`${YELLOW}${w}${NC}`);
    if (clock.warn.length > 0) console.log();
    if (clock.excused.length > 0) {
      console.log(
        `Held majors past ${HOLD_DEADLINE_DAYS} days, excused (${clock.excused.length}):`
      );
      for (const e of clock.excused) console.log(e);
      console.log();
    }
    for (const f of [...clock.cannotDate, ...clock.fail]) console.error(`${RED}${f}${NC}`);
    if (clockFailures > 0) console.error();
  };

  const sum = (pick: (g: ManifestGroup) => PackageInfo[]) =>
    groups.reduce((s, g) => s + pick(g).length, 0);
  const totalMust = sum((g) => g.mustUpgrade);
  const totalHeld = sum((g) => g.heldMajor);
  const totalBlocked = sum((g) => g.blocked);
  const totalTooNew = sum((g) => g.tooNew);
  const shape =
    `judged ${judged} package(s) across ${manifests.length} manifest(s) ` +
    `(${manifests.map((m) => m.name || 'root').join(', ')}), ` +
    `${blindJudged} uninstalled dependency(ies) judged from lockfile and registry`;

  const deferredSummary = (): string => {
    const parts: string[] = [];
    if (totalBlocked > 0) parts.push(`${totalBlocked} blocked`);
    if (totalTooNew > 0) parts.push(`${totalTooNew} too new`);
    return parts.length > 0 ? ` (${parts.join(', ')})` : '';
  };

  const printHeld = (changelogUrls?: Map<string, string | null>) => {
    if (totalHeld === 0) return;
    console.log(
      `${RED}Major upgrades awaiting a decision (${totalHeld}); \`npm run pins -- bump npm\` never applies these:${NC}\n`
    );
    for (const g of groups) {
      for (const pkg of g.heldMajor) {
        printPackage(pkg, { suffix: where(g.name), changelogUrls });
        console.log(
          `    Take it:  npm run pins -- bump npm --to ${suggestedAllowKey(pkg, g.name || undefined)} --major --reason "<why now>"`
        );
      }
    }
    console.log(
      `\n  Or hold it: add a '<package>  # BLOCKER: <reason>' line to .ci/policy/.deps-upgrade-blocklist.\n`
    );
  };

  if (planJson) {
    const steps = planInstalls(
      CONSOLE_ROOT,
      groups[0].mustUpgrade,
      groups.slice(1).map((g) => ({ dir: g.dir, name: g.name, packages: g.mustUpgrade })),
      freshnessCutoffMs(nowMs, minReleaseAgeMs)
    );
    const blockedMajors = groups.flatMap((g) =>
      g.blocked.filter((pkg) => isBreakingBump(pkg.current, pkg.latest)).map((pkg) => ({ g, pkg }))
    );
    // Held majors were window-partitioned above; a blocklisted one is not, so it is dated here.
    const blockedAge = await Promise.all(
      blockedMajors.map(({ pkg }) =>
        minReleaseAgeMs > 0 ? fetchVersionPublishTime(pkg.name, pkg.latest) : Promise.resolve(null)
      )
    );
    const majors = [
      ...groups.flatMap((g) =>
        g.heldMajor.map((pkg) => ({
          key: suggestedAllowKey(pkg, g.name || undefined),
          blockKey: null as string | null,
          pkg,
          manifest: g.name,
          publishedMs: null as number | null,
        }))
      ),
      ...blockedMajors.map(({ g, pkg }, i) => ({
        key: suggestedAllowKey(pkg, g.name || undefined),
        blockKey:
          g.name && heldKeys.has(`${g.name}:${pkg.name}`) ? `${g.name}:${pkg.name}` : pkg.name,
        pkg,
        manifest: g.name,
        publishedMs: blockedAge[i],
      })),
    ];
    const plan = {
      nowMs,
      minReleaseAgeMs,
      steps,
      majors,
      tooNew: groups.flatMap((g) => g.tooNew.map((pkg) => ({ pkg, manifest: g.name }))),
      manifests: groups.map((g) => g.name || '.'),
    };
    console.log(`PLAN-JSON ${JSON.stringify(plan)}`);
    process.exit(0);
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

  const hasFailure = totalMust > 0 || totalHeld > 0 || clockFailures > 0;

  for (const g of groups) {
    const header = g.name
      ? `${RED}Outdated packages in ${g.name} (must upgrade):${NC}`
      : `${RED}Outdated packages (must upgrade):${NC}`;
    printPackageGroup(header, g.mustUpgrade, { changelogUrls });
  }
  if (totalMust > 0) {
    // A held major beside the in-range bumps makes the plain bump refuse (scripts/lib/pins/driver.ts splitFamilySet), so the line names every held major instead.
    const heldKeys = groups.flatMap((g) =>
      g.heldMajor.map((pkg) => suggestedAllowKey(pkg, g.name || undefined))
    );
    console.log(
      heldKeys.length > 0
        ? `Run: npm run pins -- bump npm ${heldKeys.map((k) => `--to ${k}`).join(' ')} --major --reason "<why now>"`
        : 'Run: npm run pins -- bump npm'
    );
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

  printClock();

  if (hasFailure) {
    console.log(
      `${RED}Dependency check FAILED${NC}: ${totalMust} must upgrade, ${totalHeld} major(s) awaiting a decision, ${clockFailures} held-major clock failure(s); ${shape}`
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
  /** Lockfile `packages` maps per manifest, same keys. An entry's `dependencies` is the range that installed copy declares; an EXACT one pins the named package for the stub `npm update` (see bin/exact-pins.cjs in buildFixture). */
  locks: Record<string, Record<string, { version: string; dependencies?: Record<string, string> }>>;
  allow?: Record<string, string>;
  blocklist?: string;
  /** package.json content per manifest, same keys; '{}' when absent. */
  manifests?: Record<string, object>;
  /** package.json text per manifest, written verbatim over `manifests`, for a manifest that is not in npm's two-space form. */
  rawManifests?: Record<string, string>;
  /** Lockfile `packages` map the stub `npm update` writes per manifest, same keys: what npm "resolved". */
  updateLocks?: Record<string, Record<string, { version: string }>>;
  /** Lockfile entries the stub `npm install` merges in per manifest, same keys: what npm "resolved" for the install, e.g. the new sibling and the range it now declares. */
  installLocks?: Record<
    string,
    Record<string, { version: string; dependencies?: Record<string, string> }>
  >;
  /** Extra environment for the gate process (the npm_config_loglevel control, the clock mutant). */
  env?: NodeJS.ProcessEnv;
  /** Registry documents by package name, served from `<root>/.fixture-registry/`. */
  registry?: Record<string, Packument>;
  /** The `exceptions` object of .ci/policy/deps-major-exceptions.json; `{}` when absent. */
  exceptions?: Record<string, unknown>;
  /** Extra files by path from the fixture root, e.g. an installed `node_modules/<name>/package.json`. */
  files?: Record<string, string>;
  /** Lockstep families per manifest, same keys: the stub `npm update` fails ERESOLVE when it names any package of a family without naming all of them AND passing `-w=` for every workspace listed (each holds a nested copy pinned to the others), as real npm did for vitest + @vitest/* on 2026-10-02. */
  lockstep?: Record<string, Array<{ names: string[]; workspaces: string[] }>>;
  /** The fixture's .syncpackrc.json text, written verbatim; absent means the fixture has none. */
  syncpackrc?: string;
  /** Peer requirements per manifest, same keys: the stub `npm install` fails ERESOLVE when it names `spec` without also naming `needs`, as real npm did for @opentelemetry/core@3 (peer @opentelemetry/api >=1.10) on 2026-10-22. */
  installPeers?: Record<string, Array<{ spec: string; needs: string }>>;
}

// The fixture's local-only, non-submodule directory. See its use in `buildFixture` below.
const GROWTH_DIR = 'private/growth';

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
  write(
    '.ci/config/deps-major-allow.json',
    `${JSON.stringify({ allow: spec.allow ?? {} }, null, 2)}\n`
  );
  write(
    path.relative(root, policyPath('.deps-upgrade-blocklist', root)),
    spec.blocklist ?? '# fixture blocklist\n'
  );
  write(
    path.relative(root, policyPath('deps-major-exceptions.json', root)),
    `${JSON.stringify({ exceptions: spec.exceptions ?? {} }, null, 2)}\n`
  );
  for (const [name, doc] of Object.entries(spec.registry ?? {})) {
    write(path.join('.fixture-registry', `${encodeURIComponent(name)}.json`), JSON.stringify(doc));
  }
  // Local-only, NOT a submodule: must never be scanned, and its canned report would be a must-upgrade if it were. `GROWTH_DIR` (module scope, extension-less) plus a template literal here, rather than a whole quoted `private/growth/...` literal, keeps the dead-path detector (`.ci/rediacc_ci/tests/gates/test_gate_paths_exist.py`, which replaced the retired `check:ci-paths-exist`) from reading this fixture path as a real one: on a machine where `private/growth` happens to be checked out (a separate, gitignored sibling repo -- see CLAUDE.md's worktree warning) the bare literal would otherwise resolve to Tier A and then dead-end at Tier B, since neither fixture file is real.
  write(`${GROWTH_DIR}/package.json`, '{}');
  write(
    `${GROWTH_DIR}/.fixture-outdated.json`,
    JSON.stringify({ leftpad: { current: '1.0.0', latest: '1.0.1' } })
  );
  for (const [rel, text] of Object.entries(spec.files ?? {})) write(rel, text);
  if (spec.syncpackrc !== undefined) write('.syncpackrc.json', spec.syncpackrc);
  const manifestDirs = [
    '',
    ...Object.keys(spec.outdated),
    ...Object.keys(spec.locks),
    ...Object.keys(spec.manifests ?? {}),
    ...Object.keys(spec.rawManifests ?? {}),
  ];
  for (const rel of new Set(manifestDirs)) {
    // Written the way npm writes a manifest (two-space indent, trailing newline), because the override bump refuses a package.json it cannot round-trip byte for byte.
    write(
      path.join(rel, 'package.json'),
      spec.rawManifests?.[rel] ?? `${JSON.stringify(spec.manifests?.[rel] ?? {}, null, 2)}\n`
    );
    write(path.join(rel, '.fixture-outdated.json'), JSON.stringify(spec.outdated[rel] ?? {}));
    if (spec.locks[rel])
      write(path.join(rel, 'package-lock.json'), JSON.stringify({ packages: spec.locks[rel] }));
    if (spec.lockstep?.[rel])
      write(path.join(rel, '.fixture-lockstep.json'), JSON.stringify(spec.lockstep[rel]));
    if (spec.installPeers?.[rel])
      write(path.join(rel, '.fixture-install-peers.json'), JSON.stringify(spec.installPeers[rel]));
    if (spec.updateLocks?.[rel])
      write(
        path.join(rel, '.fixture-update-lock.json'),
        JSON.stringify({ packages: spec.updateLocks[rel] })
      );
    if (spec.installLocks?.[rel])
      write(
        path.join(rel, '.fixture-install-lock.json'),
        JSON.stringify({ packages: spec.installLocks[rel] })
      );
  }
  const log = path.join(root, 'npm-install.log');
  // What real npm does with an exact-version `overrides` entry, measured 2026-10-01 on npm 11.20.0: `npm update` of an overridden package resolves the override's version, whatever newer version the declared range allows. The stub applies the same clamp after it writes the "resolved" lockfile, so a plan that ignores the override fails here exactly as it failed on the real tree.
  write(
    'bin/clamp-overrides.cjs',
    [
      "const fs = require('node:fs');",
      "if (!fs.existsSync('package-lock.json')) process.exit(0);",
      "const ov = JSON.parse(fs.readFileSync('package.json', 'utf8')).overrides || {};",
      "const lock = JSON.parse(fs.readFileSync('package-lock.json', 'utf8'));",
      'lock.packages = lock.packages || {};',
      'for (const name of process.argv.slice(2)) {',
      "  if (typeof ov[name] === 'string' && /^\\d+\\.\\d+\\.\\d+$/.test(ov[name])) lock.packages[`node_modules/${name}`] = { version: ov[name] };",
      '}',
      "fs.writeFileSync('package-lock.json', JSON.stringify(lock));",
      '',
    ].join('\n')
  );
  // The ERESOLVE an exact peer pin produces when a lockstep family is updated piecemeal: npm leaves the copies outside the call on the old version, and their exact peer refuses the new one.
  write(
    'bin/check-lockstep.cjs',
    [
      "const fs = require('node:fs');",
      "if (!fs.existsSync('.fixture-lockstep.json')) process.exit(0);",
      'const args = process.argv.slice(2);',
      "for (const fam of JSON.parse(fs.readFileSync('.fixture-lockstep.json', 'utf8'))) {",
      '  if (!fam.names.some((n) => args.includes(n))) continue;',
      '  const missing = [...fam.names.filter((n) => !args.includes(n)), ...fam.workspaces.filter((w) => !args.includes(`-w=${w}`)).map((w) => `-w=${w}`)];',
      "  if (missing.length > 0) { console.error(`npm error code ERESOLVE (fixture): exact peer pin, the call lacks ${missing.join(' ')}`); process.exit(1); }",
      '}',
      '',
    ].join('\n')
  );
  // The ERESOLVE a peer requirement produces when `install` names a package without the in-range sibling it peer-requires: the sibling is still at its old version in the tree, so npm refuses.
  write(
    'bin/check-peers.cjs',
    [
      "const fs = require('node:fs');",
      "if (!fs.existsSync('.fixture-install-peers.json')) process.exit(0);",
      'const args = process.argv.slice(2);',
      "for (const p of JSON.parse(fs.readFileSync('.fixture-install-peers.json', 'utf8'))) {",
      '  if (!args.includes(p.spec) || args.includes(p.needs)) continue;',
      '  console.error(`npm error code ERESOLVE (fixture): ${p.spec} requires ${p.needs}, the call does not name it`);',
      '  process.exit(1);',
      '}',
      '',
    ].join('\n')
  );
  // What real npm did on 2026-10-08 (npm 11.20.0) with a package an installed sibling pins EXACTLY: @opentelemetry/sdk-node@0.222.0 requires @opentelemetry/core "2.11.0", and `npm update @opentelemetry/core` kept 2.11.0 and exited 0. `pre` snapshots the lockfile before the stub update writes its "resolved" one; `post` then rebuilds it as the snapshot plus every resolved entry whose package no snapshot entry pins exactly to another version, so a pinned package stays where it was. Both are no-ops unless the snapshot carries a `dependencies` map, so every fixture without one keeps the plain copy. `install` merges `.fixture-install-lock.json` into the lockfile, so an install that moves the pinning sibling releases the pin for a later update.
  write(
    'bin/exact-pins.cjs',
    [
      "const fs = require('node:fs');",
      "const read = (f) => (fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, 'utf8')).packages || {} : {});",
      "const save = (pkgs) => fs.writeFileSync('package-lock.json', JSON.stringify({ packages: pkgs }));",
      'const [mode, ...args] = process.argv.slice(2);',
      "const names = args.filter((a) => !a.startsWith('-'));",
      "if (mode === 'install') {",
      "  if (fs.existsSync('.fixture-install-lock.json')) save({ ...read('package-lock.json'), ...read('.fixture-install-lock.json') });",
      '  process.exit(0);',
      '}',
      "if (mode === 'pre') {",
      "  const lock = read('package-lock.json');",
      "  if (Object.values(lock).some((e) => e.dependencies)) fs.writeFileSync('.fixture-pre-update-lock.json', JSON.stringify({ packages: lock }));",
      '  process.exit(0);',
      '}',
      "if (!fs.existsSync('.fixture-pre-update-lock.json')) process.exit(0);",
      "const before = read('.fixture-pre-update-lock.json');",
      "fs.rmSync('.fixture-pre-update-lock.json');",
      "const resolved = read('package-lock.json');",
      'const out = { ...before };',
      'for (const [key, entry] of Object.entries(resolved)) {',
      "  const name = key.slice(key.lastIndexOf('node_modules/') + 'node_modules/'.length);",
      '  const pinned = names.includes(name) && Object.values(before).some((e) => {',
      '    const r = (e.dependencies || {})[name];',
      "    return typeof r === 'string' && /^\\d+\\.\\d+\\.\\d+$/.test(r) && r !== entry.version;",
      '  });',
      '  if (!pinned) out[key] = entry;',
      '}',
      'save(out);',
      '',
    ].join('\n')
  );
  // `npm uninstall <names> [-w=<ws>]... [--include-workspace-root]`: drops the names from the manifests it is scoped to and from the lockfile, as real npm does.
  write(
    'bin/uninstall.cjs',
    [
      "const fs = require('node:fs');",
      'const args = process.argv.slice(2);',
      "const names = args.filter((a) => !a.startsWith('-'));",
      "const ws = args.filter((a) => a.startsWith('-w=')).map((a) => a.slice(3));",
      "const dirs = [...ws, ...(ws.length === 0 || args.includes('--include-workspace-root') ? ['.'] : [])];",
      'for (const d of dirs) {',
      '  const f = `${d}/package.json`;',
      "  const j = JSON.parse(fs.readFileSync(f, 'utf8'));",
      "  for (const k of ['dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies']) for (const n of names) if (j[k]) delete j[k][n];",
      '  fs.writeFileSync(f, `${JSON.stringify(j, null, 2)}\n`);',
      '}',
      "if (fs.existsSync('package-lock.json')) {",
      "  const l = JSON.parse(fs.readFileSync('package-lock.json', 'utf8'));",
      '  for (const n of names) delete (l.packages || {})[`node_modules/${n}`];',
      "  fs.writeFileSync('package-lock.json', JSON.stringify(l));",
      '}',
      '',
    ].join('\n')
  );
  const pins = `"${process.execPath}" "${path.join(root, 'bin', 'exact-pins.cjs')}"`;
  write(
    'bin/npm',
    [
      '#!/bin/sh',
      'case "$1" in',
      '  outdated) if [ -f .fixture-outdated.json ]; then cat .fixture-outdated.json; else echo "{}"; fi; exit 1 ;;',
      // Every install/update is recorded with the loglevel the child inherited, and a spec naming `fail-me` exits 7, so the selftest can see both the verb chosen and the failure report.
      // The canonical lockfile pass, `npm ci` and `npm run ...` are the pins transaction's own steps; they are logged apart so the install log keeps only the driver's planned verbs.
      `  ci|run) echo "$(pwd) :: $*" >> "${log}.other"; exit 0 ;;`,
      `  uninstall) shift; echo "$(pwd) :: uninstall $*" >> "${log}"; "${process.execPath}" "${path.join(root, 'bin', 'uninstall.cjs')}" "$@"; exit 0 ;;`,
      `  install) case "$*" in *--package-lock-only*) echo "$(pwd) :: $*" >> "${log}.other"; exit 0 ;; esac ;;`,
      `  esac`,
      `case "$1" in`,
      `  install|update) echo "$(pwd) :: $* :: loglevel=\${npm_config_loglevel:-} :: via=\${FIXTURE_VIA_NPX:-ambient}" >> "${log}"; case "$*" in *fail-me*) echo "fixture npm: refusing $*" >&2; exit 7 ;; esac; if [ "$1" = update ]; then "${process.execPath}" "${path.join(root, 'bin', 'check-lockstep.cjs')}" "$@" || exit 1; fi; if [ "$1" = install ]; then "${process.execPath}" "${path.join(root, 'bin', 'check-peers.cjs')}" "$@" || exit 1; ${pins} install "$@"; fi; if [ "$1" = update ]; then ${pins} pre "$@"; fi; if [ "$1" = update ] && [ -f .fixture-update-lock.json ]; then cp .fixture-update-lock.json package-lock.json; fi; if [ "$1" = update ]; then ${pins} post "$@"; "${process.execPath}" "${path.join(root, 'bin', 'clamp-overrides.cjs')}" "$@"; fi; exit 0 ;;`,
      '  *) echo "fixture npm stub: unexpected: $*" >&2; exit 2 ;;',
      'esac',
      '',
    ].join('\n')
  );
  fs.chmodSync(path.join(root, 'bin', 'npm'), 0o755);
  fs.writeFileSync(log, '');
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    ...spec.env,
    CHECK_DEPS_ROOT: root,
    PATH: `${path.join(root, 'bin')}${path.delimiter}${process.env.PATH ?? ''}`,
  };
  delete env.CHECK_DEPS_FORCE_PROBE_FAILURE;
  if (spec.env?.CHECK_DEPS_MUTANT === undefined) delete env.CHECK_DEPS_MUTANT;
  return { root, log, env };
}

/** The pins CLI, which `bump npm` and friends run through (the old `--upgrade` verb lives there now). */
const PINS_CLI = path.join(__dirname, '..', 'pins', 'pins.ts');

/**
 * Turn a built fixture into a tree the pins CLI can run in: the pinned npm in toolchain.env, a registry holding only the npm family, a stub `npx` that accepts `-y npm@<version>` only and records it, and a git repository (the transaction refuses a site file another session changed, and a submodule is its own repository). The stub's logs, `bin/` and the fixture's scratch files are excluded from git, so the transaction sees only what a step really changed.
 */
function preparePinsFixture(root: string): void {
  const w = (rel: string, text: string) => {
    fs.mkdirSync(path.dirname(path.join(root, rel)), { recursive: true });
    fs.writeFileSync(path.join(root, rel), text);
  };
  w('.devcontainer/toolchain.env', `NPM_VERSION=${FIXTURE_NPM_VERSION}\n`);
  const real = JSON.parse(
    fs.readFileSync(path.join(__dirname, '..', '..', '.ci', 'config', 'pins.json'), 'utf8')
  ) as { entries: Array<{ driver: string }> } & Record<string, unknown>;
  const reg = {
    ...real,
    submodules: { scanned: ['private/account'], unscanned: [] },
    entries: real.entries.filter((e) => e.driver === 'npm'),
    ignores: [],
  };
  w('.ci/config/pins.json', `${JSON.stringify(reg, null, 2)}\n`);
  w(
    'bin/npx',
    [
      '#!/bin/sh',
      'if [ "$1" != "-y" ]; then echo "fixture npx: unexpected: $*" >&2; exit 2; fi',
      'spec="$2"; shift 2',
      'case "$spec" in npm@*) ;; *) echo "fixture npx: not a pinned npm: $spec" >&2; exit 2 ;; esac',
      'n=$#',
      'while [ "$n" -gt 0 ]; do a="$1"; shift; case "$a" in --loglevel=*) export npm_config_loglevel="${a#--loglevel=}" ;; *) set -- "$@" "$a" ;; esac; n=$((n-1)); done',
      'export FIXTURE_VIA_NPX="$spec"',
      'exec npm "$@"',
      '',
    ].join('\n')
  );
  fs.chmodSync(path.join(root, 'bin', 'npx'), 0o755);
  const git = (cwd: string, ...args: string[]): void => {
    const r = spawnSync(
      'git',
      ['-c', 'user.email=f@x', '-c', 'user.name=f', '-c', 'commit.gpgsign=false', ...args],
      { cwd, encoding: 'utf8' }
    );
    if (r.status !== 0) throw new Error(`fixture git ${args.join(' ')}: ${r.stderr}`);
  };
  const exclude = ['/bin/', '/npm-install.log*', '.fixture-*', '/.ci/cache/', '/private/growth/'];
  for (const dir of [root, path.join(root, 'private', 'account')]) {
    fs.rmSync(path.join(dir, '.git'), { recursive: true, force: true });
    git(dir, 'init', '-q');
    fs.appendFileSync(path.join(dir, '.git', 'info', 'exclude'), `${exclude.join('\n')}\n`);
    if (dir !== root) {
      git(dir, 'add', '-A');
      git(dir, 'commit', '-q', '-m', 'fixture');
    }
  }
  git(root, 'add', '-A');
  git(root, 'commit', '-q', '-m', 'fixture');
}

interface FixtureRun {
  status: number | null;
  output: string;
  installs: string[];
  /** The canonical lockfile passes, `npm ci` and `npm run` calls, which the pins transaction makes itself. */
  other: string[];
  root: string;
  /** The root package.json as the run left it. */
  rootManifest: string;
  /** The .syncpackrc.json as the run left it, or null when the fixture had none. */
  syncpackrc: string | null;
  /** Every file under the fixture (relative path to text), for the cases that assert a net diff. */
  files: Map<string, string>;
}

/** The parsed `--plan-json` of a fixture tree: what the pins npm driver would be handed. */
function planJsonOf(
  spec: FixtureSpec,
  flags: string[] = []
): {
  steps: InstallStep[];
  majors: Array<{ key: string; blockKey: string | null; pkg: PackageInfo; manifest: string }>;
} {
  const fx = buildFixture(spec);
  try {
    const child = spawnSync(
      process.execPath,
      [...process.execArgv, process.argv[1], '--plan-json', ...flags],
      { cwd: fx.root, encoding: 'utf-8', env: fx.env }
    );
    const line = (child.stdout ?? '').split('\n').find((l) => l.startsWith('PLAN-JSON '));
    if (!line) throw new Error(`no plan: ${child.stdout}${child.stderr}`);
    return JSON.parse(line.slice('PLAN-JSON '.length));
  } finally {
    fs.rmSync(fx.root, { recursive: true, force: true });
  }
}

/**
 * Run the real script on a fixture tree. `check` runs the gate; `upgrade` runs the pins CLI (`pinsArgs`, default `bump npm`) against the same tree with the recording npm stub, the replacement of the retired `check-deps --upgrade`. The output of a pins run includes the transaction's command log, where a failed step's own stderr is.
 */
function runFixture(
  spec: FixtureSpec,
  mode: 'check' | 'upgrade',
  pinsArgs: string[] = ['bump', 'npm']
): FixtureRun {
  const fx = buildFixture(spec);
  try {
    if (mode === 'upgrade') preparePinsFixture(fx.root);
    const child = spawnSync(
      process.execPath,
      [...process.execArgv, ...(mode === 'upgrade' ? [PINS_CLI, ...pinsArgs] : [process.argv[1]])],
      {
        cwd: fx.root,
        encoding: 'utf-8',
        env: mode === 'upgrade' ? { ...fx.env, PINS_ROOT: fx.root } : fx.env,
      }
    );
    const read = (f: string): string[] =>
      fs.existsSync(f)
        ? fs
            .readFileSync(f, 'utf-8')
            .split('\n')
            .filter(Boolean)
            .map((l) => l.replaceAll(fx.root, '<root>'))
        : [];
    const cache = path.join(fx.root, '.ci', 'cache', 'pins');
    const cmdLogs = fs.existsSync(cache)
      ? fs
          .readdirSync(cache)
          .sort()
          .map((d) => path.join(cache, d, 'commands.log'))
          .filter((f) => fs.existsSync(f))
          .map((f) => fs.readFileSync(f, 'utf-8'))
      : [];
    const files = new Map<string, string>();
    const walk = (dir: string): void => {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        if (['.git', 'bin', 'cache'].includes(e.name)) continue;
        const full = path.join(dir, e.name);
        if (e.isDirectory()) walk(full);
        else files.set(path.relative(fx.root, full), fs.readFileSync(full, 'utf-8'));
      }
    };
    walk(fx.root);
    return {
      status: child.status,
      output: `${child.stdout ?? ''}${child.stderr ?? ''}${cmdLogs.join('\n')}`,
      installs: read(fx.log),
      other: read(`${fx.log}.other`),
      root: fx.root,
      rootManifest: fs.readFileSync(path.join(fx.root, 'package.json'), 'utf-8'),
      syncpackrc: fs.existsSync(path.join(fx.root, '.syncpackrc.json'))
        ? fs.readFileSync(path.join(fx.root, '.syncpackrc.json'), 'utf-8')
        : null,
      files,
    };
  } finally {
    fs.rmSync(fx.root, { recursive: true, force: true });
  }
}

/**
 * Controls: prove this gate can still FAIL, and that its --upgrade path holds a breaking bump in EVERY manifest while still applying the safe ones. Run by `--selftest`.
 */
async function selftest(): Promise<void> {
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

  // 8. END TO END, the real script on a fixture tree with a recording npm stub. The web manifest is CI-shaped: `npm outdated` gives NO `current`, only the lockfile knows it. This is the control for the 2026-09-26 incident: the major must be reported and NOT installed. Since 2026-10-15 a plain bump beside a held major is refused before any write: check:deps judges the whole tree and reds on the held major, so the minor-only run could only fail its own gate (oxc-parser 0.154 beside two minors deadlocked every bump); the minors land with the majors in the one run that names them all.
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
  const bothKeysLine =
    'npm run pins -- bump npm --to private/account/web:vite@8 --to private/account/web:lucide-react@1 --major --reason';
  expect(
    'e2e pins: a plain bump beside held majors is refused before any write, naming the --to line of every held major',
    up.status === 1 && up.installs.length === 0 && up.output.includes(bothKeysLine),
    detail
  );
  expect(
    'e2e pins: the sub-manifest majors are NOT applied',
    !/vite@|lucide-react@/.test(inst),
    detail
  );
  const upMajors = planJsonOf(incident)
    .majors.map((m) => m.key)
    .sort();
  expect(
    'e2e pins: the majors are offered as releases of their own, named by the allow key a `--to` takes',
    upMajors.join() === 'private/account/web:lucide-react@1,private/account/web:vite@8',
    `${upMajors.join()}\n${detail}`
  );
  expect(
    'e2e pins: nothing is installed in the local-only private/growth',
    !inst.includes('growth'),
    detail
  );

  const reason = 'vite 8 is taken with the plugin-react 6 migration in the same change';
  const taken = runFixture(incident, 'upgrade', [
    'bump',
    'npm',
    '--to',
    'private/account/web:vite@8',
    '--major',
    '--reason',
    reason,
  ]);
  expect(
    'e2e pins: naming one of two held majors is refused before any write, with the line naming both',
    taken.status === 1 && taken.installs.length === 0 && taken.output.includes(bothKeysLine),
    `${taken.installs.join('\n')}\n${taken.output}`
  );

  const twoMajors = runFixture(incident, 'upgrade', [
    'bump',
    'npm',
    '--to',
    'private/account/web:vite@8',
    '--to',
    'private/account/web:lucide-react@1',
    '--major',
    '--reason',
    reason,
  ]);
  const bothInst = twoMajors.installs.join('\n');
  expect(
    'e2e pins: several `--to` keys move every named major in ONE transaction, so a family whose majors only converge together is not restored by its first gate',
    twoMajors.status === 0 &&
      /private\/account\/web :: install .*vite@8\.0\.1/.test(bothInst) &&
      /private\/account\/web :: install .*lucide-react@1/.test(bothInst),
    `${bothInst}\n${twoMajors.output}`
  );
  expect(
    'e2e pins: the run that names every held major applies the safe bumps beside them, the sub-manifest minor and the root array-shaped one',
    /<root>\/private\/account\/web :: install .*react-hook-form@7\.89\.0/.test(bothInst) &&
      bothInst.includes('<root> :: install tsx@4.23.15'),
    `${bothInst}\n${twoMajors.output}`
  );
  const comma = runFixture(incident, 'upgrade', [
    'bump',
    'npm',
    '--to',
    'private/account/web:vite@8,private/account/web:lucide-react@1',
    '--major',
    '--reason',
    reason,
  ]);
  expect(
    'e2e pins: a comma list names the same set as repeated `--to`',
    comma.status === 0 && comma.installs.join('\n') === bothInst,
    comma.installs.join('\n')
  );
  const badSet = runFixture(incident, 'upgrade', [
    'bump',
    'npm',
    '--to',
    'private/account/web:vite@8',
    '--to',
    'private/account/web:nope@9',
    '--major',
    '--reason',
    reason,
  ]);
  expect(
    'e2e pins: CONTROL: one unknown key among several refuses the whole run and installs nothing',
    badSet.status === 1 && badSet.installs.length === 0 && badSet.output.includes('nope@9'),
    badSet.output
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

  // 9. UPGRADE VERB AND FAILURE REPORTING, the two 2026-09-30 defects. (a) `npm run -s` exported npm_config_loglevel=silent to the child install, so its ERESOLVE printed nothing and the gate said only "Some upgrades failed". (b) an in-range bump of the pinned typescript-eslint family was planned as `npm install name@ver`, which npm refuses; `npm update` resolves it.
  const ranges: [string | undefined, string, boolean][] = [
    ['^8.70.1', '8.71.0', true],
    ['^4.2.1', '4.2.2', true],
    ['^6.4.2', '8.0.1', false],
    ['^0.3.270', '0.3.283', true],
    ['^0.3.270', '0.4.0', false],
    ['~1.2.3', '1.2.9', true],
    ['~1.2.3', '1.3.0', false],
    ['1.0.0', '1.0.1', false],
    ['*', '9.9.9', true],
    ['^8.70.1', '8.70.0', false],
    ['^1.0.0', '1.1.0-beta.1', false],
    ['file:../shared', '1.0.0', false],
    [undefined, '1.0.0', false],
  ];
  for (const [r, v, want] of ranges) {
    expect(`satisfiesRange(${r}, ${v}) === ${want}`, satisfiesRange(r, v) === want);
  }

  const planRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'check-deps-plan-'));
  try {
    const w = (rel: string, obj: object) => {
      fs.mkdirSync(path.dirname(path.join(planRoot, rel)), { recursive: true });
      fs.writeFileSync(path.join(planRoot, rel), JSON.stringify(obj));
    };
    w('package.json', {
      devDependencies: {
        'typescript-eslint': '^8.70.1',
        '@typescript-eslint/parser': '^8.70.1',
        'eslint-plugin-sonarjs': '^4.2.1',
        pinned: '1.0.0',
        tilded: '~1.2.3',
        vite: '^6.4.2',
        tsx: '^4.21.0',
      },
    });
    w('packages/cli/package.json', { dependencies: { tsx: '^4.22.1' } });
    w('packages/www/package.json', { dependencies: { tsx: '4.22.1' } });
    w('private/account/package.json', { dependencies: { 'react-hook-form': '^7.88.0' } });
    const pk = (name: string, current: string, latest: string): PackageInfo => ({
      name,
      current,
      latest,
    });
    const steps = planInstalls(
      planRoot,
      [
        pk('typescript-eslint', '8.70.1', '8.71.0'),
        pk('@typescript-eslint/parser', '8.70.1', '8.71.0'),
        pk('eslint-plugin-sonarjs', '4.2.1', '4.2.2'),
        pk('pinned', '1.0.0', '1.0.1'),
        pk('tilded', '1.2.3', '1.3.0'),
        { ...pk('vite', '6.4.2', '8.0.1'), allowKey: 'vite@8' },
        pk('tsx', '4.22.1', '4.23.15'),
      ],
      [
        {
          dir: path.join(planRoot, 'private', 'account'),
          name: 'private/account',
          packages: [pk('react-hook-form', '7.88.0', '7.89.0')],
        },
      ]
    );
    const shown = steps.map((s) => `${s.label} :: ${s.args.join(' ')}`).sort();
    const want = [
      'packages/www (install) :: install -w=packages/www --save-exact tsx@4.23.15',
      'private/account (update) :: update react-hook-form',
      'root (install) :: install --save-exact pinned@1.0.1',
      'root (install) :: install tilded@1.3.0 vite@8.0.1',
      'root (update) :: update -w=packages/cli --include-workspace-root tsx typescript-eslint @typescript-eslint/parser eslint-plugin-sonarjs',
    ];
    expect(
      'planner: an in-range bump is `npm update <names>`, ONE call per lockfile covering every workspace and the root, an out-of-range one `npm install name@exact` per manifest, judged per manifest range, in EVERY manifest that declares the package (tsx: root and both workspaces), and an exact pin (pinned, www tsx) installs with --save-exact so it stays exact, while an out-of-range tilde (tilded) installs with the default prefix',
      JSON.stringify(shown) === JSON.stringify(want),
      `got:\n${shown.join('\n')}\nwant:\n${want.join('\n')}`
    );
    // TRANSITIVE FRESHNESS (2026-10-02): every step carries `--before=<cutoff>`, so npm cannot resolve a transitive release the window has not cleared.
    const cutoff = Date.UTC(2026, 9, 1) - 1;
    const dated = planInstalls(
      planRoot,
      [pk('typescript-eslint', '8.70.1', '8.71.0'), pk('pinned', '1.0.0', '1.0.1')],
      [],
      cutoff
    );
    expect(
      'planner: with a release-age window, every npm step ends in --before=<the cutoff>',
      dated.length === 2 &&
        dated.every((st) => st.args[st.args.length - 1] === '--before=2026-09-30T23:59:59.999Z'),
      dated.map((st) => st.args.join(' ')).join('\n')
    );
    expect(
      'planner: CONTROL: without a window no --before is added',
      steps.every((st) => !st.args.some((a) => a.startsWith('--before'))),
      steps.map((st) => st.args.join(' ')).join('\n')
    );
  } finally {
    fs.rmSync(planRoot, { recursive: true, force: true });
  }
  const W = 1440 * 60_000;
  for (const now of [
    Date.UTC(2026, 9, 2, 0, 41),
    Date.UTC(2026, 9, 2, 0, 0),
    Date.UTC(2026, 9, 2, 23, 59, 59, 999),
  ]) {
    const cut = freshnessCutoffMs(now, W) as number;
    expect(
      `freshnessCutoffMs(${new Date(now).toISOString()}) is the newest publish isWithinFreshnessWindow clears, and 1 ms later is deferred`,
      !isWithinFreshnessWindow(cut, now, W) && isWithinFreshnessWindow(cut + 1, now, W),
      `cutoff ${new Date(cut).toISOString()}`
    );
  }
  expect(
    'freshnessCutoffMs: a zero window adds no cutoff',
    freshnessCutoffMs(Date.now(), 0) === null
  );

  const rootLock = {
    'node_modules/typescript-eslint': { version: '8.70.1' },
    'node_modules/fail-me': { version: '1.0.0' },
  };
  const verbCase = (exact: string): FixtureSpec => ({
    outdated: {
      '': {
        'typescript-eslint': { current: '8.70.1', wanted: '8.71.0', latest: '8.71.0' },
        [exact]: { current: '1.0.0', wanted: '1.0.0', latest: '1.0.1' },
      },
      'private/account': {},
    },
    locks: {
      '': { ...rootLock, [`node_modules/${exact}`]: { version: '1.0.0' } },
      'private/account': {},
    },
    // npm update resolves the version the gate judged: the freshness guard must let it through.
    updateLocks: {
      '': { ...rootLock, 'node_modules/typescript-eslint': { version: '8.71.0' } },
    },
    manifests: { '': { devDependencies: { 'typescript-eslint': '^8.70.1', [exact]: '1.0.0' } } },
    env: { npm_config_loglevel: 'silent' },
  });
  const verb = runFixture(verbCase('keep-me'), 'upgrade');
  const verbInst = verb.installs.join('\n');
  const verbDetail = `installs:\n${verbInst}\noutput:\n${verb.output}`;
  expect(
    'e2e pins: PINNED NPM: every install and update ran through `npx -y npm@<NPM_VERSION>`, and the canonical lockfile pass followed under the same pin',
    verb.installs.every((l) => l.endsWith(`via=npm@${FIXTURE_NPM_VERSION}`)) &&
      verb.other.some((l) => l.includes('install --package-lock-only --ignore-scripts')),
    `${verbDetail}\nother:\n${verb.other.join('\n')}`
  );
  expect(
    'e2e pins: the in-range bump runs as `npm update`, the exact-pinned one as `npm install --save-exact name@exact`, so the manifest keeps its exact pin',
    verb.status === 0 &&
      verbInst.includes('<root> :: update typescript-eslint ::') &&
      verbInst.includes('<root> :: install --save-exact keep-me@1.0.1 ::'),
    verbDetail
  );
  expect(
    'e2e pins: a child npm under `npm run -s` does not inherit loglevel=silent (every step passes --loglevel=notice)',
    verb.installs.length === 2 && verb.installs.every((l) => l.includes('loglevel=notice')),
    verbDetail
  );
  const ambient = runFixture(
    { ...verbCase('keep-me'), env: { CHECK_DEPS_MUTANT: 'ambient-npm' } },
    'upgrade'
  );
  expect(
    'e2e pins: CONTROL: the ambient-npm mutant plans a bare `npm`, so the pinned-npm case above goes red',
    ambient.installs.length > 0 &&
      ambient.installs.every((l) => !l.endsWith(`via=npm@${FIXTURE_NPM_VERSION}`)),
    ambient.installs.join('\n')
  );
  const failing = runFixture(verbCase('fail-me'), 'upgrade');
  expect(
    'e2e pins: a failed step is named with its exact command and exit status, the run exits 1, and the tree is back as it was',
    failing.status === 1 &&
      failing.output.includes('step failed (rc=7): root (install)') &&
      failing.output.includes('fixture npm: refusing install --save-exact fail-me@1.0.1') &&
      failing.rootManifest === verb.rootManifest.replace('keep-me', 'fail-me'),
    `${failing.installs.join('\n')}\n${failing.output}`
  );
  expect(
    'e2e pins: CONTROL: an update that resolves exactly the judged version passes the freshness guard',
    !verb.output.includes('did not judge') &&
      verb.output.includes('freshness guard: every updated package resolved to its judged version'),
    verbDetail
  );

  // 10. FRESHNESS-WINDOW GUARD on `npm update`. It takes the highest in-range version, so one published after the release-age check could land unjudged; the step must fail naming it.
  const upStep = (workspace?: string): InstallStep => {
    const packages = [
      { name: 'a', current: '1.0.0', latest: '1.1.0' },
      { name: 'b', current: '2.0.0', latest: '2.0.1' },
    ];
    return {
      cwd: '/x',
      args: ['update', 'a', 'b'],
      label: 'root (update)',
      packages,
      checks: workspace ? packages.map((pkg) => ({ pkg, workspace })) : undefined,
    };
  };
  expect(
    'guard: every package at its judged version passes',
    verifyUpdatedVersions(upStep(), {
      'node_modules/a': { version: '1.1.0' },
      'node_modules/b': { version: '2.0.1' },
    }).length === 0
  );
  const newer = verifyUpdatedVersions(upStep(), {
    'node_modules/a': { version: '1.2.0' },
    'node_modules/b': { version: '2.0.1' },
  });
  expect(
    'guard: a newer-than-judged version is named with both versions',
    newer.length === 1 && newer[0] === 'a: judged 1.1.0, installed 1.2.0',
    newer.join('\n')
  );
  expect(
    'guard: a package missing from the lockfile fails rather than passing unchecked',
    verifyUpdatedVersions(upStep(), { 'node_modules/b': { version: '2.0.1' } }).join() ===
      'a: judged 1.1.0, installed <not in package-lock.json>' &&
      verifyUpdatedVersions(upStep(), null).length === 2
  );
  const wsLock = {
    'node_modules/a': { version: '1.1.0' },
    'packages/cli/node_modules/a': { version: '1.2.0' },
    'node_modules/b': { version: '2.0.1' },
  };
  expect(
    'guard: a workspace step judges the copy npm nested in that workspace, not the hoisted one',
    verifyUpdatedVersions(upStep('packages/cli'), wsLock).join() ===
      'a: judged 1.1.0, installed 1.2.0 (nested in packages/cli)',
    verifyUpdatedVersions(upStep('packages/cli'), wsLock).join()
  );

  const tooNewCase: FixtureSpec = {
    ...verbCase('keep-me'),
    updateLocks: {
      '': { ...rootLock, 'node_modules/typescript-eslint': { version: '8.72.0' } },
    },
  };
  const tooNewRun = runFixture(tooNewCase, 'upgrade');
  expect(
    'e2e pins: an update that resolves a newer-than-judged version fails the run, naming package, both versions and the guard, and the lockfile is restored',
    tooNewRun.status === 1 &&
      tooNewRun.output.includes('step failed (rc=1): freshness guard: root (update)') &&
      tooNewRun.output.includes('`npm update typescript-eslint') &&
      tooNewRun.output.includes('freshness-window guard') &&
      tooNewRun.files.get('package-lock.json') ===
        JSON.stringify({ packages: tooNewCase.locks[''] }) &&
      tooNewRun.output.includes('typescript-eslint: judged 8.71.0, installed 8.72.0'),
    tooNewRun.output
  );

  // 10b. A LOCKSTEP FAMILY MOVES IN ONE CALL PER LOCKFILE (2026-10-02). @vitest/coverage-v8 and @vitest/ui pin an EXACT peer vitest, npm nested copies in several workspaces, and the per-workspace planner ran `npm update -w=packages/cli vitest @vitest/ui`, then `-w=packages/www ...`: each call met the other workspace's pinned copy and failed ERESOLVE. The stub npm refuses exactly that; the split-update mutant restores the old planner and must go red.
  const familyLock = {
    'node_modules/vitest': { version: '5.0.2' },
    'packages/cli/node_modules/@vitest/ui': { version: '5.0.2' },
    'packages/www/node_modules/@vitest/ui': { version: '5.0.2' },
    'node_modules/dotenv': { version: '18.0.4' },
  };
  const familyCase = (env?: NodeJS.ProcessEnv): FixtureSpec => ({
    outdated: {
      '': {
        vitest: { current: '5.0.2', wanted: '5.0.3', latest: '5.0.3' },
        '@vitest/ui': { current: '5.0.2', wanted: '5.0.3', latest: '5.0.3' },
        dotenv: { current: '18.0.4', wanted: '18.0.5', latest: '18.0.5' },
      },
      'private/account': {},
    },
    locks: { '': familyLock, 'private/account': {} },
    updateLocks: {
      '': {
        'node_modules/vitest': { version: '5.0.3' },
        'packages/cli/node_modules/@vitest/ui': { version: '5.0.3' },
        'packages/www/node_modules/@vitest/ui': { version: '5.0.3' },
        'node_modules/dotenv': { version: '18.0.5' },
      },
    },
    manifests: {
      '': {
        workspaces: ['packages/cli', 'packages/www'],
        devDependencies: { dotenv: '^18.0.4' },
      },
      'packages/cli': { devDependencies: { vitest: '^5.0.2', '@vitest/ui': '^5.0.2' } },
      'packages/www': { devDependencies: { vitest: '^5.0.2', '@vitest/ui': '^5.0.2' } },
    },
    lockstep: {
      '': [{ names: ['vitest', '@vitest/ui'], workspaces: ['packages/cli', 'packages/www'] }],
    },
    env,
  });
  const family = runFixture(familyCase(), 'upgrade');
  const familyDetail = `installs:\n${family.installs.join('\n')}\noutput:\n${family.output}`;
  expect(
    'e2e pins: a lockstep family held by two workspaces and the root moves in ONE npm update covering every workspace',
    family.status === 0 &&
      family.installs.length === 1 &&
      family.installs[0].startsWith(
        '<root> :: update -w=packages/cli -w=packages/www --include-workspace-root vitest @vitest/ui dotenv ::'
      ),
    familyDetail
  );
  const split = runFixture(familyCase({ CHECK_DEPS_MUTANT: 'split-update' }), 'upgrade');
  const splitDetail = `installs:\n${split.installs.join('\n')}\noutput:\n${split.output}`;
  expect(
    'e2e pins: CONTROL: the split-update mutant (one npm update per workspace) fails ERESOLVE on the same tree',
    split.status === 1 &&
      split.output.includes('step failed (rc=1): packages/cli (update)') &&
      split.output.includes('ERESOLVE'),
    splitDetail
  );

  // 10c. AN EXACT-PINNING SIBLING MOVES FIRST (2026-10-08). @opentelemetry/sdk-node@0.222.0 pins @opentelemetry/core EXACTLY at 2.11.0, so the in-range `npm update` of core kept 2.11.0 while that sdk-node was installed, and the allow-listed install of sdk-node@0.223.0 that would release the pin ran only after it. The stub npm keeps a pinned package exactly as real npm did (exit 0, old version); the update-first mutant restores the old order and must go red, naming the pinning sibling rather than calling it a freshness breach.
  const otelCore = '@opentelemetry/core';
  const otelNode = '@opentelemetry/sdk-node';
  const otelCase = (over: Partial<FixtureSpec> = {}): FixtureSpec => ({
    outdated: {
      '': {
        [otelCore]: { current: '2.11.0', wanted: '2.12.0', latest: '2.12.0' },
        [otelNode]: { current: '0.222.0', wanted: '0.222.0', latest: '0.223.0' },
      },
      'private/account': {},
    },
    locks: {
      '': {
        [`node_modules/${otelCore}`]: { version: '2.11.0' },
        [`node_modules/${otelNode}`]: {
          version: '0.222.0',
          dependencies: { [otelCore]: '2.11.0' },
        },
      },
      'private/account': {},
    },
    installLocks: {
      '': {
        [`node_modules/${otelNode}`]: {
          version: '0.223.0',
          dependencies: { [otelCore]: '2.12.0' },
        },
      },
    },
    updateLocks: { '': { [`node_modules/${otelCore}`]: { version: '2.12.0' } } },
    manifests: {
      '': { workspaces: ['packages/cli'] },
      'packages/cli': { dependencies: { [otelCore]: '^2.11.0', [otelNode]: '^0.222.0' } },
    },
    allow: {
      [`${otelNode}@0.223`]: 'the 0.223 experimental family is taken with core 2.12 in one change',
    },
    ...over,
  });
  const otelTake = [
    'bump',
    'npm',
    '--to',
    `${otelNode}@0.223`,
    '--major',
    '--reason',
    'the 0.223 experimental family is taken with core 2.12 in one change',
  ];
  const otel = runFixture(otelCase({ allow: {} }), 'upgrade', otelTake);
  const otelDetail = `installs:\n${otel.installs.join('\n')}\noutput:\n${otel.output}`;
  expect(
    'e2e pins: the major sibling that pins an in-range package exactly is installed BEFORE the npm update of its lockfile, and the update lands the judged version',
    otel.status === 0 &&
      otel.installs.length === 2 &&
      otel.installs[0].startsWith(`<root> :: install -w=packages/cli ${otelNode}@0.223.0 ::`) &&
      otel.installs[1].startsWith(`<root> :: update -w=packages/cli ${otelCore} ::`),
    otelDetail
  );
  const updFirst = runFixture(
    otelCase({ allow: {}, env: { CHECK_DEPS_MUTANT: 'update-first' } }),
    'upgrade',
    otelTake
  );
  const updFirstDetail = `installs:\n${updFirst.installs.join('\n')}\noutput:\n${updFirst.output}`;
  expect(
    'e2e pins: CONTROL: the update-first mutant (every update before the installs) leaves core on the pinned 2.11.0 and fails, naming the pinning sibling',
    updFirst.status === 1 &&
      updFirst.installs.length === 1 &&
      updFirst.installs[0].startsWith(`<root> :: update -w=packages/cli ${otelCore} ::`) &&
      updFirst.output.includes(
        `${otelCore}: judged 2.12.0, installed 2.11.0; held back by ${otelNode}@0.222.0 requires "2.11.0"`
      ) &&
      updFirst.output.includes('below the judged version') &&
      !updFirst.output.includes('freshness-window guard'),
    updFirstDetail
  );
  // Without the allow entry the sibling is a held major. Since 2026-10-15 the plain bump is refused before any write rather than run into the held-back update: the sibling is held, so check:deps stays red whatever the update does, and the refusal names the --to line that takes it (the guard's held-back wording stays covered by pinningHolders and updateMismatches below).
  const heldSib = runFixture(otelCase({ allow: {} }), 'upgrade');
  const heldSibDetail = `installs:\n${heldSib.installs.join('\n')}\noutput:\n${heldSib.output}`;
  expect(
    'e2e pins: with the pinning sibling held, the plain bump is refused before any write, naming the --to line that takes the sibling',
    heldSib.status === 1 &&
      heldSib.installs.length === 0 &&
      heldSib.output.includes(`npm run pins -- bump npm --to ${otelNode}@0.223 --major --reason`),
    heldSibDetail
  );
  // 10d. A PEER FAMILY RIDES THE INSTALL (2026-10-22). @opentelemetry/core@3 peer-requires @opentelemetry/api >=1.10 while the in-range api bump 1.9.1 -> 1.10.0 waited for the later `npm update`, so the install failed ERESOLVE in private/account. The stub refuses `install core@3` unless the same call names api@1.10.0; the peer-split mutant restores the old planner and must go red. The fold rule is the TARGET version's declared peer range (read from the registry document) against the in-range package's current version, so 10d also covers a minor bump that raises a peer floor, a same-scope sibling that is not a peer, and a 0.x sibling with no unmet peer, each staying on or leaving the update as the range says.
  const otelApi = '@opentelemetry/api';
  const peerCase = (env?: NodeJS.ProcessEnv): FixtureSpec => ({
    outdated: {
      '': {
        [otelApi]: { current: '1.9.1', wanted: '1.10.0', latest: '1.10.0' },
        [otelCore]: { current: '2.12.0', wanted: '2.12.0', latest: '3.0.0' },
        dotenv: { current: '18.0.4', wanted: '18.0.5', latest: '18.0.5' },
      },
      'private/account': {},
    },
    locks: {
      '': {
        [`node_modules/${otelApi}`]: { version: '1.9.1' },
        [`node_modules/${otelCore}`]: { version: '2.12.0' },
        'node_modules/dotenv': { version: '18.0.4' },
      },
      'private/account': {},
    },
    installLocks: {
      '': {
        [`node_modules/${otelApi}`]: { version: '1.10.0' },
        [`node_modules/${otelCore}`]: { version: '3.0.0' },
      },
    },
    updateLocks: { '': { 'node_modules/dotenv': { version: '18.0.5' } } },
    installPeers: { '': [{ spec: `${otelCore}@3.0.0`, needs: `${otelApi}@1.10.0` }] },
    registry: {
      [otelCore]: {
        versions: { '3.0.0': { peerDependencies: { [otelApi]: '>=1.10.0 <1.11.0' } } },
      },
    },
    manifests: {
      '': { workspaces: ['packages/cli'] },
      'packages/cli': {
        dependencies: { [otelApi]: '^1.9.1', [otelCore]: '^2.12.0', dotenv: '^18.0.4' },
      },
    },
    env,
  });
  const peerTake = [
    'bump',
    'npm',
    '--to',
    `${otelCore}@3`,
    '--major',
    '--reason',
    'core 3 is taken with the api 1.10 it peer-requires in one change',
  ];
  const peer = runFixture(peerCase(), 'upgrade', peerTake);
  const peerDetail = `installs:\n${peer.installs.join('\n')}\noutput:\n${peer.output}`;
  expect(
    'e2e pins: an in-range peer sibling of an out-of-range install rides the SAME npm install; an unrelated in-range package still goes through the npm update',
    peer.status === 0 &&
      peer.installs.length === 2 &&
      peer.installs[0].startsWith(
        `<root> :: install -w=packages/cli ${otelCore}@3.0.0 ${otelApi}@1.10.0 ::`
      ) &&
      peer.installs[1].startsWith('<root> :: update -w=packages/cli dotenv ::'),
    peerDetail
  );
  const peerSplit = runFixture(peerCase({ CHECK_DEPS_MUTANT: 'peer-split' }), 'upgrade', peerTake);
  const peerSplitDetail = `installs:\n${peerSplit.installs.join('\n')}\noutput:\n${peerSplit.output}`;
  expect(
    'e2e pins: CONTROL: the peer-split mutant (the in-range peer waits for the update) fails the install with ERESOLVE',
    peerSplit.status === 1 && peerSplit.output.includes('ERESOLVE'),
    peerSplitDetail
  );
  // (a) A same-major MINOR bump can raise a peer floor too: core ~2.11 -> 2.12.0 (out of range of the tilde) peer-requires api >=1.10, so the sibling folds although no major changes.
  const minorPeerCase = (env?: NodeJS.ProcessEnv): FixtureSpec => ({
    ...peerCase(env),
    outdated: {
      '': {
        [otelApi]: { current: '1.9.1', wanted: '1.10.0', latest: '1.10.0' },
        [otelCore]: { current: '2.11.0', wanted: '2.11.0', latest: '2.12.0' },
      },
      'private/account': {},
    },
    locks: {
      '': {
        [`node_modules/${otelApi}`]: { version: '1.9.1' },
        [`node_modules/${otelCore}`]: { version: '2.11.0' },
      },
      'private/account': {},
    },
    installLocks: {
      '': {
        [`node_modules/${otelApi}`]: { version: '1.10.0' },
        [`node_modules/${otelCore}`]: { version: '2.12.0' },
      },
    },
    updateLocks: undefined,
    installPeers: { '': [{ spec: `${otelCore}@2.12.0`, needs: `${otelApi}@1.10.0` }] },
    registry: {
      [otelCore]: {
        versions: { '2.12.0': { peerDependencies: { [otelApi]: '>=1.10.0 <1.11.0' } } },
      },
    },
    manifests: {
      '': { workspaces: ['packages/cli'] },
      'packages/cli': { dependencies: { [otelApi]: '^1.9.1', [otelCore]: '~2.11.0' } },
    },
  });
  const minorPeer = runFixture(minorPeerCase(), 'upgrade');
  const minorPeerDetail = `installs:\n${minorPeer.installs.join('\n')}\noutput:\n${minorPeer.output}`;
  expect(
    'e2e pins: a same-major minor bump whose target raises a peer floor folds the unmet in-range peer into the SAME npm install',
    minorPeer.status === 0 &&
      minorPeer.installs.length === 1 &&
      minorPeer.installs[0].startsWith(
        `<root> :: install -w=packages/cli ${otelCore}@2.12.0 ${otelApi}@1.10.0 ::`
      ),
    minorPeerDetail
  );
  const minorPeerSplit = runFixture(minorPeerCase({ CHECK_DEPS_MUTANT: 'peer-split' }), 'upgrade');
  expect(
    'e2e pins: CONTROL: the peer-split mutant fails the minor-bump install with ERESOLVE',
    minorPeerSplit.status === 1 && minorPeerSplit.output.includes('ERESOLVE'),
    `installs:\n${minorPeerSplit.installs.join('\n')}\noutput:\n${minorPeerSplit.output}`
  );
  // (b) A same-scope in-range sibling the target does NOT name as a peer stays on the update (a pinned-family member installed by name would fail where `npm update` succeeds).
  const semconv = '@opentelemetry/semantic-conventions';
  const siblingBase = peerCase();
  const sibling = runFixture(
    {
      ...siblingBase,
      outdated: {
        '': {
          ...siblingBase.outdated[''],
          [semconv]: { current: '1.40.0', wanted: '1.41.0', latest: '1.41.0' },
        },
        'private/account': {},
      },
      locks: {
        '': { ...siblingBase.locks[''], [`node_modules/${semconv}`]: { version: '1.40.0' } },
        'private/account': {},
      },
      updateLocks: {
        '': {
          'node_modules/dotenv': { version: '18.0.5' },
          [`node_modules/${semconv}`]: { version: '1.41.0' },
        },
      },
      manifests: {
        '': { workspaces: ['packages/cli'] },
        'packages/cli': {
          dependencies: {
            [otelApi]: '^1.9.1',
            [otelCore]: '^2.12.0',
            dotenv: '^18.0.4',
            [semconv]: '^1.40.0',
          },
        },
      },
    },
    'upgrade',
    peerTake
  );
  expect(
    'e2e pins: a same-scope in-range sibling that no out-of-range target names as a peer stays on the npm update',
    sibling.status === 0 &&
      sibling.installs.length === 2 &&
      sibling.installs[0].startsWith(
        `<root> :: install -w=packages/cli ${otelCore}@3.0.0 ${otelApi}@1.10.0 ::`
      ) &&
      !sibling.installs[0].includes(semconv) &&
      sibling.installs[1].includes(` ${semconv}`) &&
      sibling.installs[1].includes(' dotenv'),
    `installs:\n${sibling.installs.join('\n')}\noutput:\n${sibling.output}`
  );
  // (c) A 0.x minor (sdk-node 0.222 -> 0.223) with no unmet peer keeps every in-range sibling on the update: api 1.9.1 satisfies the sdk's declared peer range.
  const zeroBase = otelCase({ allow: {} });
  const zeroX = runFixture(
    {
      ...zeroBase,
      outdated: {
        '': {
          ...zeroBase.outdated[''],
          [otelApi]: { current: '1.9.1', wanted: '1.10.0', latest: '1.10.0' },
        },
        'private/account': {},
      },
      locks: {
        '': { ...zeroBase.locks[''], [`node_modules/${otelApi}`]: { version: '1.9.1' } },
        'private/account': {},
      },
      updateLocks: {
        '': {
          ...zeroBase.updateLocks?.[''],
          [`node_modules/${otelApi}`]: { version: '1.10.0' },
        },
      },
      registry: {
        [otelNode]: {
          versions: { '0.223.0': { peerDependencies: { [otelApi]: '>=1.3.0 <2.0.0' } } },
        },
      },
      manifests: {
        '': { workspaces: ['packages/cli'] },
        'packages/cli': {
          dependencies: { [otelCore]: '^2.11.0', [otelNode]: '^0.222.0', [otelApi]: '^1.9.1' },
        },
      },
    },
    'upgrade',
    otelTake
  );
  expect(
    'e2e pins: a 0.x minor whose peer ranges its siblings already satisfy leaves them on the npm update',
    zeroX.status === 0 &&
      zeroX.installs.length === 2 &&
      zeroX.installs[0].startsWith(`<root> :: install -w=packages/cli ${otelNode}@0.223.0 ::`) &&
      !zeroX.installs[0].includes(otelApi) &&
      !zeroX.installs[0].includes(otelCore) &&
      zeroX.installs[1].includes(` ${otelApi}`) &&
      zeroX.installs[1].includes(` ${otelCore}`),
    `installs:\n${zeroX.installs.join('\n')}\noutput:\n${zeroX.output}`
  );
  const realPeer: NodeJS.ProcessEnv = { ...process.env, CHECK_DEPS_MUTANT: 'peer-split' };
  delete realPeer.CHECK_DEPS_ROOT;
  delete realPeer.CHECK_DEPS_FORCE_PROBE_FAILURE;
  const realPeerRun = spawnSync(process.execPath, [...process.execArgv, process.argv[1]], {
    cwd: CONSOLE_ROOT,
    encoding: 'utf-8',
    env: realPeer,
  });
  expect(
    'mutant: CONTROL: peer-split without CHECK_DEPS_ROOT is refused',
    realPeerRun.status === 1 &&
      `${realPeerRun.stdout}${realPeerRun.stderr}`.includes('CHECK_DEPS_MUTANT=peer-split refused'),
    `${realPeerRun.stdout}${realPeerRun.stderr}`
  );
  const pinLock: Record<string, LockEntry> = {
    'node_modules/core': { version: '2.11.0' },
    'node_modules/exact': { version: '0.222.0', dependencies: { core: '2.11.0' } },
    'node_modules/caret': { version: '1.0.0', dependencies: { core: '^2.11.0' } },
    'packages/cli/node_modules/peer': { version: '3.0.0', peerDependencies: { core: '~2.11.0' } },
  };
  expect(
    'guard: pinningHolders names every copy whose range admits the kept version but not the judged one, and never a caret range that admits both',
    pinningHolders(pinLock, 'core', '2.11.0', '2.12.0').join() ===
      'exact@0.222.0 requires "2.11.0",peer@3.0.0 requires "~2.11.0"',
    pinningHolders(pinLock, 'core', '2.11.0', '2.12.0').join('\n')
  );
  expect(
    'guard: CONTROL: a newer-than-judged version is a freshness breach, never a held-back package',
    updateMismatches(
      {
        cwd: '/x',
        args: ['update', 'core'],
        label: 'root (update)',
        packages: [{ name: 'core', current: '2.11.0', latest: '2.12.0' }],
      },
      { ...pinLock, 'node_modules/core': { version: '2.13.0' } }
    ).every((m) => !m.held)
  );
  const realUpd: NodeJS.ProcessEnv = { ...process.env, CHECK_DEPS_MUTANT: 'update-first' };
  delete realUpd.CHECK_DEPS_ROOT;
  delete realUpd.CHECK_DEPS_FORCE_PROBE_FAILURE;
  const realUpdRun = spawnSync(process.execPath, [...process.execArgv, process.argv[1]], {
    cwd: CONSOLE_ROOT,
    encoding: 'utf-8',
    env: realUpd,
  });
  expect(
    'mutant: CONTROL: update-first without CHECK_DEPS_ROOT is refused',
    realUpdRun.status === 1 &&
      `${realUpdRun.stdout}${realUpdRun.stderr}`.includes('CHECK_DEPS_MUTANT=update-first refused'),
    `${realUpdRun.stdout}${realUpdRun.stderr}`
  );

  // 11. THE HELD-MAJOR CLOCK (operator ruling 2026-10-01). A blocklisted major used to be excused forever; it now fails 90 days after the first release of its clock line unless an exception excuses it. Each case has its control, and the mutant proves the 91-day control depends on the clock rather than failing for another reason.
  const ago = (days: number) => new Date(Date.now() - days * DAY_MS).toISOString();
  const dateIn = (days: number) => isoDate(utcDay(Date.now()) + days * DAY_MS);
  const doc = (
    latest: string,
    versions: Record<
      string,
      { daysAgo: number; deprecated?: string; peer?: Record<string, string> }
    >
  ): Packument => ({
    'dist-tags': { latest },
    versions: Object.fromEntries(
      Object.entries(versions).map(([v, o]) => [
        v,
        { ...(o.deprecated ? { deprecated: o.deprecated } : {}), peerDependencies: o.peer },
      ])
    ),
    time: Object.fromEntries(Object.entries(versions).map(([v, o]) => [v, ago(o.daysAgo)])),
  });
  const widgetBlock =
    'widget  # BLOCKER: widget 2 rewrites its plugin API, so it needs a coordinated migration of every plugin\n';
  const widgetDoc = (firstDays: number) =>
    doc('2.4.1', {
      '1.2.0': { daysAgo: 400 },
      '2.0.0': { daysAgo: firstDays },
      '2.4.1': { daysAgo: 5 },
    });
  const clockCase = (over: Partial<FixtureSpec> = {}): FixtureSpec => ({
    outdated: {
      '': { widget: { current: '1.2.0', wanted: '1.2.0', latest: '2.4.1' } },
      'private/account': {},
    },
    locks: { '': { 'node_modules/widget': { version: '1.2.0' } }, 'private/account': {} },
    blocklist: widgetBlock,
    registry: { widget: widgetDoc(91) },
    ...over,
  });
  const goodReason =
    'widget 2 needs the plugin API migration, which is scheduled with the lint-tooling change';
  const run = (spec: FixtureSpec) => {
    const r = runFixture(spec, 'check');
    return { ...r, detail: r.output };
  };

  // Test 1: 89 days warns and passes; 91 days fails naming package and manifest.
  const at89 = run(clockCase({ registry: { widget: widgetDoc(89) } }));
  expect(
    'clock: a blocklisted major at 89 days passes and warns with its deadline',
    at89.status === 0 &&
      at89.output.includes(
        'Held major aging: widget 1.2.0 -> 2.4.1 (root): line 2 first released'
      ) &&
      at89.output.includes('(2.0.0), 89 days ago. Deadline'),
    at89.detail
  );
  const at91 = run(clockCase());
  expect(
    'clock: CONTROL: the same hold at 91 days fails, naming package and manifest',
    at91.status === 1 &&
      at91.output.includes('✗ Held major past 90 days: widget 1.2.0 -> 2.4.1 (root)') &&
      at91.output.includes('npm run pins -- bump npm --to widget@2 --major --reason'),
    at91.detail
  );

  // Test 2: the age is the line's first release, not the latest patch, and a deprecated X.0.0 is skipped.
  const fromX00 = run(clockCase({ registry: { widget: widgetDoc(120) } }));
  expect(
    'clock: X.0.0 at 120 days with X.4.1 at 5 days fails (age is from X.0.0)',
    fromX00.status === 1 && fromX00.output.includes('(2.0.0), 120 days ago'),
    fromX00.detail
  );
  const young = run(clockCase({ registry: { widget: widgetDoc(30) } }));
  expect(
    'clock: CONTROL: X.0.0 at 30 days is silent',
    young.status === 0 && !young.output.includes('Held major'),
    young.detail
  );
  const deprecatedFirst = run(
    clockCase({
      registry: {
        widget: doc('2.4.1', {
          '1.2.0': { daysAgo: 900 },
          '2.0.0': { daysAgo: 800, deprecated: 'This version should not be used.' },
          '2.0.1': { daysAgo: 30 },
          '2.4.1': { daysAgo: 5 },
        }),
      },
    })
  );
  expect(
    'clock: a deprecated X.0.0 at 800 days is skipped; the line starts at X.0.1 (30 days, silent)',
    deprecatedFirst.status === 0 && !deprecatedFirst.output.includes('Held major'),
    deprecatedFirst.detail
  );

  // Test 3: peer-range and engine-floor blockers, live and lifted.
  const peerEx = {
    widget: {
      owner: 'd778be9d',
      reason: goodReason,
      blocker: { kind: 'peer-range', package: 'widget-lint', peer: 'widget', excludes: '2' },
    },
  };
  const peerLive = run(
    clockCase({
      exceptions: peerEx,
      registry: {
        widget: widgetDoc(91),
        'widget-lint': doc('3.0.0', {
          '3.0.0': { daysAgo: 50, peer: { widget: '>=1.0.0 <2.0.0' } },
        }),
      },
    })
  );
  expect(
    'clock: a live peer-range exception excuses the 91-day hold and prints the excused line',
    peerLive.status === 0 &&
      peerLive.output.includes(
        '  widget (root), 91 days: excused by deps-major-exceptions.json "widget" (owner d778be9d): peer-range: widget-lint@3.0.0 declares peer widget ">=1.0.0 <2.0.0"'
      ),
    peerLive.detail
  );
  const peerLifted = run(
    clockCase({
      exceptions: peerEx,
      registry: {
        widget: widgetDoc(91),
        'widget-lint': doc('3.1.0', {
          '3.0.0': { daysAgo: 50, peer: { widget: '>=1.0.0 <2.0.0' } },
          '3.1.0': { daysAgo: 3, peer: { widget: '^1 || ^2' } },
        }),
      },
    })
  );
  expect(
    'clock: CONTROL: once the newest peer admits the line, the exception is stale and fails',
    peerLifted.status === 1 &&
      peerLifted.output.includes(
        '"widget": blocker lifted: widget-lint@3.1.0 declares peer widget "^1 || ^2", which admits widget@2.0.0. Delete the entry.'
      ),
    peerLifted.detail
  );
  const nodeCase = (engines: string): FixtureSpec =>
    clockCase({
      outdated: {
        '': { '@types/node': { current: '22.20.0', wanted: '22.20.0', latest: '26.6.3' } },
        'private/account': {},
      },
      locks: { '': { 'node_modules/@types/node': { version: '22.20.0' } }, 'private/account': {} },
      blocklist:
        '@types/node  # BLOCKER: the types must match the Node engine floor, which is Node 22 in this fixture\n',
      manifests: { '': { engines: { node: engines } } },
      registry: {
        '@types/node': doc('26.6.3', {
          '22.20.0': { daysAgo: 500 },
          '24.0.0': { daysAgo: 477 },
          '26.6.3': { daysAgo: 2 },
        }),
      },
      exceptions: {
        '@types/node': {
          owner: 'd778be9d',
          reason: 'the Node engine floor is 22, so the types for Node 24 APIs would lie',
          blocker: { kind: 'engine-floor', engine: 'node' },
        },
      },
    });
  const engLive = run(nodeCase('>=22.13.0'));
  expect(
    'clock: a live engine-floor exception excuses a 477-day hold (line 24: 23 was never published)',
    engLive.status === 0 &&
      engLive.output.includes(
        '  @types/node (root), 477 days: excused by deps-major-exceptions.json "@types/node" (owner d778be9d): engine-floor: engines.node ">=22.13.0"'
      ),
    engLive.detail
  );
  const engLifted = run(nodeCase('>=24'));
  expect(
    'clock: CONTROL: engines.node >=24 lifts the engine-floor blocker and the entry fails as stale',
    engLifted.status === 1 &&
      engLifted.output.includes(
        'blocker lifted: package.json engines.node ">=24" now admits 24.x. Delete the entry.'
      ),
    engLifted.detail
  );

  // Test 4 and 5: expiry limits and incomplete entries.
  const exCase = (entry: Record<string, unknown>) => clockCase({ exceptions: { widget: entry } });
  const expired = run(exCase({ owner: 'd778be9d', reason: goodReason, expires: dateIn(-1) }));
  expect(
    'exceptions: one that expired yesterday fails',
    expired.status === 1 && expired.output.includes(`expired on ${dateIn(-1)}`),
    expired.detail
  );
  const plus10 = run(exCase({ owner: 'd778be9d', reason: goodReason, expires: dateIn(10) }));
  expect(
    'exceptions: CONTROL: a complete entry expiring in 10 days excuses the hold',
    plus10.status === 0 && plus10.output.includes(`(owner d778be9d): expires ${dateIn(10)}`),
    plus10.detail
  );
  const plus45 = run(exCase({ owner: 'd778be9d', reason: goodReason, expires: dateIn(45) }));
  expect(
    'exceptions: CONTROL: 45 days out is refused (the limit is 30)',
    plus45.status === 1 && plus45.output.includes('is 45 days out; the limit is 30'),
    plus45.detail
  );
  for (const [label, entry, want] of [
    ['missing owner', { reason: goodReason, expires: dateIn(10) }, '"widget": no owner'],
    ['missing reason', { owner: 'd778be9d', expires: dateIn(10) }, '"widget": no reason'],
    [
      'free-text-only',
      { owner: 'd778be9d', reason: goodReason },
      '"widget": free-text-only entries are refused',
    ],
  ] as const) {
    const r = run(exCase(entry));
    expect(
      `exceptions: ${label} is refused with its own message`,
      r.status === 1 && r.output.includes(want),
      r.detail
    );
  }
  expect(
    'exceptions: a low-quality reason goes through the canonical validator and is refused',
    parseMajorExceptions(
      JSON.stringify({ exceptions: { widget: { owner: 'abc', reason: 'x', expires: dateIn(1) } } }),
      Date.now()
    ).problems.length === 0 && validateBlockerQuality('widget', 'x', MAJOR_EXCEPTIONS_REL) !== null
  );
  expect(
    'exceptions: an entry with both blocker and expires is refused, and so is an unknown kind',
    parseMajorExceptions(
      JSON.stringify({
        exceptions: {
          a: {
            owner: 'abc',
            reason: goodReason,
            expires: dateIn(1),
            blocker: { kind: 'engine-floor', engine: 'node' },
          },
          b: { owner: 'abc', reason: goodReason, blocker: { kind: 'vibes' } },
        },
      }),
      Date.now()
    ).problems.length === 2
  );

  // Test 6: under 60 days, nothing is printed (case 1's 89-day run is the control that does print).
  expect(
    'clock: a 30-day hold prints no aging text',
    young.status === 0 && !young.output.includes('aging'),
    young.detail
  );

  // Test 7: the mutant. Ignoring the clock turns the 91-day control green, so that control depends on the clock; and the seam is refused on a real tree.
  const mutant = run(clockCase({ env: { CHECK_DEPS_MUTANT: 'ignore-clock' } }));
  expect(
    'mutant: CHECK_DEPS_MUTANT=ignore-clock turns the 91-day control green (the control depends on the clock)',
    mutant.status === 0 && !mutant.output.includes('Held major past'),
    mutant.detail
  );
  const realEnv: NodeJS.ProcessEnv = { ...process.env, CHECK_DEPS_MUTANT: 'ignore-clock' };
  delete realEnv.CHECK_DEPS_ROOT;
  delete realEnv.CHECK_DEPS_FORCE_PROBE_FAILURE;
  const realMutant = spawnSync(process.execPath, [...process.execArgv, process.argv[1]], {
    cwd: CONSOLE_ROOT,
    encoding: 'utf-8',
    env: realEnv,
  });
  expect(
    'mutant: CONTROL: the same seam without CHECK_DEPS_ROOT is refused',
    realMutant.status === 1 &&
      `${realMutant.stdout}${realMutant.stderr}`.includes('CHECK_DEPS_MUTANT=ignore-clock refused'),
    `${realMutant.stdout}${realMutant.stderr}`
  );

  // Test 8: scope. A scoped exception does not reach the root's hold of the same package; a bare one excuses both.
  const viteDoc = doc('8.3.1', {
    '6.4.2': { daysAgo: 600 },
    '7.0.0': { daysAgo: 463 },
    '8.3.1': { daysAgo: 4 },
  });
  const viteHold = { vite: { current: '6.4.2', wanted: '6.4.2', latest: '8.3.1' } };
  const scopeCase = (key: string): FixtureSpec => ({
    outdated: { '': viteHold, 'private/account': {}, 'private/account/web': viteHold },
    locks: {
      '': { 'node_modules/vite': { version: '6.4.2' } },
      'private/account': {},
      'private/account/web': { 'node_modules/vite': { version: '6.4.2' } },
    },
    blocklist:
      'vite  # BLOCKER: vite 8 changes the bundler, so the build migrates as one dedicated change\n',
    registry: { vite: viteDoc },
    exceptions: { [key]: { owner: 'd778be9d', reason: goodReason, expires: dateIn(10) } },
  });
  const scoped = run(scopeCase('private/account/web:vite'));
  expect(
    'scope: a private/account/web:vite exception excuses only that manifest; the root hold still fails',
    scoped.status === 1 &&
      scoped.output.includes('✗ Held major past 90 days: vite 6.4.2 -> 8.3.1 (root)') &&
      scoped.output.includes('  vite (private/account/web), 463 days: excused'),
    scoped.detail
  );
  const bare = run(scopeCase('vite'));
  expect(
    'scope: CONTROL: a bare key excuses both',
    bare.status === 0 &&
      bare.output.includes('  vite (root), 463 days: excused') &&
      bare.output.includes('  vite (private/account/web), 463 days: excused'),
    bare.detail
  );

  // Test 9: cannot date, dead key, no blocklist line, and an allowed major never reaching the clock.
  const noDoc = run(clockCase({ registry: {} }));
  expect(
    'clock: a held major with no registry document is CANNOT DATE and fails',
    noDoc.status === 1 && noDoc.output.includes('✗ cannot date held major widget (root)'),
    noDoc.detail
  );
  const noLine = run(
    clockCase({
      registry: {
        widget: doc('2.4.1', {
          '1.2.0': { daysAgo: 400 },
          '2.4.1': { daysAgo: 300, deprecated: 'no' },
        }),
      },
    })
  );
  expect(
    'clock: a document with no stable, non-deprecated release past current is CANNOT DATE',
    noLine.status === 1 &&
      noLine.output.includes(
        '✗ cannot date held major widget (root): no stable, non-deprecated release'
      ),
    noLine.detail
  );
  const dead = run(
    clockCase({
      blocklist: `${widgetBlock}gizmo  # BLOCKER: gizmo 3 drops the CommonJS build this fixture still loads\n`,
      registry: { widget: widgetDoc(30) },
      exceptions: { gizmo: { owner: 'd778be9d', reason: goodReason, expires: dateIn(10) } },
    })
  );
  expect(
    'exceptions: an entry that matches no blocklist-held major is dead and fails',
    dead.status === 1 &&
      dead.output.includes(
        '"gizmo": excuses nothing in this run (no blocklist-held major matches). Delete the entry.'
      ),
    dead.detail
  );
  const orphan = run(
    clockCase({
      exceptions: { gizmo: { owner: 'd778be9d', reason: goodReason, expires: dateIn(10) } },
    })
  );
  expect(
    'exceptions: an entry with no blocklist line is refused',
    orphan.status === 1 &&
      orphan.output.includes('"gizmo": no matching line in .ci/policy/.deps-upgrade-blocklist'),
    orphan.detail
  );
  const allowedMajor = run(
    clockCase({ blocklist: '# none\n', registry: {}, allow: { 'widget@2': goodReason } })
  );
  expect(
    'clock: an allowed major is must-upgrade and never reaches the clock (no CANNOT DATE without a document)',
    allowedMajor.status === 1 &&
      allowedMajor.output.includes('must upgrade') &&
      !allowedMajor.output.includes('cannot date') &&
      !allowedMajor.output.includes('Held major'),
    allowedMajor.detail
  );

  // Test 10: the range evaluator, pure.
  const admitsLine = (range: string, versions: string[], line: string) => {
    const sets = parseRange(range);
    return sets ? versions.some((v) => releaseLine(v) === line && rangeAdmits(sets, v)) : null;
  };
  const rangeCases: [string, string[], string, boolean][] = [
    ['>=4.8.4 <6.1.0', ['6.0.3', '7.0.2'], '7', false],
    ['>=4.8.4 <6.1.0', ['6.0.3', '7.0.2'], '6', true],
    ['^3 || ^9', ['9.39.4', '10.0.1', '10.11.0'], '10', false],
    ['^3 || ^9', ['9.39.4', '10.0.1'], '9', true],
    ['^9.7', ['9.6.0', '10.0.0'], '9', false],
    ['^9.7', ['9.8.0', '10.0.0'], '9', true],
    ['^9.7', ['10.0.0'], '10', false],
    ['>=10.4', ['10.3.0'], '10', false],
    ['>=10.4', ['10.3.0', '10.4.0'], '10', true],
    ['^2 || ^3 || ^4 || ^5 || ^6 || ^7.2.0 || ^8 || ^9', ['10.0.0', '10.11.0'], '10', false],
    ['^0.3', ['0.3.9', '0.4.0'], '0.4', false],
    ['~1.2', ['1.2.7', '1.3.0'], '1', true],
    ['>= 1.x', ['1.0.0'], '1', true],
  ];
  for (const [r, vs, l, want] of rangeCases) {
    expect(`range: "${r}" admits line ${l} of [${vs}] === ${want}`, admitsLine(r, vs, l) === want);
  }
  for (const bad of ['1.0.0 - 2.0.0', 'latest', 'git+https://x/y.git', '>=1.0.0 <foo']) {
    expect(`range: "${bad}" is refused, not passed`, parseRange(bad) === null);
  }
  expect(
    'range: the engine floor is the lowest lower bound across alternatives',
    rangeFloorMajor(parseRange('>=22.13.0') ?? []) === 22 &&
      rangeFloorMajor(parseRange('^20 || >=22') ?? []) === 20 &&
      rangeFloorMajor(parseRange('<30') ?? []) === 0
  );

  // 11. AN UNINSTALLED MANIFEST IS NOT A CLEAN ONE (worklist #1feb4717, 2026-10-01). `npm outdated` reads the installed tree whatever flag it is given, and skips every devDependency, optionalDependency and peerDependency that is not on disk (npm 11.20.0, lib/commands/outdated.js: "deps different from prod not currently on disk are not included in the output"). So private/account/web with no node_modules reported `{}` for its typescript, the hold vanished, and the gate told the reader to delete a valid exception. The fixture is that shape: npm reports nothing, the lockfile pins 6.0.3, the registry has 7.0.2.
  const tsDoc = doc('7.0.2', {
    '6.0.3': { daysAgo: 300 },
    '7.0.2': { daysAgo: 120 },
  });
  const tsReason =
    'the web lint chain declares peer typescript below 7, so the web build stays on 6 until it moves';
  const devCase = (over: Partial<FixtureSpec> = {}): FixtureSpec => ({
    outdated: { '': {}, 'private/account': {}, 'private/account/web': {} },
    locks: {
      '': {},
      'private/account': {},
      'private/account/web': { 'node_modules/typescript': { version: '6.0.3' } },
    },
    manifests: {
      'private/account/web': {
        devDependencies: {
          typescript: '^6.0.3',
          '@rediacc/shared': 'file:../../../packages/shared',
        },
      },
    },
    blocklist:
      'typescript  # BLOCKER: the web lint chain declares peer typescript below 7, so it stays on 6\n',
    registry: { typescript: tsDoc },
    exceptions: {
      'private/account/web:typescript': {
        owner: 'd778be9d',
        reason: tsReason,
        expires: dateIn(10),
      },
    },
    ...over,
  });
  const uninstalled = run(devCase());
  expect(
    'uninstalled: a devDependency npm cannot see is judged from the lockfile and registry, so its exception excuses a real hold',
    uninstalled.status === 0 &&
      uninstalled.output.includes('  typescript (private/account/web), 120 days: excused') &&
      !uninstalled.output.includes('excuses nothing') &&
      uninstalled.output.includes(
        '1 uninstalled dependency(ies) judged from lockfile and registry'
      ),
    uninstalled.detail
  );
  const installedDev = run(
    devCase({
      files: { 'private/account/web/node_modules/typescript/package.json': '{"version":"7.0.2"}' },
    })
  );
  expect(
    'uninstalled: CONTROL: the same devDependency ON DISK is left to npm (whose `{}` then means current), so the exception is dead',
    installedDev.status === 1 &&
      installedDev.output.includes(
        '"private/account/web:typescript": excuses nothing in this run (no blocklist-held major matches). Delete the entry.'
      ) &&
      installedDev.output.includes('0 uninstalled dependency(ies) judged'),
    installedDev.detail
  );
  const noRegistry = run(devCase({ registry: {} }));
  expect(
    'uninstalled: an uninstalled devDependency the registry cannot answer for is refused as unjudged, never passed',
    noRegistry.status === 1 &&
      noRegistry.output.includes(
        'typescript (private/account/web): not installed, so npm outdated skips it, and the registry returned no document'
      ) &&
      !noRegistry.output.includes('excuses nothing') &&
      !noRegistry.output.includes('up-to-date'),
    noRegistry.detail
  );
  // The registry reads run through a bounded concurrent pool (REGISTRY_POOL_SIZE = 8). Twelve uninstalled devDependencies overflow it; eleven have a document and one does not. The one failed lookup must still refuse the run, not be swallowed by the pool or lost among the eleven that answered.
  const poolNames = Array.from({ length: 12 }, (_, i) => `pooled-dep-${i}`);
  const poolMissing = poolNames[7];
  const poolDoc = doc('1.0.0', { '1.0.0': { daysAgo: 200 } });
  const poolCase = (missing: string | null): FixtureSpec =>
    devCase({
      manifests: {
        'private/account/web': {
          devDependencies: Object.fromEntries(poolNames.map((n) => [n, '^1.0.0'])),
        },
      },
      locks: {
        '': {},
        'private/account': {},
        'private/account/web': Object.fromEntries(
          poolNames.map((n) => [`node_modules/${n}`, { version: '1.0.0' }])
        ),
      },
      blocklist: '# fixture blocklist\n',
      exceptions: {},
      registry: Object.fromEntries(poolNames.filter((n) => n !== missing).map((n) => [n, poolDoc])),
    });
  const poolOneFails = run(poolCase(poolMissing));
  expect(
    'pool: one failed registry lookup among twelve concurrent ones still refuses the run and names it',
    poolOneFails.status === 1 &&
      poolOneFails.output.includes(
        `${poolMissing} (private/account/web): not installed, so npm outdated skips it, and the registry returned no document`
      ) &&
      !poolOneFails.output.includes('up-to-date'),
    poolOneFails.detail
  );
  const poolAllAnswer = run(poolCase(null));
  expect(
    'pool: CONTROL: the same twelve with every lookup answered pass',
    poolAllAnswer.status === 0 &&
      poolAllAnswer.output.includes(
        '12 uninstalled dependency(ies) judged from lockfile and registry'
      ),
    poolAllAnswer.detail
  );
  const rootUninstalled = run(
    devCase({
      manifests: { '': { devDependencies: { leftpad: '^1.0.0' } } },
      exceptions: {},
      locks: { '': {}, 'private/account': {} },
      outdated: { '': {}, 'private/account': {} },
    })
  );
  expect(
    'uninstalled: a root devDependency that is not installed refuses the run and names the install command',
    rootUninstalled.status === 1 &&
      rootUninstalled.output.includes('leftpad (root)') &&
      rootUninstalled.output.includes('npm ci && npm run install:natives') &&
      !rootUninstalled.output.includes('up-to-date'),
    rootUninstalled.detail
  );
  const rootInstalled = run(
    devCase({
      manifests: { '': { devDependencies: { leftpad: '^1.0.0' } } },
      exceptions: {},
      locks: { '': {}, 'private/account': {} },
      outdated: { '': {}, 'private/account': {} },
      files: { 'node_modules/leftpad/package.json': '{"version":"1.0.0"}' },
    })
  );
  expect(
    'uninstalled: CONTROL: the same root devDependency on disk passes',
    rootInstalled.status === 0 && rootInstalled.output.includes('All dependencies are up-to-date'),
    rootInstalled.detail
  );

  // 12. AN OVERRIDE PINS WHAT `npm update` RESOLVES (worklist #d8fef08a, 2026-10-01). fast-xml-parser was judged 5.11.1 -> 5.11.2, but the root `overrides` entry pinned 5.11.1, so `npm update -w=packages/www fast-xml-parser` stayed on 5.11.1 and the freshness guard failed the step. The planner now moves an exact-pin override to the judged version and runs `npm update <name>` at the root; a ranged override that excludes the target is refused up front. The stub npm clamps to an exact override exactly as real npm does.
  const fxpReason =
    'BLOCKER: pin 5.11.1 to carry the CDATA injection fix; without the pin transitive consumers drift below the fixed range';
  const fxpCase = (override: string): FixtureSpec => ({
    outdated: {
      '': {
        'fast-xml-parser': {
          current: '5.11.1',
          wanted: '5.11.1',
          latest: '5.11.2',
          dependent: 'www',
        },
      },
      'private/account': {},
    },
    locks: {
      '': { 'node_modules/fast-xml-parser': { version: '5.11.1' } },
      'private/account': {},
    },
    updateLocks: { '': { 'node_modules/fast-xml-parser': { version: '5.11.2' } } },
    manifests: {
      '': {
        workspaces: ['packages/www'],
        overrides: { 'fast-xml-parser': override },
        _overridesReasons: { 'fast-xml-parser': fxpReason },
      },
      'packages/www': { dependencies: { 'fast-xml-parser': '^5.11.0' } },
    },
  });
  const pinned = runFixture(fxpCase('5.11.1'), 'upgrade');
  const pinnedPlan = runFixture(fxpCase('5.11.1'), 'upgrade', ['plan', 'npm']);
  const pinnedInst = pinned.installs.join('\n');
  const pinnedDetail = `installs:\n${pinnedInst}\noutput:\n${pinned.output}\npackage.json:\n${pinned.rootManifest}`;
  const pinnedPkg = JSON.parse(pinned.rootManifest) as {
    overrides: Record<string, string>;
    _overridesReasons: Record<string, string>;
  };
  expect(
    'override: an exact-pin override is moved to the judged version and the update runs at the root, not under -w',
    pinned.status === 0 &&
      pinnedPkg.overrides['fast-xml-parser'] === '5.11.2' &&
      pinnedInst.includes('<root> :: update fast-xml-parser ::') &&
      !pinnedInst.includes('-w=packages/www fast-xml-parser'),
    pinnedDetail
  );
  expect(
    'override: the _overridesReasons note is kept intact, and its stale version is named for review',
    pinnedPkg._overridesReasons['fast-xml-parser'] === fxpReason &&
      pinnedPlan.output.includes('_overridesReasons["fast-xml-parser"] still names 5.11.1'),
    pinnedDetail
  );
  const ranged = runFixture(fxpCase('>=5.0.0'), 'upgrade');
  const rangedInst = ranged.installs.join('\n');
  expect(
    'override: CONTROL: an override range that admits the target is left alone and the workspace update runs as before',
    ranged.status === 0 &&
      (JSON.parse(ranged.rootManifest) as { overrides: Record<string, string> }).overrides[
        'fast-xml-parser'
      ] === '>=5.0.0' &&
      rangedInst.includes('<root> :: update -w=packages/www fast-xml-parser ::'),
    `installs:\n${rangedInst}\noutput:\n${ranged.output}`
  );
  const bounded = runFixture(fxpCase('>=5.0.0 <5.11.2'), 'upgrade');
  const boundedInst = bounded.installs.join('\n');
  expect(
    'override: a ranged override that excludes the target is refused before npm runs, and package.json is untouched',
    bounded.status === 1 &&
      !boundedInst.includes('fast-xml-parser') &&
      bounded.output.includes('excludes the judged 5.11.2') &&
      (JSON.parse(bounded.rootManifest) as { overrides: Record<string, string> }).overrides[
        'fast-xml-parser'
      ] === '>=5.0.0 <5.11.2',
    `installs:\n${boundedInst}\noutput:\n${bounded.output}`
  );

  // 13. THE SYNCPACK PIN GROUPS FOLLOW THE UPGRADE (worklist #3b831146, 2026-10-08). --upgrade took the allow-listed @opentelemetry 0.222 -> 0.223 and left the "0.x line in lockstep" group in .syncpackrc.json at ^0.222.0, so `syncpack lint` (check:version) failed on the next run. The upgrade now rewrites the pinVersion of each group holding a moved package, keeping the label; a group whose members did not all move to one line is refused by name. The fixture npm stub never rewrites a manifest, so the "syncpack-style check" below compares each group's pinVersion with the declared ranges AS npm would have left them (a moved package declares ^<its judged latest>); it does not shell out to syncpack.
  const pinGroups = (zero: string, two: string, extra: string[] = []) =>
    `${JSON.stringify(
      {
        versionGroups: [
          {
            label: 'Pin the OpenTelemetry 0.x line in lockstep',
            packages: ['**'],
            dependencies: [otelNode, ...extra],
            pinVersion: zero,
          },
          {
            label: 'Pin the OpenTelemetry 2.x line in lockstep',
            packages: ['**'],
            dependencies: [otelCore],
            pinVersion: two,
          },
          {
            label: 'Pin i18next for CLI',
            packages: ['**'],
            dependencies: ['i18next'],
            pinVersion: '^26.4.2',
          },
        ],
      },
      null,
      2
    )}\n`;
  const behindGroups = (rcText: string, spec: FixtureSpec): string[] => {
    const latest = new Map<string, string>();
    for (const outdated of Object.values(spec.outdated)) {
      for (const [n, o] of Object.entries(outdated)) {
        if (!Array.isArray(o) && o.latest) latest.set(n, o.latest);
      }
    }
    const ranges = Object.values(spec.manifests ?? {}).map((m) => {
      const deps = (m as { dependencies?: Record<string, string> }).dependencies ?? {};
      return Object.fromEntries(
        Object.entries(deps).map(([n, r]) => [n, latest.has(n) ? `^${latest.get(n)}` : r])
      );
    });
    const rc = JSON.parse(rcText) as {
      versionGroups: Array<{ label: string; dependencies: string[]; pinVersion: string }>;
    };
    return rc.versionGroups
      .filter((g) =>
        g.dependencies.some((d) => ranges.some((r) => r[d] !== undefined && r[d] !== g.pinVersion))
      )
      .map((g) => g.label);
  };
  const pinCase = (rcText: string, over: Partial<FixtureSpec> = {}): FixtureSpec =>
    otelCase({ syncpackrc: rcText, allow: {}, ...over });
  const startRc = pinGroups('^0.222.0', '^2.11.0');
  const pinSpec = pinCase(startRc);
  const pinBefore = behindGroups(startRc, pinSpec);
  expect(
    'pin groups: CONTROL: the syncpack-style check sees both otel groups behind the post-upgrade manifests before any rewrite',
    pinBefore.length === 2,
    pinBefore.join(', ')
  );
  const pinRun = runFixture(pinSpec, 'upgrade', otelTake);
  const pinAfter =
    pinRun.syncpackrc === null ? ['no file'] : behindGroups(pinRun.syncpackrc, pinSpec);
  const pinGroupsOut = (
    pinRun.syncpackrc ? JSON.parse(pinRun.syncpackrc) : { versionGroups: [] }
  ) as {
    versionGroups: Array<{ label: string; pinVersion: string }>;
  };
  expect(
    'pin groups: an allow-listed out-of-range move and an in-range one move their lockstep groups, labels and the untouched i18next group stay byte-identical, and nothing is left behind',
    pinRun.status === 0 &&
      pinAfter.length === 0 &&
      pinRun.syncpackrc === pinGroups('^0.223.0', '^2.12.0') &&
      pinGroupsOut.versionGroups[2].pinVersion === '^26.4.2' &&
      pinRun.output.includes('3 groups, 2 hold a moved package, 2 rewritten') &&
      pinRun.output.includes('pinVersion "^0.222.0" -> "^0.223.0"'),
    `${pinRun.output}\n${pinRun.syncpackrc}`
  );
  const skipRun = runFixture(
    pinCase(startRc, { env: { CHECK_DEPS_MUTANT: 'skip-pin-sync' } }),
    'upgrade',
    otelTake
  );
  const skipBehind = skipRun.syncpackrc === null ? [] : behindGroups(skipRun.syncpackrc, pinSpec);
  expect(
    'pin groups: CONTROL: with the rewrite disabled (skip-pin-sync mutant) the same upgrade exits 0 yet the syncpack-style check finds both groups behind',
    skipRun.status === 0 && skipRun.syncpackrc === startRc && skipBehind.length === 2,
    `${skipRun.output}\n${skipRun.syncpackrc}`
  );
  // A group with a second member that is declared, on the old line, and did not move: pinning it to 0.223 would only fail syncpack on that member, so the group is refused by name and left alone while the other group still moves.
  const lagSpec = pinCase(pinGroups('^0.222.0', '^2.11.0', ['@opentelemetry/sdk-logs']), {
    manifests: {
      '': { workspaces: ['packages/cli'] },
      'packages/cli': {
        dependencies: {
          [otelCore]: '^2.11.0',
          [otelNode]: '^0.222.0',
          '@opentelemetry/sdk-logs': '^0.222.0',
        },
      },
    },
  });
  const lagRun = runFixture(lagSpec, 'upgrade', otelTake);
  expect(
    'pin groups: a partial lockstep move is refused naming the group and the laggard, the whole run is restored (the other group does not move alone) and the run is red',
    lagRun.status === 1 &&
      lagRun.syncpackrc === pinGroups('^0.222.0', '^2.11.0', ['@opentelemetry/sdk-logs']) &&
      lagRun.output.includes(
        'group "Pin the OpenTelemetry 0.x line in lockstep" has members on different lines'
      ) &&
      lagRun.output.includes('@opentelemetry/sdk-logs "^0.222.0" (not moved)'),
    `${lagRun.output}\n${lagRun.syncpackrc}`
  );
  // Nothing in the groups moved: the file is not rewritten at all.
  const idleRc = `${JSON.stringify({ versionGroups: [{ label: 'Pin i18next for CLI', packages: ['**'], dependencies: ['i18next'], pinVersion: '^26.4.2' }] }, null, 2)}\n`;
  const idleRun = runFixture(pinCase(idleRc), 'upgrade', otelTake);
  expect(
    'pin groups: a group whose packages did not move is untouched, and the shape says 0 groups hold a moved package',
    idleRun.status === 0 &&
      idleRun.syncpackrc === idleRc &&
      idleRun.output.includes('1 groups, 0 hold a moved package, 0 rewritten'),
    `${idleRun.output}\n${idleRun.syncpackrc}`
  );
  // A glob entry covering a moved package: nothing is rewritten and the group is named.
  {
    const globGroup = (label: string, pinVersion: string) => ({
      label,
      packages: ['**'],
      dependencies: ['@opentelemetry/*'],
      pinVersion,
    });
    const globRc = `${JSON.stringify(
      {
        versionGroups: [
          globGroup('Pin OpenTelemetry by glob', '^0.222.0'),
          globGroup('Any version of the api', '*'),
        ],
      },
      null,
      2
    )}\n`;
    const plan = planPinSync(globRc, new Map([['@opentelemetry/api', '0.223.0']]), []);
    expect(
      'pin groups: a glob entry covering a moved package is an error naming the group, with no rewrite, and a non-caret pin stays silent',
      plan.text === null &&
        plan.errors.length === 1 &&
        plan.errors[0].includes('group "Pin OpenTelemetry by glob"') &&
        plan.rewrites.length === 0,
      JSON.stringify(plan)
    );
  }
  {
    // A moved literal member must not hide a moved glob-covered package that ends past the line the pin would move to.
    const mixedRc = `${JSON.stringify(
      {
        versionGroups: [
          {
            label: 'Pin OpenTelemetry mixed',
            packages: ['**'],
            dependencies: ['@opentelemetry/api', '@opentelemetry/sdk-*'],
            pinVersion: '^0.222.0',
          },
        ],
      },
      null,
      2
    )}\n`;
    const mixed = planPinSync(
      mixedRc,
      new Map([
        ['@opentelemetry/api', '0.223.0'],
        ['@opentelemetry/sdk-node', '0.224.0'],
      ]),
      []
    );
    expect(
      'pin groups: a glob entry covering a package that moved past a moved literal member is an error naming the group, with no rewrite',
      mixed.text === null &&
        mixed.errors.length === 1 &&
        mixed.errors[0].includes('group "Pin OpenTelemetry mixed"') &&
        mixed.errors[0].includes('@opentelemetry/sdk-node@0.224.0') &&
        mixed.errors[0].includes('@opentelemetry/api@0.223.0') &&
        mixed.rewrites.length === 0,
      JSON.stringify(mixed)
    );
    const level = planPinSync(
      mixedRc,
      new Map([
        ['@opentelemetry/api', '0.223.0'],
        ['@opentelemetry/sdk-node', '0.223.0'],
      ]),
      []
    );
    expect(
      'pin groups: a glob-covered package level with the moved literal member is rewritten with the group, not refused',
      level.errors.length === 0 && level.rewrites.length === 1,
      JSON.stringify(level)
    );
  }
  // A file the rewrite cannot reproduce byte for byte is refused, not reformatted.
  const oddRc = startRc.replace(/\n/g, '\r\n');
  const oddRun = runFixture(pinCase(oddRc), 'upgrade', otelTake);
  expect(
    'pin groups: an rc file that is not in the exact form it would rewrite is refused and left byte-identical',
    oddRun.status === 1 &&
      oddRun.syncpackrc === oddRc &&
      oddRun.output.includes('not in the two-space JSON form'),
    `${oddRun.output}\n${oddRun.syncpackrc}`
  );
  expect(
    'pin groups: a refused rewrite (no text) prints no rewrite line and counts 0 rewritten',
    oddRun.output.includes('hold a moved package, 0 rewritten') &&
      !oddRun.output.includes('.syncpackrc.json group'),
    oddRun.output
  );
  const realPin: NodeJS.ProcessEnv = { ...process.env, CHECK_DEPS_MUTANT: 'skip-pin-sync' };
  delete realPin.CHECK_DEPS_ROOT;
  delete realPin.CHECK_DEPS_FORCE_PROBE_FAILURE;
  const realPinRun = spawnSync(process.execPath, [...process.execArgv, process.argv[1]], {
    cwd: CONSOLE_ROOT,
    encoding: 'utf-8',
    env: realPin,
  });
  expect(
    'mutant: CONTROL: skip-pin-sync without CHECK_DEPS_ROOT is refused',
    realPinRun.status === 1 &&
      `${realPinRun.stdout}${realPinRun.stderr}`.includes(
        'CHECK_DEPS_MUTANT=skip-pin-sync refused'
      ),
    `${realPinRun.stdout}${realPinRun.stderr}`
  );

  // THE RELEASE-AGE PARTITION KEEPS INPUT ORDER. The lookups run concurrently and here answer in reverse, the last package first; both lists must still come out in the order the packages went in, or two runs over one tree print different text.
  const orderNow = Date.parse('2026-10-14T12:00:00Z');
  const orderPkgs = ['a', 'b', 'c', 'd'].map((name) => ({
    name,
    current: '1.0.0',
    latest: '1.0.1',
  }));
  const orderAge = new Map([
    ['a', orderNow - 10 * 86_400_000],
    ['b', orderNow - 60_000],
    ['c', orderNow - 10 * 86_400_000],
    ['d', orderNow - 60_000],
  ]);
  const orderDelay = new Map([
    ['a', 40],
    ['b', 30],
    ['c', 20],
    ['d', 10],
  ]);
  const ordered = await partitionByReleaseAge(
    orderPkgs,
    86_400_000,
    orderNow,
    (name) =>
      new Promise((resolve) =>
        setTimeout(() => resolve(orderAge.get(name) ?? null), orderDelay.get(name))
      )
  );
  expect(
    'the release-age partition keeps input order when the registry answers in reverse',
    ordered.installable.map((x) => x.name).join(',') === 'a,c' &&
      ordered.tooNew.map((x) => x.name).join(',') === 'b,d',
    `installable=${ordered.installable.map((x) => x.name).join(',')} tooNew=${ordered.tooNew.map((x) => x.name).join(',')}`
  );

  // 14. T4: THE NPM DRIVER'S LOCKFILE BEHAVIOUR. The workers/ projects are judged (nothing did until 2026-10-14), a changed root lockfile is followed by the canonical pass, `npm ci` and `npm run install:natives` in that order with no hand step, and `lockfiles` runs the canonical pass over every npm project of the registry.
  const wkLock = { 'node_modules/hono': { version: '4.12.25' } };
  const workers: FixtureSpec = {
    outdated: {
      '': { tsx: { current: '4.22.1', wanted: '4.23.15', latest: '4.23.15' } },
      'private/account': {},
      'workers/account': { hono: { current: '4.12.25', wanted: '4.12.26', latest: '4.12.26' } },
    },
    locks: {
      '': { 'node_modules/tsx': { version: '4.22.1' } },
      'private/account': {},
      'workers/account': wkLock,
    },
    updateLocks: {
      '': { 'node_modules/tsx': { version: '4.23.15' } },
      'workers/account': { 'node_modules/hono': { version: '4.12.26' } },
    },
    manifests: {
      '': { devDependencies: { tsx: '^4.22.1' } },
      'workers/account': { dependencies: { hono: '^4.12.25' } },
    },
  };
  const wChk = runFixture(workers, 'check');
  expect(
    'workers: check names the workers/ manifest among those judged and reports its outdated package',
    wChk.status === 1 &&
      wChk.output.includes('(root, workers/account, private/account)') &&
      wChk.output.includes('Outdated packages in workers/account (must upgrade)') &&
      wChk.output.includes('hono: 4.12.25 -> 4.12.26') &&
      wChk.output.includes('Run: npm run pins -- bump npm'),
    wChk.output
  );
  expect(
    'workers: the failure text names the pins remedy and no longer the deleted --upgrade',
    !wChk.output.includes('--upgrade'),
    wChk.output
  );
  const wRun = runFixture(workers, 'upgrade');
  expect(
    'workers: `bump npm` updates the workers/ project in its own directory under the pinned npm',
    wRun.status === 0 &&
      wRun.installs.some((l) => l.startsWith('<root>/workers/account :: update hono ::')) &&
      wRun.installs.every((l) => l.endsWith(`via=npm@${FIXTURE_NPM_VERSION}`)),
    `${wRun.installs.join('\n')}\n${wRun.output}`
  );
  const canon = wRun.other.map((l) => l.replace(/^<root>/, '').split(' :: ')[1]);
  expect(
    'lockfile: a changed root lockfile is followed by the canonical pass per touched lockfile, then `npm ci`, then `npm run install:natives`, with no hand step',
    canon.filter((c) => c === 'install --package-lock-only --ignore-scripts').length === 2 &&
      canon.indexOf('ci') > canon.lastIndexOf('install --package-lock-only --ignore-scripts') &&
      canon.indexOf('run install:natives') === canon.indexOf('ci') + 1 &&
      wRun.other.some((l) => l.includes('<root>/workers/account ::')),
    wRun.other.join('\n')
  );
  const lf = runFixture(workers, 'upgrade', ['lockfiles']);
  expect(
    'lockfile: `lockfiles` runs the canonical pass under the pinned npm over every npm project of the registry that has a lockfile, and nothing else',
    lf.status === 0 &&
      lf.other.filter((l) => l.includes('--package-lock-only')).length === 3 &&
      lf.installs.length === 0 &&
      lf.output.includes(`npx -y npm@${FIXTURE_NPM_VERSION} install --package-lock-only`),
    `${lf.other.join('\n')}\n${lf.output}`
  );
  const lf1 = runFixture(workers, 'upgrade', ['lockfiles', 'workers/account']);
  expect(
    'lockfile: `lockfiles <dir>` runs it for that project alone, and an unknown directory is refused naming the known ones',
    lf1.status === 0 && lf1.other.filter((l) => l.includes('--package-lock-only')).length === 1,
    lf1.other.join('\n')
  );
  const lfBad = runFixture(workers, 'upgrade', ['lockfiles', ['packages', 'nope'].join('/')]);
  expect(
    'lockfile: CONTROL: an unknown directory is refused and nothing runs',
    lfBad.status === 1 &&
      lfBad.output.includes('is not an npm project of the registry') &&
      lfBad.other.length === 0,
    lfBad.output
  );

  // 15. T6: A MAJOR BY NAME. `bump npm --to <key> --major --reason` takes a blocklisted major in one transaction: the install, and the removal of its blocklist line and its held-major exception, with no allow entry left behind (the entry is transient, so the allow liveness check has nothing dead to refuse).
  const blockedBlock =
    '# Widget 2 rewrites its plugin API.\nwidget  # BLOCKER: widget 2 rewrites its plugin API, so it needs a coordinated migration of every plugin\n\n';
  const keepBlock =
    'keeper  # BLOCKER: keeper stays on 1.x because the exporter pins its peer range to the 1.x line\n';
  const majorSpec = (over: Partial<FixtureSpec> = {}): FixtureSpec => ({
    outdated: {
      '': {
        widget: { current: '1.2.0', wanted: '1.2.0', latest: '2.4.1' },
        keeper: { current: '1.0.0', wanted: '1.0.0', latest: '2.0.0' },
      },
      'private/account': {},
    },
    locks: {
      '': {
        'node_modules/widget': { version: '1.2.0' },
        'node_modules/keeper': { version: '1.0.0' },
      },
      'private/account': {},
    },
    manifests: { '': { dependencies: { widget: '^1.2.0', keeper: '^1.0.0' } } },
    blocklist: `# fixture blocklist\n\n${blockedBlock}${keepBlock}`,
    exceptions: {
      widget: {
        owner: 'd778be9d',
        reason:
          'widget 2 needs the plugin API migration, which is scheduled with the lint-tooling change',
        expires: isoDate(utcDay(Date.now()) + 10 * DAY_MS),
      },
    },
    ...over,
  });
  const takeWidget = [
    'bump',
    'npm',
    '--to',
    'widget@2',
    '--major',
    '--reason',
    'widget 2 is taken now that the plugin API migration landed',
  ];
  const mj = runFixture(majorSpec(), 'upgrade', takeWidget);
  const mjAllow = mj.files.get('.ci/config/deps-major-allow.json');
  const mjEx = JSON.parse(mj.files.get(MAJOR_EXCEPTIONS_REL) ?? '{}') as {
    exceptions: Record<string, unknown>;
  };
  const mjBlock = mj.files.get(BLOCKLIST_REL) ?? '';
  expect(
    'major: the net diff of a blocklisted major is the install, the dropped blocklist line with its comment, and the dropped exception, and nothing else',
    mj.status === 0 &&
      mj.installs.length === 1 &&
      mj.installs[0].startsWith('<root> :: install widget@2.4.1 ::') &&
      !mjBlock.includes('widget') &&
      !mjBlock.includes('Widget 2 rewrites') &&
      mjBlock.includes('keeper  # BLOCKER:') &&
      !('widget' in mjEx.exceptions) &&
      mjAllow === `${JSON.stringify({ allow: {} }, null, 2)}\n`,
    `${mj.installs.join('\n')}\n${mjBlock}\n${mj.output}`
  );
  expect(
    'major: CONTROL: without `--major` the same `--to` is refused as a major and nothing is written',
    runFixture(majorSpec(), 'upgrade', ['bump', 'npm', '--to', 'widget@2']).status === 1,
    ''
  );
  const noReason = runFixture(majorSpec(), 'upgrade', [
    'bump',
    'npm',
    '--to',
    'widget@2',
    '--major',
  ]);
  expect(
    'major: CONTROL: `--major` without `--reason` is refused',
    noReason.status === 2 && noReason.output.includes('--reason'),
    noReason.output
  );
  const youngMajor = runFixture(
    majorSpec({
      files: { '.ci/config/release-age.json': '{"minimum_release_age_minutes": 1440}\n' },
      registry: {
        widget: {
          'dist-tags': { latest: '2.4.1' },
          versions: { '1.2.0': {}, '2.4.1': {} },
          time: {
            '1.2.0': new Date(Date.now() - 400 * DAY_MS).toISOString(),
            '2.4.1': new Date(Date.now() - 3_600_000).toISOString(),
          },
        } as Packument,
        keeper: {
          'dist-tags': { latest: '2.0.0' },
          versions: { '1.0.0': {}, '2.0.0': {} },
          time: { '2.0.0': new Date(Date.now() - 400 * DAY_MS).toISOString() },
        } as Packument,
      },
    }),
    'upgrade',
    takeWidget
  );
  expect(
    'major: CONTROL: a blocklisted major published inside the release-age window is refused, and the tree is untouched',
    youngMajor.status === 1 &&
      youngMajor.output.includes('inside the release-age window') &&
      youngMajor.installs.length === 0 &&
      (youngMajor.files.get(BLOCKLIST_REL) ?? '').includes('widget  # BLOCKER:'),
    youngMajor.output
  );

  // 16. T6: `remove <pkg>` uninstalls from every declaring manifest and drops every line that named the package.
  const rmBlock = (pkg: string) =>
    `# ${pkg} is held on 1.x for the exporter.\n${pkg}  # BLOCKER: ${pkg} stays on 1.x because the exporter pins its peer range to the 1.x line\n\n`;
  const rmRc = `${JSON.stringify(
    {
      versionGroups: [
        {
          label: 'Pin gizmo and keeper together',
          packages: ['**'],
          dependencies: ['gizmo', 'keeper'],
          pinVersion: '^1.0.0',
        },
        {
          label: 'Pin gizmo alone',
          packages: ['**'],
          dependencies: ['gizmo'],
          pinVersion: '^1.0.0',
        },
      ],
    },
    null,
    2
  )}\n`;
  const rmKnip =
    '{\n  "ignoreDependencies": [\n    // BLOCKER: gizmo is spawned by a script knip cannot trace to a call site\n    "gizmo",\n    // BLOCKER: keeper is loaded lazily and knip cannot trace the call\n    "keeper"\n  ]\n}\n';
  const rmSpec = (over: Partial<FixtureSpec> = {}): FixtureSpec => ({
    outdated: { '': {}, 'private/account': {} },
    locks: {
      '': {
        'node_modules/gizmo': { version: '1.0.0' },
        'node_modules/keeper': { version: '1.0.0' },
      },
      'private/account': {},
    },
    manifests: {
      '': {
        workspaces: ['packages/cli'],
        dependencies: { gizmo: '^1.0.0', keeper: '^1.0.0' },
        overrides: { gizmo: '1.0.0', keeper: '1.0.0' },
        _overridesReasons: {
          gizmo: 'BLOCKER: pinned for the exporter',
          keeper: 'BLOCKER: pinned for the exporter',
        },
      },
      'packages/cli': { devDependencies: { gizmo: '^1.0.0' } },
    },
    blocklist: `# fixture blocklist\n\n${rmBlock('gizmo')}${rmBlock('keeper')}`,
    exceptions: {
      gizmo: {
        owner: 'd778be9d',
        reason:
          'gizmo 2 needs the exporter migration, which is scheduled with the lint-tooling change',
        expires: isoDate(utcDay(Date.now()) + 10 * DAY_MS),
      },
    },
    allow: {},
    syncpackrc: rmRc,
    files: { 'knip.jsonc': rmKnip },
    ...over,
  });
  const rm = runFixture(rmSpec(), 'upgrade', ['remove', 'gizmo']);
  const rmRoot = JSON.parse(rm.rootManifest) as {
    dependencies: Record<string, string>;
    overrides: Record<string, string>;
    _overridesReasons: Record<string, string>;
  };
  const rmCli = JSON.parse(rm.files.get('packages/cli/package.json') ?? '{}') as {
    devDependencies: Record<string, string>;
  };
  const rmRcAfter = JSON.parse(rm.syncpackrc ?? '{}') as {
    versionGroups: Array<{ label: string; dependencies: string[] }>;
  };
  const rmKnipAfter = rm.files.get('knip.jsonc') ?? '';
  expect(
    'remove: the package leaves every declaring manifest and every policy, override, syncpack and knip line, while its neighbours stay byte-identical',
    rm.status === 0 &&
      !('gizmo' in rmRoot.dependencies) &&
      'keeper' in rmRoot.dependencies &&
      !('gizmo' in rmCli.devDependencies) &&
      !('gizmo' in rmRoot.overrides) &&
      'keeper' in rmRoot.overrides &&
      !('gizmo' in rmRoot._overridesReasons) &&
      'keeper' in rmRoot._overridesReasons &&
      !(rm.files.get(BLOCKLIST_REL) ?? '').includes('gizmo') &&
      (rm.files.get(BLOCKLIST_REL) ?? '').includes('keeper  # BLOCKER:') &&
      !(
        'gizmo' in
        (
          JSON.parse(rm.files.get(MAJOR_EXCEPTIONS_REL) ?? '{}') as {
            exceptions: object;
          }
        ).exceptions
      ) &&
      rmRcAfter.versionGroups.length === 1 &&
      rmRcAfter.versionGroups[0].label === 'Pin gizmo and keeper together' &&
      rmRcAfter.versionGroups[0].dependencies.join() === 'keeper' &&
      !rmKnipAfter.includes('gizmo') &&
      rmKnipAfter.includes('"keeper"') &&
      !rmKnipAfter.includes(',\n  ]'),
    `${rm.output}\n${rm.rootManifest}\n${rmKnipAfter}`
  );
  expect(
    'remove: the uninstall runs once per npm project under the pinned npm with the workspace scoped by -w, then the canonical pass',
    rm.installs.length === 1 &&
      rm.installs[0].startsWith(
        '<root> :: uninstall gizmo -w=packages/cli --include-workspace-root'
      ) &&
      rm.other.some((l) => l.includes('--package-lock-only')),
    rm.installs.join('\n')
  );
  const rmImported = runFixture(
    rmSpec({
      files: {
        'knip.jsonc': rmKnip,
        'src/use.ts': "import { g } from 'gizmo';\nexport const x = g;\n",
      },
    }),
    'upgrade',
    ['remove', 'gizmo']
  );
  expect(
    'remove: CONTROL: a package a source file still imports is refused naming the file, and nothing is written',
    rmImported.status === 1 &&
      rmImported.output.includes('still imported by src/use.ts') &&
      rmImported.installs.length === 0 &&
      rmImported.rootManifest.includes('"gizmo": "^1.0.0"'),
    rmImported.output
  );
  for (const [where, file] of [
    ['scripts/', 'scripts/tool.ts'],
    ['a tests directory', ['packages', 'cli', 'tests', 'use.test.ts'].join('/')],
  ] as const) {
    const deep = runFixture(
      rmSpec({
        files: { 'knip.jsonc': rmKnip, [file]: "const g = require('gizmo/sub');\nexport { g };\n" },
      }),
      'upgrade',
      ['remove', 'gizmo']
    );
    expect(
      `remove: a package still imported from ${where} (outside src/ and the top level) is refused naming the file`,
      deep.status === 1 &&
        deep.output.includes(`still imported by ${file}`) &&
        deep.installs.length === 0,
      deep.output
    );
  }
  for (const [where, file] of [
    ['a source folder named build/ below the declaring directory', 'scripts/build/x.ts'],
    ['a dot directory', '.ci/scripts/y.ts'],
  ] as const) {
    const hidden = runFixture(
      rmSpec({
        files: { 'knip.jsonc': rmKnip, [file]: "import { g } from 'gizmo';\nexport { g };\n" },
      }),
      'upgrade',
      ['remove', 'gizmo']
    );
    expect(
      `remove: a package still imported from ${where} is refused naming the file`,
      hidden.status === 1 &&
        hidden.output.includes(`still imported by ${file}`) &&
        hidden.installs.length === 0,
      hidden.output
    );
  }
  const outputOnly = runFixture(
    rmSpec({
      files: {
        'knip.jsonc': rmKnip,
        'build/gen.js': "const g = require('gizmo');\nmodule.exports = g;\n",
        '.ci/cache/c.js': "const g = require('gizmo');\nmodule.exports = g;\n",
      },
    }),
    'upgrade',
    ['remove', 'gizmo']
  );
  expect(
    "remove: CONTROL: an importer under the declaring directory's own build/ or .ci/cache/ is output, not source, and does not refuse",
    outputOnly.status === 0 && outputOnly.installs.length === 1,
    outputOnly.output
  );
  const memberOutput = runFixture(
    rmSpec({
      files: {
        'knip.jsonc': rmKnip,
        'packages/cli/build/gen.js': "const g = require('gizmo');\nmodule.exports = g;\n",
        'packages/cli/coverage/c.js': "const g = require('gizmo');\nmodule.exports = g;\n",
        'packages/cli/.astro/a.js': "const g = require('gizmo');\nmodule.exports = g;\n",
        'workers/x/.wrangler/w.js': "const g = require('gizmo');\nmodule.exports = g;\n",
      },
    }),
    'upgrade',
    ['remove', 'gizmo']
  );
  expect(
    "remove: CONTROL: output a workspace member builds (build/, coverage/ beside its package.json) and generated dot directories at any depth are not sources, so the root's scan does not refuse on them",
    memberOutput.status === 0 && memberOutput.installs.length === 1,
    memberOutput.output
  );
  const noLocks = runFixture(rmSpec({ locks: {} }), 'upgrade', ['remove', 'gizmo']);
  expect(
    'remove: CONTROL: a registry family whose npm-lockfile scope matches no lockfile is refused as VACUOUS, not reported as nothing to do',
    noLocks.status === 1 && noLocks.output.includes('VACUOUS') && noLocks.installs.length === 0,
    noLocks.output
  );
  const rawOnly = buildFixture({
    outdated: {},
    locks: {},
    rawManifests: { 'only/raw': '{"raw":true}\n' },
  });
  const rawOnlyText = fs.existsSync(path.join(rawOnly.root, 'only/raw/package.json'))
    ? fs.readFileSync(path.join(rawOnly.root, 'only/raw/package.json'), 'utf8')
    : '<absent>';
  fs.rmSync(rawOnly.root, { recursive: true, force: true });
  expect(
    'fixture: a raw manifest for a directory no other fixture map names is still written',
    rawOnlyText === '{"raw":true}\n',
    rawOnlyText
  );
  const rmCompact = rmSpec().manifests?.[''] ?? {};
  const rawRoot = runFixture(
    rmSpec({ rawManifests: { '': JSON.stringify(rmCompact, null, 4) } }),
    'upgrade',
    ['remove', 'gizmo']
  );
  expect(
    "remove: a root manifest that holds an override for the package but is not in npm's two-space form is refused, and nothing is written",
    rawRoot.status === 1 && rawRoot.output.includes('not in npm') && rawRoot.installs.length === 0,
    rawRoot.output
  );
  const knipTwoArrays =
    '{\n  "ignoreBinaries": [\n    "alpha",\n    "beta",\n  ],\n  "ignoreDependencies": [\n    // BLOCKER: gizmo is spawned by a script knip cannot trace to a call site\n    "gizmo",\n    // BLOCKER: keeper is loaded lazily and knip cannot trace the call\n    "keeper"\n  ],\n  "ignoreMembers": [\n    "m",\n  ]\n}\n';
  const rmTwo = runFixture(rmSpec({ files: { 'knip.jsonc': knipTwoArrays } }), 'upgrade', [
    'remove',
    'gizmo',
  ]);
  const twoAfter = rmTwo.files.get('knip.jsonc') ?? '';
  expect(
    'remove: dropping a knip entry leaves the trailing commas of every other array alone',
    rmTwo.status === 0 &&
      !twoAfter.includes('gizmo') &&
      twoAfter.includes('"beta",\n  ]') &&
      twoAfter.includes('"m",\n  ]'),
    twoAfter
  );
  const rmLast = runFixture(rmSpec({ files: { 'knip.jsonc': knipTwoArrays } }), 'upgrade', [
    'remove',
    'keeper',
  ]);
  const lastAfter = rmLast.files.get('knip.jsonc') ?? '';
  expect(
    "remove: dropping the last entry of a knip array strips the comma before it and no other array's",
    rmLast.status === 0 &&
      !lastAfter.includes('keeper') &&
      lastAfter.includes('"gizmo"\n  ]') &&
      lastAfter.includes('"beta",\n  ]') &&
      lastAfter.includes('"m",\n  ]'),
    lastAfter
  );

  const rmNone = runFixture(rmSpec(), 'upgrade', ['remove', 'ghost']);
  expect(
    'remove: CONTROL: a package no manifest declares is refused',
    rmNone.status === 1 && rmNone.output.includes('no npm manifest of the registry declares it'),
    rmNone.output
  );

  const realAmbient: NodeJS.ProcessEnv = { ...process.env, CHECK_DEPS_MUTANT: 'ambient-npm' };
  delete realAmbient.CHECK_DEPS_ROOT;
  delete realAmbient.CHECK_DEPS_FORCE_PROBE_FAILURE;
  const realAmbientRun = spawnSync(process.execPath, [...process.execArgv, process.argv[1]], {
    cwd: CONSOLE_ROOT,
    encoding: 'utf-8',
    env: realAmbient,
  });
  expect(
    'mutant: CONTROL: ambient-npm without CHECK_DEPS_ROOT is refused',
    realAmbientRun.status === 1 &&
      `${realAmbientRun.stdout}${realAmbientRun.stderr}`.includes(
        'CHECK_DEPS_MUTANT=ambient-npm refused'
      ),
    `${realAmbientRun.stdout}${realAmbientRun.stderr}`
  );

  console.log(
    joinReport(
      `${GREEN}✓${NC} ${checks} selftest checks: the probe fails closed on both shapes; a breaking bump is held in `,
      'every manifest and applied only when allow-listed, a plain bump beside a held major is refused before any write naming the --to line of every held major, and the run naming them all applies the minors beside them (end to end, CI-shaped ',
      'lockfile input); array and lockfile-only reports are judged, not dropped; dead allow entries and unknown ',
      'versions fail; the scan set is exactly the checked-out submodules; an in-range bump runs as npm update and ',
      'an out-of-range one as a pinned npm install, and an update that resolves anything but the judged version fails ',
      '(freshness-window guard); a failed step is named with its command and exit status, and the child npm never ',
      "inherits a silent loglevel; a blocklisted major warns at 60 days and fails at 90 from its clock line's first ",
      'release (deprecated releases skipped), unless a live peer-range/engine-floor blocker or an expiry <=30 days ',
      'excuses it; expired, stale, dead, ownerless, reasonless and free-text-only exceptions fail; an undatable hold ',
      'fails; the ignore-clock mutant turns the 91-day control green and is refused on a real tree; an uninstalled ',
      'private devDependency is judged from lockfile and registry (and refused when they cannot answer) while an ',
      'installed one is left to npm, and an uninstalled root refuses the run; an exact-pin override is moved to the ',
      'judged version before a root npm update, while an admitting override is left alone and a bounding one is refused; ',
      'a lockstep family moves in one npm update per lockfile, and the split-update mutant fails ERESOLVE; every npm command the pins driver plans is `npx -y npm@<NPM_VERSION>` (the ambient-npm mutant fails), the canonical lockfile pass, `npm ci` and `install:natives` follow a changed root lockfile, and `lockfiles` covers every npm project; the workers/ projects are judged; a major is taken by name with its blocklist line and exception dropped and no allow entry left behind, a young blocklisted major is refused, and `remove` drops every line that named the package and refuses one a source file still imports; an allow-listed ',
      'sibling that pins an in-range package exactly is installed before its lockfile is updated, an in-range same-scope peer of an installing package rides that install (the peer-split mutant fails ERESOLVE), the update-first mutant ',
      'leaves that package held back, and a held-back package names its pinning sibling instead of a freshness breach; ',
      'every step carries --before=<the freshness cutoff>, which agrees with the window rule at its boundary; an upgrade ',
      'rewrites the .syncpackrc.json pinVersion of each group holding a moved package (label kept), the skip-pin-sync ',
      'mutant leaves the group behind and is refused on a real tree, a partial lockstep move or an unreproducible rc ',
      'file is refused by name, and a group whose packages did not move is untouched; the release-age partition keeps ',
      'the input order when the registry answers in reverse'
    )
  );
  process.exit(0);
}

// Run the check
if (process.argv.includes('--selftest')) {
  selftest().catch((error: unknown) => {
    console.error(
      `${RED}✗${NC} selftest crashed: ${error instanceof Error ? error.stack : String(error)}`
    );
    process.exit(1);
  });
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
