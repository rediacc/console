import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// CHECK_DEPS_ROOT is the selftest's seam: it points the whole gate (manifests, lockfiles, blocklist, allow file, release-age config) at a synthetic fixture tree so the --upgrade path can be driven end to end without touching the real one. When it is set, changelog lookups are skipped too, because a fixture never needs them and they are the only network call left.
export const FIXTURE_ROOT = process.env.CHECK_DEPS_ROOT;
export const CONSOLE_ROOT = FIXTURE_ROOT
  ? path.resolve(FIXTURE_ROOT)
  : path.resolve(__dirname, '..', '..', '..');
/** The selftest's mutant seam (see MUTANTS in scripts/gates/check-deps.ts). */
export const MUTANT = process.env.CHECK_DEPS_MUTANT;
export const MAJOR_ALLOW_REL = '.ci/config/deps-major-allow.json';
export const DAY_MS = 86_400_000;

interface ParsedVersion {
  major: number;
  minor: number;
  patch: number;
  prerelease: string | null;
}

export interface PackageInfo {
  name: string;
  current: string;
  latest: string;
  wanted?: string;
  reason?: string;
  /** The allow key that authorised a breaking upgrade, when one did. */
  allowKey?: string;
  /** The peerDependencies the TARGET (`latest`) version declares, optional ones included (npm enforces an installed optional peer's range), from the registry document; absent when none was read. */
  peers?: Record<string, string>;
}

/** The `packages` map of a manifest's package-lock.json, or null when there is none. */
/** One `packages` entry of a package-lock.json: the resolved version and the ranges that installed copy itself declares. */
export interface LockEntry {
  version?: string;
  dependencies?: Record<string, string>;
  optionalDependencies?: Record<string, string>;
  peerDependencies?: Record<string, string>;
}

export function readLockPackages(dir: string): Record<string, LockEntry> | null {
  const lockPath = path.join(dir, 'package-lock.json');
  if (!fs.existsSync(lockPath)) return null;
  try {
    const lock = JSON.parse(fs.readFileSync(lockPath, 'utf-8')) as {
      packages?: Record<string, LockEntry>;
    };
    return lock.packages ?? null;
  } catch {
    return null;
  }
}

/**
 * Parse a semver version string into components
 */
export function parseVersion(version: string): ParsedVersion | null {
  const match = /^(\d+)\.(\d+)\.(\d+)(?:-(.+))?$/.exec(version);
  if (!match) return null;
  return {
    major: Number.parseInt(match[1], 10),
    minor: Number.parseInt(match[2], 10),
    patch: Number.parseInt(match[3], 10),
    prerelease: match[4] || null,
  };
}

/** Numeric order of two versions; unparseable ones sort as equal so a caller keeps its first pick. */
export function compareVersions(a: string, b: string): number {
  const va = parseVersion(a);
  const vb = parseVersion(b);
  if (!va || !vb) return 0;
  return va.major - vb.major || va.minor - vb.minor || va.patch - vb.patch;
}

/**
 * The caret line a version belongs to: '8' for 8.x, '0.575' for 0.575.x, '0.0.3' for 0.0.3. Two versions on different lines are a breaking move under npm's own caret semantics, which is why 0.575 -> 1.48 (lucide-react) counts exactly like 6 -> 8 (vite). Null when the version does not parse.
 */
export function releaseLine(version: string): string | null {
  const v = parseVersion(version);
  if (!v) return null;
  if (v.major > 0) return String(v.major);
  if (v.minor > 0) return `0.${v.minor}`;
  return `0.0.${v.patch}`;
}

/**
 * True when moving current -> latest leaves the caret range. An unparseable version on either side counts as breaking: the cost of holding a version the gate cannot classify is one manual decision, the cost of applying it blind is a surprise major.
 */
export function isBreakingBump(current: string, latest: string): boolean {
  const lc = releaseLine(current);
  const ll = releaseLine(latest);
  if (!lc || !ll) return true;
  return lc !== ll;
}

/**
 * Find which workspace packages contain a given dependency
 */
export function findWorkspacesWithPackage(
  packageName: string,
  root: string = CONSOLE_ROOT
): string[] {
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

// ---------------------------------------------------------------------------
// Range evaluator, for peer-range blockers and engines.node. `satisfiesRange` above handles single shapes only and `semver` is not a direct dependency, so this is in-file. It understands `||` sets of space-separated comparators (`^ ~ >= > <= < =`, bare and x-range versions, partials such as `^9.7` and `>=10.4`) and REFUSES anything else (hyphen ranges, tags, URLs) by returning null: a range it cannot read is never passed.
// ---------------------------------------------------------------------------

type Triple = [number, number, number];
interface Bound {
  op: '>=' | '>' | '<' | '<=';
  v: Triple;
}
/** One `||` alternative: every bound must hold. `[]` admits everything. */
type RangeSet = Bound[];

const NEVER: Bound = { op: '<', v: [0, 0, 0] };
const COMPARATOR_RE =
  /^(<=|>=|<|>|=|\^|~>?)?v?(\d+|[xX*])(?:\.(\d+|[xX*]))?(?:\.(\d+|[xX*]))?(-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/;

function cmpTriple(a: Triple, b: Triple): number {
  return a[0] - b[0] || a[1] - b[1] || a[2] - b[2];
}

function parseComparator(text: string): Bound[] | null {
  const m = COMPARATOR_RE.exec(text);
  if (!m) return null;
  const op = (m[1] ?? '').replace('~>', '~');
  const parts: number[] = [];
  for (const raw of [m[2], m[3], m[4]]) {
    if (raw === undefined || /^[xX*]$/.test(raw)) break;
    parts.push(Number.parseInt(raw, 10));
  }
  const n = parts.length;
  const pre = Boolean(m[5]) && n === 3;
  const [M = 0, mi = 0, p = 0] = parts;
  const base: Triple = [M, mi, p];
  const nextOf = (k: number): Triple =>
    k === 1 ? [M + 1, 0, 0] : k === 2 ? [M, mi + 1, 0] : [M, mi, p + 1];
  // A prerelease comparator is judged only against STABLE versions here, so `>=X-pre` is `>=X`, `<=X-pre` is `<X`, and an exact `X-pre` admits no stable version at all.
  switch (op) {
    case '':
    case '=':
      if (n === 0) return [];
      if (n < 3)
        return [
          { op: '>=', v: base },
          { op: '<', v: nextOf(n) },
        ];
      return pre
        ? [NEVER]
        : [
            { op: '>=', v: base },
            { op: '<=', v: base },
          ];
    case '>=':
      return n === 0 ? [] : [{ op: '>=', v: base }];
    case '>':
      if (n === 0) return [NEVER];
      if (n < 3) return [{ op: '>=', v: nextOf(n) }];
      return [{ op: pre ? '>=' : '>', v: base }];
    case '<':
      return n === 0 ? [NEVER] : [{ op: '<', v: base }];
    case '<=':
      if (n === 0) return [];
      if (n < 3) return [{ op: '<', v: nextOf(n) }];
      return [{ op: pre ? '<' : '<=', v: base }];
    case '~':
      if (n === 0) return [];
      return [
        { op: '>=', v: base },
        { op: '<', v: nextOf(n === 1 ? 1 : 2) },
      ];
    case '^': {
      if (n === 0) return [];
      const upper: Triple =
        M > 0 || n === 1 ? [M + 1, 0, 0] : mi > 0 || n === 2 ? [0, mi + 1, 0] : [0, 0, p + 1];
      return [
        { op: '>=', v: base },
        { op: '<', v: upper },
      ];
    }
    default:
      return null;
  }
}

/** Parse a range into its `||` alternatives, or null when any part of it is not understood. */
export function parseRange(range: string): RangeSet[] | null {
  const sets: RangeSet[] = [];
  for (const alt of range.split('||')) {
    const text = alt.trim().replace(/(<=|>=|<|>|=|\^|~>?)\s+/g, '$1');
    if (/\s-\s/.test(alt)) return null;
    const bounds: Bound[] = [];
    if (text !== '') {
      for (const tok of text.split(/\s+/)) {
        const b = parseComparator(tok);
        if (!b) return null;
        bounds.push(...b);
      }
    }
    sets.push(bounds);
  }
  return sets;
}

/** True when the STABLE `version` satisfies one of the parsed alternatives. */
export function rangeAdmits(sets: RangeSet[], version: string): boolean {
  const pv = parseVersion(version);
  if (!pv || pv.prerelease) return false;
  const t: Triple = [pv.major, pv.minor, pv.patch];
  return sets.some((set) =>
    set.every((b) => {
      const c = cmpTriple(t, b.v);
      return b.op === '>=' ? c >= 0 : b.op === '>' ? c > 0 : b.op === '<' ? c < 0 : c <= 0;
    })
  );
}

/** The lowest major a parsed range admits at all, i.e. the major of its lowest lower bound (0 when an alternative has none). */
export function rangeFloorMajor(sets: RangeSet[]): number {
  let floor = Number.POSITIVE_INFINITY;
  for (const set of sets) {
    let lo = 0;
    for (const b of set) if (b.op === '>=' || b.op === '>') lo = Math.max(lo, b.v[0]);
    floor = Math.min(floor, lo);
  }
  return floor === Number.POSITIVE_INFINITY ? 0 : floor;
}

/** Start of the UTC day containing `ms`. */
export function utcDay(ms: number): number {
  return Math.floor(ms / DAY_MS) * DAY_MS;
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
export function printPackage(
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
 * The manifests syncpack lints, mirroring `source` in .syncpackrc.json: the root, every packages/* and private/account. Fixture roots read the same shape.
 */
export function syncpackSourceDirs(): string[] {
  const dirs = ['', 'private/account'];
  try {
    for (const d of fs.readdirSync(path.join(CONSOLE_ROOT, 'packages'), { withFileTypes: true })) {
      if (d.isDirectory()) dirs.push(`packages/${d.name}`);
    }
  } catch {
    // No packages/ directory: only the root and private/account are sources.
  }
  return dirs.map((d) => path.join(CONSOLE_ROOT, d));
}
