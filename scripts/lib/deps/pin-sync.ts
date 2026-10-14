import fs from 'node:fs';
import path from 'node:path';
import { BLUE, NC, RED } from '../console.js';
import { type InstallStep, readDeclaredRanges } from './plan.js';
import {
  CONSOLE_ROOT,
  compareVersions,
  FIXTURE_ROOT,
  MUTANT,
  releaseLine,
  syncpackSourceDirs,
} from './shared.js';

const SYNCPACK_RC = path.join(CONSOLE_ROOT, '.syncpackrc.json');
const SYNCPACK_PIN_RE = /^\^(\d+\.\d+\.\d+)$/;

/**
 * Move the `pinVersion` of every .syncpackrc.json versionGroup whose literal `dependencies` include a package the upgrade moved (worklist #3b831146: on 2026-10-08 --upgrade took @opentelemetry 0.222 -> 0.223 and left the "0.x line in lockstep" group at ^0.222.0, so check:version failed on the next run). `moved` maps a package to the version the upgrade installed; `declared` is the dependency ranges of each source manifest. Pure, so the selftest drives it without a file.
 *
 * Refuses (an error, no text) a rc file that is not in the exact form it would rewrite (JSON.stringify two-space plus a trailing newline), a pin that is not a plain caret range, and a group whose members do not all sit on the moved line: a member the manifests declare that did not move (or whose range this gate cannot read) is named as a laggard, because pinning the group would only trade one syncpack failure for another. Glob entries in `dependencies` are not expanded: only literal names are synced, and a caret-pinned group whose glob entry covers a package that moved past the pin is an error naming the group (a hand edit), never a silent skip. The group `label` is never touched (check-syncpack-reasons.ts keys on it).
 */
function globToRegExp(glob: string): RegExp {
  const body = glob
    .split(/([*?])/)
    .map((part) =>
      part === '*' ? '.*' : part === '?' ? '.' : part.replace(/[.+^${}()|[\]\\]/g, '\\$&')
    )
    .join('');
  return new RegExp(`^${body}$`);
}

export function planPinSync(
  text: string,
  moved: Map<string, string>,
  declared: Record<string, string>[]
): { text: string | null; groups: number; involved: number; rewrites: string[]; errors: string[] } {
  const out = {
    text: null as string | null,
    groups: 0,
    involved: 0,
    rewrites: [] as string[],
    errors: [] as string[],
  };
  let rc: { versionGroups?: Record<string, unknown>[] };
  try {
    rc = JSON.parse(text) as typeof rc;
  } catch (e) {
    out.errors.push(`.syncpackrc.json is not valid JSON: ${(e as Error).message}`);
    return out;
  }
  const groups = rc.versionGroups ?? [];
  out.groups = groups.length;
  groups.forEach((group, i) => {
    const pin = group.pinVersion;
    const deps = group.dependencies;
    if (typeof pin !== 'string' || !Array.isArray(deps)) return;
    const members = deps.filter((d): d is string => typeof d === 'string' && !/[*?!]/.test(d));
    const movedMembers = members.filter((d) => moved.has(d));
    const label = typeof group.label === 'string' ? group.label : `versionGroups[${i}]`;
    const globs = deps.filter(
      (d): d is string => typeof d === 'string' && /[*?]/.test(d) && !d.startsWith('!')
    );
    // Literal members are handled by the rewrite below, so a glob entry only matters for a moved package it covers that no literal entry names.
    const globMoved = [...moved.keys()].filter(
      (name) => !members.includes(name) && globs.some((g) => globToRegExp(g).test(name))
    );
    // A glob entry cannot be expanded against the manifests here, so a moved package it covers past the pin (or past the line a literal member moves it to) is named for a hand edit, whether or not the group also has a moved literal member; a group pinned to anything but a caret range (a `*` group) holds no line to keep.
    const gm = pin.match(SYNCPACK_PIN_RE);
    const pinLine = movedMembers.reduce<string | null>(
      (a, d) => {
        const v = moved.get(d) as string;
        return a === null || compareVersions(v, a) > 0 ? v : a;
      },
      gm ? gm[1] : null
    );
    const globBest = globMoved.reduce<string | null>(
      (a, n) =>
        a === null || compareVersions(moved.get(n) as string, a) > 0 ? (moved.get(n) as string) : a,
      null
    );
    const globPast =
      gm !== null &&
      globBest !== null &&
      pinLine !== null &&
      compareVersions(globBest, pinLine) > 0;
    if (globPast) {
      out.involved++;
      out.errors.push(
        `group "${label}" covers ${globMoved.map((n) => `${n}@${moved.get(n)}`).join(', ')} through a glob entry, which is not expanded, so its pin ${pin} is not moved${movedMembers.length > 0 ? ` (its literal members ${movedMembers.map((n) => `${n}@${moved.get(n)}`).join(', ')} moved too, and are not rewritten either)` : ''}; set its pinVersion by hand`
      );
    }
    if (movedMembers.length === 0) return;
    if (globPast) return;
    out.involved++;
    const m = pin.match(SYNCPACK_PIN_RE);
    if (!m) {
      out.errors.push(
        `group "${label}" pins "${pin}", which is not a plain caret range, so it is not rewritten blind; set its pinVersion by hand to the line ${movedMembers.map((d) => `${d}@${moved.get(d)}`).join(', ')} moved to`
      );
      return;
    }
    const lines = new Map<string, string[]>();
    const note = (line: string | null, who: string) => {
      const key = line ?? 'unreadable';
      lines.set(key, [...(lines.get(key) ?? []), who]);
    };
    for (const d of members) {
      const target = moved.get(d);
      if (target !== undefined) {
        note(releaseLine(target), `${d}@${target} (moved)`);
        continue;
      }
      for (const ranges of declared) {
        const range = ranges[d];
        if (range === undefined) continue;
        const base = range.match(/^[\^~]?(\d+\.\d+\.\d+)$/);
        note(base ? releaseLine(base[1]) : null, `${d} "${range}" (not moved)`);
      }
    }
    if (lines.size > 1) {
      const [first, ...rest] = [...lines.entries()].sort((a, b) => b[1].length - a[1].length);
      out.errors.push(
        `group "${label}" has members on different lines, so its pin ${pin} is not moved: ${first[1].join(', ')} vs ${rest.map(([, who]) => who.join(', ')).join('; ')}. Move the laggards to the same line (or allow-list them), then re-run.`
      );
      return;
    }
    const best = movedMembers
      .map((d) => moved.get(d) as string)
      .reduce((a, b) => (compareVersions(a, b) >= 0 ? a : b));
    const next = `^${best}`;
    if (next === pin || compareVersions(best, m[1]) < 0) return;
    group.pinVersion = next;
    out.rewrites.push(`group "${label}": pinVersion "${pin}" -> "${next}"`);
  });
  if (out.rewrites.length > 0) {
    const fresh = JSON.parse(text) as unknown;
    if (`${JSON.stringify(fresh, null, 2)}\n` !== text) {
      out.errors.push(
        '.syncpackrc.json is not in the two-space JSON form, so its pin groups are not rewritten blind; set each pinVersion above by hand'
      );
      return out;
    }
    out.text = `${JSON.stringify(rc, null, 2)}\n`;
  }
  return out;
}

/**
 * After a successful --upgrade, bring the syncpack pin groups along with the packages the steps moved. Returns false (naming each group) when a group cannot be moved safely, so the run stays red instead of leaving check:version to fail later.
 */
export function syncPinGroups(steps: InstallStep[]): boolean {
  const moved = new Map<string, string>();
  for (const step of steps) {
    if (step.refused) continue;
    for (const p of step.packages) {
      const prev = moved.get(p.name);
      if (prev === undefined || compareVersions(p.latest, prev) > 0) moved.set(p.name, p.latest);
    }
  }
  if (moved.size === 0) return true;
  if (MUTANT === 'skip-pin-sync') return true;
  let text: string;
  try {
    text = fs.readFileSync(SYNCPACK_RC, 'utf-8');
  } catch (e) {
    if (FIXTURE_ROOT) return true;
    console.error(
      `${RED}✗${NC} cannot read .syncpackrc.json to move its pin groups: ${(e as Error).message}`
    );
    return false;
  }
  const plan = planPinSync(text, moved, syncpackSourceDirs().map(readDeclaredRanges));
  // A plan with no text rewrote nothing (it carries only errors), so it neither prints nor counts rewrites it did not make.
  const written = plan.text !== null ? plan.rewrites : [];
  // tree-write: safe reached only from check-deps --upgrade (syncPinGroups after executeInstalls), never from the gate run
  if (plan.text !== null) fs.writeFileSync(SYNCPACK_RC, plan.text);
  console.log(
    `\n${BLUE}syncpack pin groups:${NC} ${plan.groups} groups, ${plan.involved} hold a moved package, ${written.length} rewritten`
  );
  for (const r of written) console.log(`  .syncpackrc.json ${r}`);
  if (plan.errors.length === 0) return true;
  console.error(
    `${RED}✗${NC} ${plan.errors.length} syncpack pin group(s) not moved (check:version stays red until each is):`
  );
  for (const e of plan.errors) console.error(`  ${e}`);
  return false;
}
