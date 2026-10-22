import fs from 'node:fs';
import path from 'node:path';
import {
  compareVersions,
  FIXTURE_ROOT,
  findWorkspacesWithPackage,
  MUTANT,
  type PackageInfo,
  parseRange,
  parseVersion,
  rangeAdmits,
  releaseLine,
  utcDay,
} from './shared.js';

export interface InstallStep {
  cwd: string;
  args: string[];
  label: string;
  packages: PackageInfo[];
  /** For an `(update)` step: every (package, declaring workspace) pair the freshness guard checks, `workspace` being the `packages/<ws>` path where npm may have nested a copy, absent for the root manifest. Defaults to `packages`, hoisted. */
  checks?: Array<{ pkg: PackageInfo; workspace?: string }>;
  /** An exact-pin `overrides` entry that would hold the package where it is: the pins npm driver plans a write that moves it to the judged version before npm runs. */
  overrideBump?: { file: string; name: string; from: string; to: string };
  /** Set when an override makes the step unsafe to apply: the pins npm driver refuses the whole plan and runs nothing. */
  refused?: string;
}

/** The project-level `overrides` that pin a package itself, by name: a string value, or the `"."` key of an object value. Keys with a version selector (`name@range`) and nested parent scopes target transitive copies only and are left out. */
function readDirectOverrides(dir: string): Map<string, string> {
  const out = new Map<string, string>();
  try {
    const pkg = JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf-8')) as {
      overrides?: Record<string, unknown>;
    };
    for (const [key, value] of Object.entries(pkg.overrides ?? {})) {
      if (typeof value === 'string') out.set(key, value);
      else if (typeof value === 'object' && value !== null) {
        const self = (value as Record<string, unknown>)['.'];
        if (typeof self === 'string') out.set(key, self);
      }
    }
  } catch {
    // An unreadable manifest has no overrides this planner can honour; npm itself will refuse it loudly.
  }
  return out;
}

const EXACT_VERSION_RE = /^\d+\.\d+\.\d+$/;

/** The ranges a manifest declares for what it installs (dependencies, devDependencies, optionalDependencies). Peer ranges are left out: they say what a consumer must bring, not what this manifest installs. Empty when the manifest is missing or unreadable. */
export function readDeclaredRanges(dir: string): Record<string, string> {
  try {
    const pkg = JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf-8')) as {
      dependencies?: Record<string, string>;
      devDependencies?: Record<string, string>;
      optionalDependencies?: Record<string, string>;
    };
    return { ...pkg.optionalDependencies, ...pkg.devDependencies, ...pkg.dependencies };
  } catch {
    return {};
  }
}

/**
 * True when `version` satisfies the declared `range`. Only the shapes the scanned manifests use are understood: `^x.y.z`, `~x.y.z`, an exact `x.y.z`, and `*`. Anything else (a `file:` spec, a compound range, a prerelease target) answers false, which keeps the package on the pinned `npm install name@version` path the gate always used.
 */
export function satisfiesRange(range: string | undefined, version: string): boolean {
  if (range === undefined) return false;
  const r = range.trim();
  const target = parseVersion(version);
  if (!target || target.prerelease) return false;
  if (r === '*' || r === 'x') return true;
  const m = r.match(/^([\^~]?)(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)$/);
  if (!m) return false;
  const [, op, baseText] = m;
  const base = parseVersion(baseText);
  if (!base) return false;
  if (op === '') return compareVersions(version, baseText) === 0 && !base.prerelease;
  if (compareVersions(version, baseText) < 0) return false;
  if (op === '~') return target.major === base.major && target.minor === base.minor;
  return releaseLine(version) === releaseLine(baseText);
}

/**
 * The newest publish time a release can have and still be actionable at `nowMs`: the inverse of scripts/lib/release-age.ts's rule (a release published at P is actionable from startOfNextUtcDay(P + window)), so P qualifies exactly when P < startOfUtcDay(now) - window. Every planned npm step passes it as `--before`, because the gate judges only the packages it names: `npm update vitest` re-resolves vitest's whole subtree, and on 2026-10-02 it pulled vite 8.3.2 (published 2026-10-01T10:17Z, 14 h old) into private/account/package-lock.json as a transitive dependency the freshness window never saw. The selftest proves this agrees with isWithinFreshnessWindow on both sides of the boundary. Null when the window is off.
 */
export function freshnessCutoffMs(nowMs: number, minReleaseAgeMs: number): number | null {
  if (minReleaseAgeMs <= 0) return null;
  return utcDay(nowMs) - minReleaseAgeMs - 1;
}

/**
 * Build the npm invocations for the packages cleared to upgrade. Pure apart from reading manifests, so the selftest can assert what WOULD run.
 *
 * TWO VERBS, chosen per manifest by the range it already declares. A target the declared range already allows (`^8.70.1` -> 8.71.0) is planned as `npm update <names>`: that is the only verb npm resolves a pinned sibling family with (typescript-eslint pins its @typescript-eslint/* siblings exactly, so on 2026-09-30 `npm install typescript-eslint@8.71.0 @typescript-eslint/parser@8.71.0 ...` failed ERESOLVE against the installed 8.70.1 family, while `npm update` of the same names succeeded). `npm update` takes the highest version the range allows, which is the judged `latest` unless a newer in-range version was published after this run's freshness check; the pins npm driver therefore follows every `(update)` step with a freshness guard against the lockfile that fails the run when npm resolved anything but the exact version judged (see verifyUpdatedVersions). A target outside the declared range (an allow-listed major, an exact pin) still installs as `name@<the exact latest judged>`, never `name@latest`, for the same freshness reason. The input is only ever `mustUpgrade`, which categorizePackages never lets a held major into.
 *
 * ONE `npm update` PER LOCKFILE (2026-10-02). Each manifest's packages are still judged against that manifest's own range, but every in-range bump of one npm project (the console root and its workspaces, or one private/ manifest) runs as a SINGLE `npm update -w=<every workspace holding one> [--include-workspace-root] <every name>`. The per-workspace split this replaced (`npm update -w=packages/cli vitest @vitest/ui ...`, then `-w=packages/www ...`, one call each) could never move a family that moves in lockstep: @vitest/coverage-v8@5.0.2 and @vitest/ui@5.0.2 declare an EXACT peer `vitest@"5.0.2"`, npm had nested a coverage-v8 copy in four workspaces, and a `-w` call does not touch another workspace's nested copy, so each per-workspace call met the other workspaces' pins and failed ERESOLVE (6 of 9 steps on 2026-10-02, while the one combined call resolved in 7 s on npm 11.20.0). A lockfile is one ideal tree, so the coupling is decided by npm's resolver over the whole of it, not re-derived here from peer ranges: any grouping finer than the lockfile would have to reproduce that resolver (transitive peers, nesting, hoisting), and one call per lockfile is a superset of every such group. An `-w` scope does not stop a named update moving a HOISTED copy anyway (measured on npm 11.20.0: `npm update -w=packages/a picomatch` moved a picomatch only packages/b declares), so the split never isolated the workspaces it claimed to. Out-of-range targets stay per manifest (`npm install -w=packages/<ws> name@exact`), because `install` adds the package to every workspace it is given.
 *
 * INSTALL BEFORE UPDATE, PER LOCKFILE (2026-10-08). Within one project the out-of-range `npm install` steps run first and the project's single `npm update` after them. The reverse order, which this replaced, ran the update while the OLD version of an allow-listed sibling was still installed: @opentelemetry/sdk-node 0.222.0 (and its 0.x experimental family) pins @opentelemetry/core, resources and sdk-metrics EXACTLY at 2.11.0, so `npm update -w=packages/cli @opentelemetry/core ...` kept 2.11.0, the freshness guard failed the step (judged 2.12.0, installed 2.11.0) in the console root and in private/account alike, and only the install of sdk-node@0.223.0 that ran after it released the pin. Installing first moves the pinning sibling, so the update then resolves the judged version in the same run. When no allow entry moves the sibling, the update still cannot land; verifyUpdatedVersions then names the lockfile entry that pins it (a held-back package, not a freshness breach).
 *
 * A PEER FAMILY RIDES THE INSTALL (2026-10-22). Within one manifest, an in-range package that shares an npm scope with an out-of-range one joins that install as an exact `name@latest` instead of waiting for the `npm update`: `@opentelemetry/core@3` peer-requires `@opentelemetry/api` >=1.10 and failed ERESOLVE in private/account while the in-range api 1.9.1 -> 1.10.0 was still queued. Only the same-scope siblings of a package whose semver major number changes fold (a 0.x minor keeps its siblings on the update); the rest of the manifest stays on the single `npm update` (a pinned sibling family installed by name fails where `update` succeeds).
 *
 * AN OVERRIDE DECIDES WHAT NPM RESOLVES (worklist #d8fef08a). A package the project's `overrides` pins to a range that excludes the judged version cannot move by `npm update` or `npm install`: on 2026-10-01 the root pinned fast-xml-parser to 5.11.1, `npm update -w=packages/www fast-xml-parser` stayed on 5.11.1, and the freshness guard failed the step. Such a package leaves the ordinary steps. When the override is an exact version and every declaring manifest's range admits the target, the step moves the override to the judged version (planOverrideBump) and runs `npm update <name>` in the project root, which re-resolves every copy the override governs (measured on npm 11.20.0: `npm update` honours a changed override, while `npm install --package-lock-only` exits 0 without applying it). Any other override that excludes the target (a bounded range, a range this gate cannot read, a declared range that excludes the target too) is a refused step: moving it is a decision about the bound, not a freshness bump. An override that admits the target, or a `$name` reference to the root's own range, changes nothing here.
 */
export function planInstalls(
  root: string,
  rootPackages: PackageInfo[],
  privateGroups: Array<{ dir: string; name: string; packages: PackageInfo[] }>,
  /** `freshnessCutoffMs` for this run: every step gets `--before=<it>` so npm resolves no transitive release the window has not cleared. */
  beforeMs: number | null = null
): InstallStep[] {
  const steps: InstallStep[] = [];
  const spec = (p: PackageInfo) => `${p.name}@${p.latest}`;
  /** Overridden packages by `<cwd>\0<name>`, gathered across every manifest that declares them, then planned once per project. */
  const overridden = new Map<
    string,
    { cwd: string; label: string; pkg: PackageInfo; value: string; problems: string[] }
  >();
  /** In-range bumps by project (keyed by `cwd`), collected across its manifests and run as one `npm update` per project. */
  const updates = new Map<
    string,
    {
      cwd: string;
      label: string;
      workspaces: string[];
      root: boolean;
      checks: Array<{ pkg: PackageInfo; workspace?: string }>;
    }
  >();
  /** Out-of-range bumps, one `install` step per manifest, emitted BEFORE the project's update (see the INSTALL BEFORE UPDATE note above). */
  const installs: InstallStep[] = [];
  /** Every project (`cwd`) in the order its first manifest was planned, so the steps keep the root-then-private/ order. */
  const cwdOrder: string[] = [];
  /** One manifest's packages: in-range targets join the project's single `update`, the rest become an `install` step. */
  const plan = (
    cwd: string,
    manifestDir: string,
    flags: string[],
    label: string,
    allPkgs: PackageInfo[],
    workspace?: string
  ) => {
    if (!cwdOrder.includes(cwd)) cwdOrder.push(cwd);
    const ranges = readDeclaredRanges(manifestDir);
    const overrides = readDirectOverrides(cwd);
    const pkgs = allPkgs.filter((p) => {
      const value = overrides.get(p.name);
      if (value === undefined || value.startsWith('$')) return true;
      const sets = parseRange(value);
      if (sets && rangeAdmits(sets, p.latest)) return true;
      const key = `${cwd}\0${p.name}`;
      const entry = overridden.get(key) ?? {
        cwd,
        label: cwd === root ? 'root' : label,
        pkg: p,
        value,
        problems: [],
      };
      const manifestRel = path.relative(root, path.join(manifestDir, 'package.json'));
      if (!EXACT_VERSION_RE.test(value)) {
        entry.problems.push(
          `overrides["${p.name}"] is "${value}", which excludes the judged ${p.latest}; only an exact-version pin is moved automatically`
        );
      } else if (ranges[p.name] !== undefined && !satisfiesRange(ranges[p.name], p.latest)) {
        entry.problems.push(
          `${manifestRel} declares ${p.name} "${ranges[p.name]}", which excludes the judged ${p.latest} as well as the override "${value}"`
        );
      }
      overridden.set(key, entry);
      return false;
    });
    let inRange = pkgs.filter((p) => satisfiesRange(ranges[p.name], p.latest));
    let outOfRange = pkgs.filter((p) => !inRange.includes(p));
    // PEER FAMILY RIDES THE INSTALL (2026-10-22). An in-range sibling of an out-of-range package (same npm scope) joins that manifest's install as an exact `name@latest`: core@3 peer-requires @opentelemetry/api >=1.10, and the in-range api bump queued for the later `npm update` left the install failing ERESOLVE. Unscoped and unrelated packages stay on the update. The peer-split mutant (fixture runs only) disables this.
    if (outOfRange.length > 0 && !(MUTANT === 'peer-split' && FIXTURE_ROOT)) {
      const scopeOf = (n: string) => (n.startsWith('@') ? n.split('/')[0] : null);
      const majorOf = (v: string) => parseVersion(v)?.major;
      // Only a bump of the semver major number can change a peer range; a 0.x minor (sdk-node 0.222 -> 0.223) keeps its in-range siblings on the update, which the install-before-update order serves.
      const scopes = new Set<string>();
      for (const p of outOfRange) {
        const scope = scopeOf(p.name);
        if (scope !== null && majorOf(p.current) !== majorOf(p.latest)) scopes.add(scope);
      }
      const folded = inRange.filter((p) => {
        const scope = scopeOf(p.name);
        return scope !== null && scopes.has(scope);
      });
      if (folded.length > 0) {
        inRange = inRange.filter((p) => !folded.includes(p));
        outOfRange = [...outOfRange, ...folded];
      }
    }
    if (inRange.length > 0) {
      // The split-update mutant (fixture runs only, see MUTANTS) keys the group per manifest, which is the planner this replaced.
      const key = MUTANT === 'split-update' && FIXTURE_ROOT ? `${cwd}\0${workspace ?? ''}` : cwd;
      const group = updates.get(key) ?? {
        cwd,
        label: cwd === root && !(MUTANT === 'split-update' && FIXTURE_ROOT) ? 'root' : label,
        workspaces: [],
        root: false,
        checks: [],
      };
      if (workspace) group.workspaces.push(workspace);
      else group.root = true;
      for (const pkg of inRange) group.checks.push({ pkg, workspace });
      updates.set(key, group);
    }
    // AN EXACT PIN IS KEPT (worklist #22aa3ff6). `npm install name@x` saves `^x` whatever the manifest declared, so on 2026-10-14 private/account's exact `zod: "4.6.5"` came back as `^4.6.7`. An exact pin installs in its own step with --save-exact. Every other out-of-range package (a caret, a tilde, a comparator) installs with npm's default prefix, so a `~x` or `>=x` range is rewritten to `^x`; the selftest pins that such a package installs WITHOUT `--save-exact`.
    const exact = outOfRange.filter((p) => EXACT_VERSION_RE.test(ranges[p.name] ?? ''));
    const ranged = outOfRange.filter((p) => !exact.includes(p));
    for (const [group, extra] of [
      [ranged, []],
      [exact, ['--save-exact']],
    ] as const) {
      if (group.length === 0) continue;
      installs.push({
        cwd,
        args: ['install', ...flags, ...extra, ...group.map(spec)],
        label: `${label} (install)`,
        packages: group,
      });
    }
  };

  const byWorkspace = new Map<string, PackageInfo[]>();
  const rootDeclared: PackageInfo[] = [];
  const rootRanges = readDeclaredRanges(root);
  for (const pkg of rootPackages) {
    const workspaces = findWorkspacesWithPackage(pkg.name, root);
    // EVERY MANIFEST THAT DECLARES IT. A package the root declares AND a workspace declares used to go to the workspaces only: on 2026-09-26 packages/cli's tsx became ^4.23.15 while the root's stayed ^4.21.0 (locked 4.22.1), and the gate stayed red until a hand bump.
    if (workspaces.length === 0 || rootRanges[pkg.name] !== undefined) rootDeclared.push(pkg);
    for (const ws of workspaces) {
      const existing = byWorkspace.get(ws) ?? [];
      existing.push(pkg);
      byWorkspace.set(ws, existing);
    }
  }
  for (const [ws, pkgs] of byWorkspace) {
    plan(
      root,
      path.join(root, 'packages', ws),
      [`-w=packages/${ws}`],
      `packages/${ws}`,
      pkgs,
      `packages/${ws}`
    );
  }
  if (rootDeclared.length > 0) plan(root, root, [], 'root', rootDeclared);
  for (const { dir, name, packages } of privateGroups) {
    if (packages.length === 0) continue;
    plan(dir, dir, [], name, packages);
  }
  const updateSteps: InstallStep[] = [];
  for (const { cwd, label, workspaces, root: withRoot, checks } of updates.values()) {
    const wsFlags = [...new Set(workspaces)].sort().map((ws) => `-w=${ws}`);
    const names = [...new Set(checks.map((c) => c.pkg.name))];
    updateSteps.push({
      cwd,
      args: [
        'update',
        ...wsFlags,
        ...(wsFlags.length > 0 && withRoot ? ['--include-workspace-root'] : []),
        ...names,
      ],
      label: `${label} (update)`,
      packages: names.map((n) => checks.find((c) => c.pkg.name === n)!.pkg),
      checks,
    });
  }
  if (MUTANT === 'update-first' && FIXTURE_ROOT) {
    // The update-first mutant (fixture runs only, see MUTANTS): every update, then every install, the order this replaced.
    steps.push(...updateSteps, ...installs);
  } else {
    for (const cwd of cwdOrder) {
      steps.push(...installs.filter((st) => st.cwd === cwd));
      steps.push(...updateSteps.filter((st) => st.cwd === cwd));
    }
  }
  const finish = (all: InstallStep[]): InstallStep[] => {
    if (beforeMs === null) return all;
    const flag = `--before=${new Date(beforeMs).toISOString()}`;
    return all.map((st) => (st.refused ? st : { ...st, args: [...st.args, flag] }));
  };
  for (const { cwd, label, pkg, value, problems } of overridden.values()) {
    const file = path.join(cwd, 'package.json');
    if (problems.length > 0) {
      const dirRel = path.relative(root, cwd) || '.';
      steps.push({
        cwd,
        args: [],
        label: `${label} (override)`,
        packages: [pkg],
        refused: `${[...new Set(problems)].join('; ')}. Move the override (and its _overridesReasons note) and any declared range by hand, then run \`npm update ${pkg.name}\` in ${dirRel}.`,
      });
      continue;
    }
    steps.push({
      cwd,
      args: ['update', pkg.name],
      label: `${label} (override)`,
      packages: [pkg],
      overrideBump: { file, name: pkg.name, from: value, to: pkg.latest },
    });
  }
  return finish(steps);
}
