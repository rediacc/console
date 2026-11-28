/**
 * The carried-reds.json half of the record-only advance decision (PLAN-ciquick-gate-contract R1), the twin of
 * .claude/rediacc_hooks/guards/block_unverified_push.py `parse_carry_doc`, `carried_widening`, `removed_still_red`
 * and `carry_step_problem`. A step that touches `.ci/config/carried-reds.json` advances only when it touches that
 * file alone and SHRINKS it: the push guard refuses any other carry-file step, so the runner must not write one.
 * Pure. scripts/ci-runner/advance-parity.json pins both halves on one corpus (run.ts --selftest here,
 * .claude/rediacc_hooks/guards/test-block_unverified_push.py (PARITY cases) there).
 */

export const CARRIED_REL = '.ci/config/carried-reds.json';
/** block_unverified_push REASON_MIN / STAR_REASON_MIN: an entry whose reason is shorter carries nothing. */
const REASON_MIN = 80;
const STAR_REASON_MIN = 160;
const EXPIRES_RE = /^\d{4}-\d{2}-\d{2}$/;

/** The effective carry: keyed and whole-gate entries, and each gate's finding patterns with their expiry. */
export interface CarryDoc {
  carried: Record<string, Set<string> | '*'>;
  patterns: Record<string, Record<string, string>>;
}

/** A finding-key pattern: `*` is any run of characters, everything else literal (`carry_pattern_re`). */
export function carryPatternRe(glob: string): RegExp {
  const body = [...glob]
    .map((ch) => (ch === '*' ? '.*' : ch.replace(/[.+?^${}()|[\]\\/-]/g, '\\$&')))
    .join('');
  return new RegExp(`^${body}$`, 's');
}

function patternCovers(key: string, globs: readonly string[]): boolean {
  return globs.some((g) => carryPatternRe(g).test(key));
}

/** carried-reds.json text -> the effective carry, or a sentence saying why it is a schema error (`parse_carry_doc`). */
export function parseCarryDoc(text: string): CarryDoc | string {
  let doc: unknown;
  try {
    doc = JSON.parse(text);
  } catch (e) {
    return `carried-reds.json does not parse as JSON: ${(e as Error).message.slice(0, 120)}`;
  }
  const d = doc as { version?: unknown; carried?: unknown } | null;
  if (d === null || typeof d !== 'object' || Array.isArray(d) || d.version !== 2)
    return 'carried-reds.json is not `"version": 2`.';
  if (!Array.isArray(d.carried)) return 'carried-reds.json has no `carried` list.';
  const carried: CarryDoc['carried'] = {};
  const patterns: CarryDoc['patterns'] = {};
  const shapes = new Map<string, string>();
  for (const [i, raw] of d.carried.entries()) {
    const e = (raw !== null && typeof raw === 'object' && !Array.isArray(raw) ? raw : {}) as Record<
      string,
      unknown
    >;
    const gate = e.gate;
    if (typeof gate !== 'string' || gate === '')
      return `carried-reds.json entry ${i} names no gate.`;
    const findings = e.findings;
    const globs = e.patterns;
    let shape: string;
    if (globs !== undefined && globs !== null) {
      if (findings !== undefined && findings !== null)
        return `carried-reds.json entry ${i} (${gate}) has both \`findings\` and \`patterns\`.`;
      if (
        !Array.isArray(globs) ||
        globs.length === 0 ||
        !globs.every((g) => typeof g === 'string' && g !== '')
      )
        return `carried-reds.json entry ${i} (${gate}) has an empty or non-string \`patterns\`.`;
      // A match-all pattern is a whole-gate carry (block_unverified_push parse_carry_doc, review f3d07ec8.2).
      if ((globs as string[]).some((g) => /^\*+$/.test(g)))
        return `carried-reds.json entry ${i} (${gate}) has a pattern that matches every finding key.`;
      if (typeof e.expires !== 'string' || !EXPIRES_RE.test(e.expires))
        return `carried-reds.json entry ${i} (${gate}) carries finding patterns with no \`expires\` date.`;
      shape = 'keys';
    } else if (findings === '*') shape = '*';
    else if (
      Array.isArray(findings) &&
      findings.length > 0 &&
      findings.every((k) => typeof k === 'string' && k !== '')
    )
      shape = 'keys';
    else return `carried-reds.json entry ${i} (${gate}) has no \`findings\`.`;
    if ((shapes.get(gate) ?? shape) !== shape)
      return `${gate} is carried both by "*" and by keys or patterns.`;
    shapes.set(gate, shape);
    const reason = typeof e.reason === 'string' ? e.reason : '';
    // Code points, as Python's len() counts them.
    if ([...reason].length < (shape === '*' ? STAR_REASON_MIN : REASON_MIN)) continue;
    if (globs !== undefined && globs !== null) {
      const mine = (patterns[gate] ??= {});
      for (const g of globs as string[]) {
        const was = mine[g] ?? '';
        mine[g] = was > (e.expires as string) ? was : (e.expires as string);
      }
      continue;
    }
    if (shape === '*') {
      carried[gate] = '*';
      continue;
    }
    const prev = carried[gate];
    const keys = prev instanceof Set ? prev : new Set<string>();
    for (const k of findings as string[]) keys.add(k);
    carried[gate] = keys;
  }
  return { carried, patterns };
}

const byCode = (a: string, b: string): number => Number(a > b) - Number(a < b);

/** Every way `next` excuses more than `prev` (`carried_widening`). */
export function carriedWidening(prev: CarryDoc, next: CarryDoc): string[] {
  const out: string[] = [];
  for (const gate of Object.keys(next.carried).sort(byCode)) {
    const was = prev.carried[gate];
    const now = next.carried[gate];
    if (was === undefined) out.push(`adds a carry for ${gate}`);
    else if ((was === '*') !== (now === '*')) out.push(`switches ${gate} between "*" and keys`);
    else if (now instanceof Set && was instanceof Set) {
      const added = [...now].filter((k) => !was.has(k)).sort(byCode);
      if (added.length > 0) out.push(`adds key(s) to ${gate}: ${added.join(', ')}`);
    }
  }
  for (const gate of Object.keys(next.patterns).sort(byCode)) {
    const was = prev.patterns[gate] ?? {};
    for (const [glob, exp] of Object.entries(next.patterns[gate]).sort(([a], [b]) =>
      byCode(a, b)
    )) {
      if (!(glob in was)) out.push(`adds pattern ${glob} to ${gate}`);
      else if (exp > was[glob]) out.push(`extends pattern ${glob} of ${gate} to ${exp}`);
    }
  }
  return out;
}

/** What the receipt says is red: its failed gates and their finding keys. */
export interface Judged {
  failed: ReadonlySet<string>;
  findings: Record<string, unknown>;
}

/** Every excuse `prev` holds and `next` drops that still covers a red in the receipt (`removed_still_red`). */
export function removedStillRed(prev: CarryDoc, next: CarryDoc, judged: Judged): string[] {
  const out: string[] = [];
  for (const gate of Object.keys(prev.carried).sort(byCode)) {
    const was = prev.carried[gate];
    const now = next.carried[gate];
    if (!judged.failed.has(gate)) continue;
    if (was === '*') {
      if (now === undefined) out.push(`${gate} (its whole-gate carry)`);
      continue;
    }
    const dropped =
      now instanceof Set ? [...was].filter((k) => !now.has(k)) : now === undefined ? [...was] : [];
    if (dropped.length === 0) continue;
    const emitted = judged.findings[gate];
    if (!Array.isArray(emitted)) {
      out.push(
        `${gate} (the receipt records no finding keys to show ${dropped.sort(byCode).join(', ')} gone)`
      );
      continue;
    }
    const hit = dropped.filter((k) => emitted.includes(k)).sort(byCode);
    if (hit.length > 0) out.push(`${gate}: ${hit.join(', ')}`);
  }
  for (const gate of Object.keys(prev.patterns).sort(byCode)) {
    if (!judged.failed.has(gate)) continue;
    const kept = next.patterns[gate] ?? {};
    const dropped = Object.keys(prev.patterns[gate])
      .filter((g) => !(g in kept))
      .sort(byCode);
    if (dropped.length === 0) continue;
    const emitted = judged.findings[gate];
    if (!Array.isArray(emitted)) {
      out.push(
        `${gate} (the receipt records no finding keys to show pattern(s) ${dropped.join(', ')} unused)`
      );
      continue;
    }
    const keys =
      next.carried[gate] instanceof Set ? (next.carried[gate] as Set<string>) : new Set();
    const hit = [
      ...new Set(
        emitted.filter(
          (k): k is string =>
            typeof k === 'string' &&
            patternCovers(k, dropped) &&
            !keys.has(k) &&
            !patternCovers(k, Object.keys(kept))
        )
      ),
    ].sort(byCode);
    if (hit.length > 0) out.push(`${gate}: ${hit.join(', ')}`);
  }
  return out;
}

/** Why a step touching carried-reds.json is not a shrink of it, else undefined (`carry_step_problem` plus the guard-side wording of `plan_advance`). `textAt` answers the file's text at a tree, undefined when the tree has none. */
export function carryStepProblem(
  paths: readonly string[],
  from: string,
  to: string,
  textAt: (tree: string) => string | undefined,
  judged: Judged
): string | undefined {
  const others = paths.filter((p) => p !== CARRIED_REL).sort(byCode);
  if (others.length > 0)
    return `carried-reds.json changed together with other path(s): ${others.join('; ')}.`;
  const read = (tree: string): CarryDoc | string => {
    const text = textAt(tree);
    if (text === undefined) return `tree ${tree.slice(0, 12)} has no ${CARRIED_REL}`;
    const doc = parseCarryDoc(text);
    return typeof doc === 'string' ? `at tree ${tree.slice(0, 12)}: ${doc}` : doc;
  };
  const prev = read(from);
  const next = typeof prev === 'string' ? prev : read(to);
  if (typeof prev === 'string' || typeof next === 'string')
    return `carried-reds.json cannot be judged a shrink: ${typeof prev === 'string' ? prev : next}.`;
  const widened = carriedWidening(prev, next);
  if (widened.length > 0) return `carried-reds.json widened: ${widened.join('; ')}.`;
  const red = removedStillRed(prev, next, judged);
  if (red.length > 0)
    return `carried-reds.json drops excuses that still cover reds: ${red.join('; ')}.`;
  return undefined;
}
