/**
 * The composition rule for every shrink-only baseline in this repo.
 *
 * WHY THIS EXISTS. Seven gates here freeze a backlog and call it shrink-only. Every one of
 * them enforced that claim on the READ path only: a new finding fails, a fixed-but-still-
 * baselined finding fails until it is drained. The WRITE path, `--write-baseline`, was an
 * unconditional reseed in all seven. Those are different claims and the gap between them is
 * silent:
 *
 *   shrink-only, as enforced:  the TOTAL cannot grow without someone noticing.
 *   shrink-only, as promised:  the SET can only lose members.
 *
 * A reseed that drains thirty findings and adds one satisfies the first and violates the
 * second, and it prints a smaller number while doing it, so it reads as progress. That is
 * not hypothetical. A drain on this repo's own data printed `2,189 -> 2,160` and went green;
 * the set diff showed 30 removed and ONE ADDED, a violation created that same hour. A later
 * drain of the em-dash baseline (2,876 -> 2,844) was caught only because the session
 * snapshotted the file first and diffed by hand. The next person will not, and the first
 * real-tree run of this module refused a reseed that would have absorbed two brand new
 * findings a background job had introduced minutes earlier.
 *
 * So the discipline moves out of the runbook and into the code. Comparing SIZES is not the
 * same claim as comparing SETS, and only one of them is the promise on the tin.
 *
 * WHY A SHARED MODULE RATHER THAN SEVEN COPIES. Because it was a class, not an instance. The
 * gate whose header cites another gate as its model for "the baseline only shrinks" was
 * copying a file that did not enforce it either. Seven copies of this logic would be seven
 * chances to drift, and the next gate to copy one of them would inherit whichever copy it
 * happened to land on.
 *
 * WHAT IS DELIBERATELY NOT HERE. There is no `--force`. A blanket override switches the rule
 * off for the whole tree at the exact moment the tree is being rewritten, which is when it
 * matters most. The only permitted growth is a NARROW, NAMED one (see `seed` below), and a
 * gate that has no legitimate way to grow simply never offers it.
 */

/** A finding id that is in the new set and not in the old one, i.e. the set GREW. */
export const baselineAdditions = (
  oldIds: readonly string[],
  newIds: readonly string[],
  seed?: string
): string[] => {
  const known = new Set(oldIds);
  return newIds
    .filter((id) => !known.has(id))
    .filter((id) => {
      if (seed === undefined) return true;
      // Ids are `<path>:<where>`; compare on the path half only. `lastIndexOf` rather than
      // `indexOf` because a Windows-style or colon-bearing `where` would otherwise truncate
      // the path and silently widen the exemption.
      const file = id.slice(0, id.lastIndexOf(':'));
      return !(file === seed || file.startsWith(`${seed}/`));
    });
};

/**
 * The same question for a baseline that records a COUNT PER FILE rather than a set of ids
 * (the P7 backlog shape: `{ "docs/x.md": 3 }`).
 *
 * Growth there has two faces and both must be refused: a file that was not in the table at
 * all, and a file whose allowance goes UP. A set-based check would catch only the first,
 * because the key already exists.
 */
export const countAdditions = (
  oldCounts: Readonly<Record<string, number>>,
  newCounts: Readonly<Record<string, number>>
): string[] =>
  Object.entries(newCounts)
    .filter(([file, n]) => oldCounts[file] === undefined || n > (oldCounts[file] ?? 0))
    .map(([file, n]) =>
      oldCounts[file] === undefined
        ? `${file}: NEW (${n} violation(s))`
        : `${file}: ${oldCounts[file]} -> ${n} (the allowance GREW)`
    )
    .sort();

export type WriteVerdict =
  | { kind: 'missing-baseline' }
  | { kind: 'unknown-seed'; seed: string; known: readonly string[] }
  | { kind: 'would-grow'; added: string[] }
  | null;

/**
 * The complete `--write-baseline` decision. Returns null when the write is allowed.
 *
 * WHY PURE. These refusals only ever fire on a path that REWRITES a live suppression file,
 * so exercising them for real means reseeding real debt, which is the one thing a session
 * must not do casually. Left inline in each gate's `main()`, they would be verified once by
 * hand on the day they were written and trusted forever after. Pulled out here, all four
 * outcomes run in every consuming gate's selftest, on every invocation, in CI included.
 *
 * ORDER IS LOAD-BEARING. `missing-baseline` is decided FIRST because every later rule reads
 * the old set: with no file there is no old set, so the rest would pass vacuously. Deleting
 * the baseline is otherwise the cheapest way to switch this whole module off.
 */
export const writeBaselineVerdict = (input: {
  baselineExists: boolean;
  firstSeedFlag: boolean;
  /** The value of the gate's seed flag, when it offers one. */
  seed?: string;
  /** Legal seed values. Omitted or empty means this gate has NO legitimate grow path. */
  knownSeeds?: readonly string[];
  /** Growth, already computed by the caller via baselineAdditions or countAdditions. */
  additions: readonly string[];
}): WriteVerdict => {
  if (!input.baselineExists && !input.firstSeedFlag) return { kind: 'missing-baseline' };
  if (input.seed !== undefined && !(input.knownSeeds ?? []).includes(input.seed))
    return { kind: 'unknown-seed', seed: input.seed, known: input.knownSeeds ?? [] };
  // A genuine first seed has no previous set, so "it grew" has nothing to mean.
  if (!input.baselineExists) return null;
  return input.additions.length > 0 ? { kind: 'would-grow', added: [...input.additions] } : null;
};

/**
 * The refusal text. Shared so that every gate says the same thing about the same rule, and
 * so the one sentence that actually changes behaviour -- "Do NOT add it to the baseline" --
 * cannot go missing from one of them.
 */
export const renderRefusal = (
  verdict: NonNullable<WriteVerdict>,
  ctx: {
    /** How to name the baseline file in prose. */
    baselineLabel: string;
    /** e.g. 'finding', 'dead class', 'stale pin'. */
    noun: string;
    previousCount: number;
    newCount: number;
    /** Usage line for the seed flag, when the gate offers one. */
    seedHelp?: string;
    /**
     * Set when a gate's ids are derived from TEXT that a human may legitimately rewrite
     * (a CSS selector list, a hashed line). A rewrite re-keys the entry, so the gate sees
     * one id die and another appear, and a blanket reseed would absorb the newcomer.
     */
    rekeyHint?: boolean;
  }
): string => {
  if (verdict.kind === 'missing-baseline')
    return (
      `Refusing to write the baseline: ${ctx.baselineLabel} does not exist.\n` +
      `  With no previous baseline there is nothing to compare against, so all ${ctx.newCount} ` +
      `${ctx.noun}(s)\n  would be recorded as debt with no check on what is among them, and ` +
      `DELETING the file is\n  therefore the cheapest way to defeat this rule. If this really ` +
      `is a first seed, say so:\n  --write-baseline --first-seed. If it is not, restore the ` +
      `file and drain it instead.`
    );

  if (verdict.kind === 'unknown-seed')
    return (
      `Refusing to write the baseline: "${verdict.seed}" is not a permitted seed target.\n` +
      (verdict.known.length > 0
        ? `  Permitted: ${verdict.known.join(', ')}\n`
        : `  This gate has NO legitimate grow path, so no seed target is permitted.\n`) +
      `  A typo here would look like a permitted seed while permitting nothing.`
    );

  return (
    `Refusing to write the baseline: it would GAIN ${verdict.added.length} ${ctx.noun}(s) ` +
    `not in the current one.\n` +
    verdict.added.map((id) => `    ${id}`).join('\n') +
    `\n\n  The baseline shrinks. It never grows. A reseed that drains 30 and adds 1 still\n` +
    `  LOOKS like progress in the totals (${ctx.previousCount} -> ${ctx.newCount}), which is ` +
    `exactly how a brand new\n  violation gets enshrined as permanent, invisible debt.\n\n` +
    `  Fix the value instead. Do NOT add it to ${ctx.baselineLabel}.` +
    (ctx.rekeyHint
      ? `\n\n  If you REWROTE the text an entry is keyed on, the old id dies and a new one is\n` +
        `  born, and this is what that looks like. Hand-edit that single line rather than\n` +
        `  reseeding, which would rewrite every entry and absorb anyone else's fresh findings.`
      : '') +
    (ctx.seedHelp ? `\n  Legitimate exception: ${ctx.seedHelp}` : '')
  );
};

/**
 * The set-math cases, written ONCE and executed by every consuming gate's selftest.
 *
 * Both directions throughout. A one-way proof ("a genuine shrink is allowed") is satisfied
 * by a function that returns [] for everything, which is precisely the no-op this module
 * was written to replace.
 */
/**
 * The WHOLE `--write-baseline` path, in one call.
 *
 * EXTRACTED 2026-09-04, and by the duplication gate rather than by taste: adding a fourth
 * consumer put the read-previous / verdict / refuse / write / log sequence over three
 * copies, in files that had each retyped it. `writeBaselineVerdict` above was already the
 * shared DECISION; this is the shared PLUMBING around it, which is the half that actually
 * gets copied. A consumer that hand-rolls it can still drift -- forgetting the refusal, or
 * logging a smaller number after absorbing an addition -- which is the exact failure the
 * module's own header opens with.
 *
 * Returns true when the baseline was written; on a refusal it prints and returns false, and
 * the caller exits non-zero without writing anything.
 */
export const commitBaseline = (input: {
  path: string;
  label: string;
  noun: string;
  key: string;
  note: string;
  current: readonly string[];
  firstSeed: boolean;
  read: (p: string) => string | null;
  write: (p: string, body: string) => void;
  log?: (line: string) => void;
  err?: (line: string) => void;
}): boolean => {
  const raw = input.read(input.path);
  const had = raw !== null;
  const previous: string[] = had ? (JSON.parse(raw)[input.key] ?? []) : [];
  const verdict = writeBaselineVerdict({
    baselineExists: had,
    firstSeedFlag: input.firstSeed,
    additions: had ? baselineAdditions(previous, [...input.current]) : [],
  });
  if (verdict !== null) {
    (input.err ?? console.error)(
      `\n\u001b[31m\u2717\u001b[0m ${renderRefusal(verdict, {
        baselineLabel: input.label,
        noun: input.noun,
        previousCount: previous.length,
        newCount: input.current.length,
        rekeyHint: false,
      })}`
    );
    return false;
  }
  input.write(
    input.path,
    `${JSON.stringify({ note: input.note, [input.key]: input.current }, null, 2)}\n`
  );
  const drained = previous.filter((f) => !input.current.includes(f)).length;
  (input.log ?? console.log)(
    `baseline written: ${input.current.length} entr(ies) (${previous.length} before, ` +
      `${drained} drained, 0 added)`
  );
  return true;
};

export const sharedSelftestCases = (): { name: string; ok: boolean; detail?: string }[] => {
  const old = ['a.json:k1', 'a.json:k2', 'a.json:k3'];
  const v = (o: Partial<Parameters<typeof writeBaselineVerdict>[0]>) =>
    writeBaselineVerdict({
      baselineExists: true,
      firstSeedFlag: false,
      additions: [],
      ...o,
    });

  return [
    {
      name: 'baseline: a genuine shrink adds nothing',
      ok: baselineAdditions(old, ['a.json:k1', 'a.json:k3']).length === 0,
    },
    {
      name: 'baseline: an identical reseed adds nothing',
      ok: baselineAdditions(old, old).length === 0,
    },
    {
      name: 'baseline CONTROL: draining two and adding one is caught, though the TOTAL shrinks',
      ok: baselineAdditions(old, ['a.json:k1', 'a.json:kNEW']).join() === 'a.json:kNEW',
      detail: JSON.stringify(baselineAdditions(old, ['a.json:k1', 'a.json:kNEW'])),
    },
    {
      name: 'baseline: a seed target permits a new id from THAT path only',
      ok: baselineAdditions(old, [...old, 'new/surface/x.ts:h1'], 'new/surface').length === 0,
    },
    {
      name: 'baseline CONTROL: a seed target does NOT excuse a new id elsewhere',
      ok: baselineAdditions(old, [...old, 'a.json:kNEW'], 'new/surface').join() === 'a.json:kNEW',
      detail: 'a seed that opened the whole tree would be a --force wearing a narrower name',
    },
    {
      name: 'baseline CONTROL: a prefix collision is not mistaken for the seed target',
      ok:
        baselineAdditions(old, [...old, 'new/surface-archive/x.ts:h1'], 'new/surface').length === 1,
      detail: 'prefix matching without the separator would silently widen the exemption',
    },
    {
      name: 'counts: an unchanged table adds nothing',
      ok: countAdditions({ 'a.md': 3 }, { 'a.md': 3 }).length === 0,
    },
    {
      name: 'counts: a ratchet DOWN adds nothing',
      ok: countAdditions({ 'a.md': 3 }, { 'a.md': 1 }).length === 0,
    },
    {
      name: 'counts CONTROL: a file whose allowance GREW is caught',
      ok: countAdditions({ 'a.md': 3 }, { 'a.md': 4 }).length === 1,
      detail: JSON.stringify(countAdditions({ 'a.md': 3 }, { 'a.md': 4 })),
    },
    {
      name: 'counts CONTROL: a file absent from the old table is caught',
      ok: countAdditions({ 'a.md': 3 }, { 'a.md': 3, 'b.md': 1 }).length === 1,
      detail: 'a set-only check would miss this, since the total may still be smaller',
    },
    { name: 'verdict: an unchanged reseed is allowed', ok: v({}) === null },
    {
      name: 'verdict CONTROL: growth is refused',
      ok: v({ additions: ['x'] })?.kind === 'would-grow',
    },
    {
      name: 'verdict: a missing baseline is refused without --first-seed',
      ok: v({ baselineExists: false })?.kind === 'missing-baseline',
      detail: 'deleting the file must not be a way to switch the composition rule off',
    },
    {
      name: 'verdict: --first-seed permits a missing baseline, and ONLY a missing one',
      ok:
        v({ baselineExists: false, firstSeedFlag: true }) === null &&
        v({ firstSeedFlag: true, additions: ['x'] })?.kind === 'would-grow',
      detail: 'the flag must not double as a blanket override when the baseline is present',
    },
    {
      name: 'verdict CONTROL: an unlisted seed target is refused, not silently ignored',
      ok: v({ seed: 'nope', knownSeeds: ['yes'] })?.kind === 'unknown-seed',
    },
    {
      name: 'verdict: a listed seed target is accepted',
      ok: v({ seed: 'yes', knownSeeds: ['yes'] }) === null,
    },
    {
      name: 'verdict CONTROL: a gate with no grow path refuses every seed target',
      ok: v({ seed: 'anything' })?.kind === 'unknown-seed',
      detail: 'knownSeeds omitted means this gate cannot legitimately grow',
    },
  ];
};
