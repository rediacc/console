import type { InstallStep } from './plan.js';
import {
  compareVersions,
  type LockEntry,
  type PackageInfo,
  parseRange,
  parseVersion,
  rangeAdmits,
} from './shared.js';

/**
 * Plan the move of one `overrides` entry in a package.json's text, refusing any file it cannot rewrite byte for byte (npm's own two-space form with a trailing newline), so nothing but that one value ever changes. Pure: it returns the new text and never writes (the pins transaction writes it, journaled). `after` is null when the move is refused, with the reason in `error`. The advisory is set when the `_overridesReasons` note still names the old version; the note itself is never rewritten, since it is the human justification check:ci-overrides-reasons enforces and only a human can say why the new version is the right floor.
 */
export function planOverrideBump(
  text: string,
  b: { name: string; from: string; to: string },
  rel: string
): { after: string | null; error: string | null; advisory: string | null } {
  let pkg: { overrides?: Record<string, unknown>; _overridesReasons?: Record<string, unknown> };
  try {
    pkg = JSON.parse(text) as typeof pkg;
  } catch (e) {
    return { after: null, error: `cannot read ${rel}: ${(e as Error).message}`, advisory: null };
  }
  if (`${JSON.stringify(pkg, null, 2)}\n` !== text) {
    return {
      after: null,
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
      after: null,
      error: `${rel} overrides["${b.name}"] is no longer "${b.from}" (it changed after the plan was made); re-run the plan`,
      advisory: null,
    };
  }
  if (typeof current === 'object' && current !== null) {
    (current as Record<string, unknown>)['.'] = b.to;
  } else {
    overrides[b.name] = b.to;
  }
  const note = pkg._overridesReasons?.[b.name];
  const advisory =
    typeof note === 'string' && note.includes(b.from)
      ? `${rel} _overridesReasons["${b.name}"] still names ${b.from}; the override is now ${b.to}. Update the note before committing.`
      : null;
  return { after: `${JSON.stringify(pkg, null, 2)}\n`, error: null, advisory };
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
