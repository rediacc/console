import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { BLUE, GREEN, NC, RED, YELLOW } from '../console.js';
import type { InstallStep } from './plan.js';
import {
  CONSOLE_ROOT,
  compareVersions,
  type LockEntry,
  MAJOR_ALLOW_REL,
  type PackageInfo,
  parseRange,
  parseVersion,
  printPackage,
  rangeAdmits,
  readLockPackages,
} from './shared.js';

/**
 * Move one `overrides` entry in a package.json, refusing any file it cannot rewrite byte for byte (npm's own two-space form with a trailing newline), so nothing but that one value ever changes. Returns an error line, or null plus an advisory when the `_overridesReasons` note still names the old version. The note itself is never rewritten: it is the human justification check:ci-overrides-reasons enforces, and only a human can say why the new version is the right floor.
 */
function applyOverrideBump(b: NonNullable<InstallStep['overrideBump']>): {
  error: string | null;
  advisory: string | null;
} {
  const rel = path.relative(CONSOLE_ROOT, b.file) || 'package.json';
  let text: string;
  let pkg: { overrides?: Record<string, unknown>; _overridesReasons?: Record<string, unknown> };
  try {
    text = fs.readFileSync(b.file, 'utf-8');
    pkg = JSON.parse(text) as typeof pkg;
  } catch (e) {
    return { error: `cannot read ${rel}: ${(e as Error).message}`, advisory: null };
  }
  if (`${JSON.stringify(pkg, null, 2)}\n` !== text) {
    return {
      error: `${rel} is not in npm's two-space JSON form, so its override is not rewritten blind; set overrides["${b.name}"] to "${b.to}" by hand, then run \`npm update ${b.name}\``,
      advisory: null,
    };
  }
  const overrides = pkg.overrides ?? {};
  const current = overrides[b.name];
  const self =
    typeof current === 'object' && current !== null
      ? (current as Record<string, unknown>)['.']
      : current;
  if (self !== b.from) {
    return {
      error: `${rel} overrides["${b.name}"] is no longer "${b.from}" (it changed after the plan was made); re-run the upgrade`,
      advisory: null,
    };
  }
  if (typeof current === 'object' && current !== null) {
    (current as Record<string, unknown>)['.'] = b.to;
  } else {
    overrides[b.name] = b.to;
  }
  fs.writeFileSync(b.file, `${JSON.stringify(pkg, null, 2)}\n`);
  const note = pkg._overridesReasons?.[b.name];
  const advisory =
    typeof note === 'string' && note.includes(b.from)
      ? `${rel} _overridesReasons["${b.name}"] still names ${b.from}; the override is now ${b.to}. Update the note before committing.`
      : null;
  return { error: null, advisory };
}

/**
 * The environment a planned npm step runs in: this process's, minus any inherited npm loglevel. `npm run -s check:deps -- --upgrade` exports `npm_config_loglevel=silent` to this script, and a child npm that inherits it prints NOTHING when it fails; on 2026-09-30 that turned an ERESOLVE into a bare "Some upgrades failed". Without the variable the child falls back to .npmrc or npm's default level, so its own error reaches the terminal.
 */
export function upgradeChildEnv(base: NodeJS.ProcessEnv = process.env): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = { ...base };
  for (const key of Object.keys(env)) {
    if (key.toLowerCase() === 'npm_config_loglevel') delete env[key];
  }
  return env;
}

/**
 * FRESHNESS-WINDOW GUARD for `npm update`. That verb takes the highest version the declared range allows, so a version published after this run's release-age check (.ci/config/release-age.json) could land without ever being judged, which is exactly the smash-and-grab release the window exists to stop. After an `(update)` step, every (package, declaring workspace) pair in it must resolve in the step's lockfile to the EXACT version the gate judged: the workspace's nested copy (`packages/<ws>/node_modules/<name>`) when npm placed one there, else the hoisted `node_modules/<name>`. Returns one line per package that does not, empty when all match. Pure, so the selftest drives it directly.
 */
export function verifyUpdatedVersions(
  step: InstallStep,
  lock: Record<string, LockEntry> | null
): string[] {
  return updateMismatches(step, lock).map((m) => m.line);
}

/**
 * The installed copies in `lock` whose own declared range for `name` admits the version npm kept but not the judged one, as `<name>@<version> requires "<range>"`. This is how an exact-pinning sibling shows up: @opentelemetry/sdk-node@0.222.0 requires @opentelemetry/core "2.11.0", so no `npm update` of core can reach 2.12.0 while that sdk-node is installed. Pure, so the selftest drives it directly.
 */
export function pinningHolders(
  lock: Record<string, LockEntry> | null,
  name: string,
  kept: string,
  judged: string
): string[] {
  const out: string[] = [];
  for (const [key, entry] of Object.entries(lock ?? {})) {
    const holder = key.slice(key.lastIndexOf('node_modules/') + 'node_modules/'.length);
    if (!key.includes('node_modules/') || holder === name) continue;
    for (const deps of [entry.dependencies, entry.optionalDependencies, entry.peerDependencies]) {
      const range = deps?.[name];
      if (range === undefined) continue;
      const sets = parseRange(range);
      if (sets && rangeAdmits(sets, kept) && !rangeAdmits(sets, judged)) {
        out.push(`${holder}@${entry.version ?? '?'} requires "${range}"`);
      }
    }
  }
  return [...new Set(out)];
}

/**
 * Every checked package of an `(update)` step that did not resolve to its judged version, split by what that means. `held` is a package npm left on an OLDER version than judged: nothing unjudged landed, the update simply could not move it, and `holders` names the installed copies whose declared range pins it (pinningHolders). Anything else (a newer version, or a package missing from the lockfile) is a freshness-window breach.
 */
export function updateMismatches(
  step: InstallStep,
  lock: Record<string, LockEntry> | null
): Array<{ line: string; held: boolean }> {
  const out: Array<{ line: string; held: boolean }> = [];
  const seen = new Set<string>();
  const checks: Array<{ pkg: PackageInfo; workspace?: string }> =
    step.checks ?? step.packages.map((p) => ({ pkg: p }));
  for (const { pkg, workspace } of checks) {
    const nested = workspace ? lock?.[`${workspace}/node_modules/${pkg.name}`] : undefined;
    const resolved = (nested ?? lock?.[`node_modules/${pkg.name}`])?.version;
    if (resolved === pkg.latest) continue;
    const held =
      resolved !== undefined &&
      parseVersion(resolved) !== null &&
      parseVersion(pkg.latest) !== null &&
      compareVersions(resolved, pkg.latest) < 0;
    const holders = held ? pinningHolders(lock, pkg.name, resolved, pkg.latest) : [];
    const line =
      `${pkg.name}: judged ${pkg.latest}, installed ${resolved ?? '<not in package-lock.json>'}${nested ? ` (nested in ${workspace})` : ''}` +
      (held
        ? holders.length > 0
          ? `; held back by ${holders.join(', ')}`
          : "; held back, and no installed copy in package-lock.json pins it, so npm's own output above is the reason"
        : '');
    if (seen.has(line)) continue;
    seen.add(line);
    out.push({ line, held });
  }
  return out;
}

/** Run the planned steps, printing what each one takes, and name every step that failed with its exact command and exit status. An `(update)` step that exits 0 still fails when verifyUpdatedVersions finds a version the gate did not judge. */
export function executeInstalls(steps: InstallStep[]): boolean {
  if (steps.length === 0) {
    console.log(`${GREEN}No packages to upgrade${NC}`);
    return true;
  }
  const failures: string[] = [];
  const advisories: string[] = [];
  const env = upgradeChildEnv();
  for (const step of steps) {
    if (step.refused) {
      failures.push(
        `  ${step.label}: ${step.packages.map((p) => `${p.name} ${p.current} -> ${p.latest}`).join(', ')} not applied: ${step.refused}`
      );
      continue;
    }
    console.log(`${BLUE}Upgrading ${step.packages.length} package(s) in ${step.label}...${NC}`);
    console.log(`  \`npm ${step.args.join(' ')}\`\n`);
    for (const pkg of step.packages) printPackage(pkg);
    console.log();
    if (step.overrideBump) {
      const b = step.overrideBump;
      const bumped = applyOverrideBump(b);
      if (bumped.error) {
        failures.push(`  ${step.label}: ${bumped.error}`);
        continue;
      }
      console.log(
        `  overrides["${b.name}"]: "${b.from}" -> "${b.to}" in ${path.relative(CONSOLE_ROOT, b.file) || 'package.json'}\n`
      );
      if (bumped.advisory) advisories.push(bumped.advisory);
    }
    const result = spawnSync('npm', step.args, {
      cwd: step.cwd,
      stdio: 'inherit',
      shell: true,
      env,
    });
    if (result.status !== 0) {
      const why = result.error
        ? `could not start: ${result.error.message}`
        : result.signal
          ? `killed by ${result.signal}`
          : `exit status ${result.status}`;
      failures.push(
        `  ${step.label}: \`npm ${step.args.join(' ')}\` in ${path.relative(CONSOLE_ROOT, step.cwd) || '.'} (${why})` +
          (step.overrideBump
            ? `; overrides["${step.overrideBump.name}"] was already moved to "${step.overrideBump.to}", so package.json and the lockfile disagree until it succeeds`
            : '')
      );
      continue;
    }
    if (step.args[0] !== 'update') continue;
    const mismatches = updateMismatches(step, readLockPackages(step.cwd));
    const stepRef = `${step.label}: \`npm ${step.args.join(' ')}\` in ${path.relative(CONSOLE_ROOT, step.cwd) || '.'}`;
    const unjudged = mismatches.filter((m) => !m.held);
    const heldBack = mismatches.filter((m) => m.held);
    if (unjudged.length > 0) {
      failures.push(
        `  ${stepRef} resolved a version the gate did not judge (freshness-window guard, .ci/config/release-age.json):\n` +
          unjudged.map((m) => `      ${m.line}`).join('\n') +
          '\n    package.json and package-lock.json in that directory now hold the unjudged version; revert them there before committing.'
      );
    }
    if (heldBack.length > 0) {
      failures.push(
        `  ${stepRef} left ${heldBack.length} package(s) below the judged version (npm kept the installed one, so nothing unjudged landed):\n` +
          heldBack.map((m) => `      ${m.line}`).join('\n') +
          `\n    A package an installed sibling pins exactly moves only with that sibling: take the sibling's bump (an allow entry in ${MAJOR_ALLOW_REL} when it is a held major, which --upgrade installs before this update), or wait for a sibling release that admits the judged version.`
      );
    }
  }
  for (const a of advisories) console.log(`\n${YELLOW}${a}${NC}`);
  if (failures.length === 0) {
    console.log(`\n${GREEN}Upgrades completed${NC}`);
    return true;
  }
  console.error(`\n${RED}✗${NC} ${failures.length} of ${steps.length} upgrade step(s) failed:`);
  for (const f of failures) console.error(f);
  console.error(
    '  The npm error for each is printed above its step; re-run that command to see it again.'
  );
  return false;
}
