/**
 * The other version sites of a registry pin follow a package the npm driver moved (worklist
 * #43aebb3a). `bump npm` moved wrangler in workers/account/package.json from 4.164.0 to 4.165.0
 * and left .ci/config/constants.sh WRANGLER_VERSION at 4.164.0, so `check:ci-pin-registry` went
 * red after the bump's own gates (check:deps, check:ci-lockfile, check:version) had passed.
 *
 * A registry leaf whose `source.package` is a moved package, whose sites all carry the `version`
 * role, and one of whose sites is a package.json (the anchor `npm update` moved) has every
 * other site rewritten to the anchor's value, in the same transaction. Pure apart from the
 * reads the caller supplies.
 */
import path from 'node:path';
import { type DriverContext, type FileWrite, planLeafSites } from '../driver.js';
import { type PinEntry, type PinRegistry, type PinSite, siteMatches } from '../registry.js';

const isAnchor = (s: PinSite): boolean => path.posix.basename(s.file) === 'package.json';

/** The leaves a moved package drags: every site `version`, at least two sites, one of them a package.json. */
export function followers(reg: PinRegistry, moved: ReadonlySet<string>): PinEntry[] {
  return reg.entries.filter(
    (e) =>
      e.kind === 'leaf' &&
      e.source.package !== undefined &&
      moved.has(e.source.package) &&
      e.sites.length > 1 &&
      e.sites.every((s) => s.role === 'version') &&
      e.sites.some(isAnchor)
  );
}

/** The files a follower rewrites: every site but the anchors, declared in the step before it runs. */
export function followWrites(entries: PinEntry[]): Array<{ repo: string; file: string }> {
  return entries.flatMap((e) =>
    e.sites.filter((s) => !isAnchor(s)).map((s) => ({ repo: s.repo, file: s.file }))
  );
}

/** The rewrites that bring each follower's sites to its anchor's value; throws when an anchor is not a plain version. */
export function planFollow(
  entries: PinEntry[],
  ctx: DriverContext
): { writes: FileWrite[]; changes: string[] } {
  const writes: FileWrite[] = [];
  const changes: string[] = [];
  for (const e of entries) {
    const anchor = e.sites.find(isAnchor) as PinSite;
    const text = ctx.read(anchor);
    const value = text === null ? undefined : siteMatches(anchor, text)[0]?.value;
    if (value === undefined || !/^\d+\.\d+\.\d+$/.test(value))
      throw new Error(
        `${e.id}: the anchor site ${anchor.file} holds ${value ?? 'no match'}, not a plain version the other sites can follow`
      );
    const p = planLeafSites(e, { version: value }, ctx);
    for (const w of p.writes) if (ctx.read(w) !== w.after) writes.push(w);
    changes.push(...p.changes.filter((c) => !c.includes(` ${value} -> ${value}`)));
  }
  return { writes, changes };
}
