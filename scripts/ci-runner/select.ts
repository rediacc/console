/**
 * The `--changed` selection contract: fail OPEN on scope, REFUSE on a change set
 * that cannot be trusted.
 *
 * WHY THIS IS A MODULE AND NOT FOUR LINES IN `run.ts`. The two halves below pull in
 * opposite directions and the second one was missing, so the first one looked like the
 * whole design:
 *
 *   FAIL OPEN ON SCOPE. Measured on this tree 2026-09-09 against
 *   scripts/ci-runner/gates.lock.json: 474 entries, 464 with `gate: true`, and exactly
 *   46 of those declare `paths`. 418 gates declare none. Scoping a run by `paths` alone
 *   therefore says nothing about 90% of the estate, so an entry with no `paths` is
 *   selected for EVERY non-empty change set. That rule already existed and is preserved
 *   here verbatim; what did not exist was anything asserting it.
 *
 *   THOSE FOUR NUMBERS ARE A TIMESTAMP, NOT A CONSTANT. They moved to 475/465/46/419
 *   within the hour, from another session's manifest entry. `check:ci-changed-selection`
 *   recomputes them from the lock and prints the shape on every run, which is the only
 *   form of this measurement a reader should trust.
 *
 *   REFUSE AN UNUSABLE CHANGE SET. "Nothing changed" and "the differ broke" arrive in
 *   the same shape -- an empty file list -- and under the fail-open rule above the
 *   empty list is the ONE input for which fail-open silently inverts into fail-closed:
 *   every path-declaring gate is dropped because no file matched it, while the
 *   no-paths gates all survive. The run then reports a green having skipped exactly the
 *   gates that were scoped on purpose.
 *
 * WHAT THAT COST, MEASURED BEFORE THE FIX, on the real invocation:
 *
 *     $ CI_RUNNER_BASE=refs/heads/__no_such_ref__ npx tsx scripts/ci-runner/run.ts --list --changed
 *     ci-runner: --changed could not resolve a merge base against refs/heads/__no_such_ref__; selecting every gate
 *     ... rc=0, 418 `gate` lines
 *
 *   Against 464 on a full `--list`. The warning says "selecting every gate" and the
 *   selection drops 46 of them, so the instrument reported work it had not done -- and
 *   it did so on the exact code path that fires when git is unavailable, which is the
 *   path a CI runner takes on a shallow clone.
 *
 * WHY REFUSAL AND NOT "SELECT EVERYTHING". Selecting everything would be safe and
 * silent, and silence is what let this sit. A caller that asked to be scoped and cannot
 * be told what changed has asked a question with no answer; answering it with a full
 * run hides a broken differ for as long as the machine stays fast enough. The exit code
 * is the signal, and the message names the fix (drop `--changed`, or set
 * `CI_RUNNER_BASE` to a ref that resolves).
 *
 * NAME-SHAPED SCOPE (PLAN-ciquick-cpu W2.4). A gate that declares `lists` or `names` reads tracked NAMES, not content (scripts/ci-runner/input-hash.ts), so it is scoped even with no `paths`, and a changed file matching nothing it declares can still move its input: an add under a listed directory. It is selected exactly when its `list`/`name` lines differ between the base and the judged state, built by the same `listLines`/`nameLines` input-hash.ts hashes with, from the two listings the change set supplies (`ChangeSet.listings`). A change set that cannot list either side selects every such gate and says so in the note: the fail-open direction, never a silent drop. `refs` does not scope a gate (a ref is not a tree read): a gate declaring only `refs` stays unscoped, and a path-scoped gate that declares `refs` is selected by any non-empty change set, since the commit a ref names may have moved with it.
 */
import { isEntryPoint } from '../lib/entry-point.js';
import { type LsEntry, listLines, matchGlob, nameLines } from './input-hash';

/** The narrow shape `select()` needs. Structural, so `GateSpec` satisfies it. */
export interface PathScopedSpec {
  readonly id: string;
  readonly paths?: readonly string[];
  /** Directories whose listing the gate reads (GateSpec.lists). */
  readonly lists?: readonly string[];
  /** Globs whose matching tracked names the gate reads (GateSpec.names). */
  readonly names?: readonly string[];
  /** Refs whose commit the gate reads (GateSpec.refs). */
  readonly refs?: readonly string[];
}

/** One tracked entry of a listing: its mode and path, enough to build `list` and `name` lines. */
export interface NameEntry {
  readonly mode: string;
  readonly path: string;
}

/**
 * `origin` is the whole point of this type. A caller that swallows a git failure and
 * returns `[]` has destroyed the difference between "clean tree" and "no answer", and
 * both of those must refuse anyway -- but for DIFFERENT reasons, and a reader fixing
 * one of them needs to be told which they have.
 */
export interface ChangeSet {
  readonly files: readonly string[];
  readonly origin: 'resolved' | 'unresolved';
  readonly base: string;
  /** Why the differ could not answer. Required when `origin` is `unresolved`. */
  readonly reason?: string;
  /** The tracked entries at the base and in the judged state, read only when a gate declares `lists` or `names`; undefined (or absent) when git cannot list that side. */
  readonly listings?: {
    readonly before: () => readonly NameEntry[] | undefined;
    readonly after: () => readonly NameEntry[] | undefined;
  };
}

export class ChangeSetRefusal extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ChangeSetRefusal';
  }
}

/**
 * Throws unless the change set can bear a scoping decision.
 *
 * Three refusals, and the first is the one nobody writes: a selector handed an empty
 * MANIFEST would report "0 gates selected, all fine". Zero inputs is a failure, never
 * a pass.
 */
export function refuseUnusableChangeSet(
  specs: readonly PathScopedSpec[],
  changeSet: ChangeSet
): void {
  if (specs.length === 0) {
    throw new ChangeSetRefusal(
      'the selector was handed ZERO gates, so any selection it reports is vacuous. ' +
        'Its green would mean nothing. Check that scripts/ci-runner/manifest.ts still ' +
        'exports GATES and that the caller passed them.'
    );
  }
  if (changeSet.origin === 'unresolved') {
    throw new ChangeSetRefusal(
      `--changed cannot scope this run: the differ gave no answer against ` +
        `${changeSet.base} (${changeSet.reason ?? 'no reason recorded'}). An unanswerable ` +
        `question is not an empty answer. Run without --changed to select every gate, or ` +
        `set CI_RUNNER_BASE to a ref that resolves (a shallow clone often cannot reach ` +
        `origin/main; \`git fetch --deepen=100\` or \`fetch-depth: 0\` fixes it).`
    );
  }
  if (changeSet.files.length === 0) {
    throw new ChangeSetRefusal(
      `--changed found ZERO changed files against ${changeSet.base}, and refuses to ` +
        `report a green on that. Nothing changed and the differ broke are the same shape ` +
        `here, and the empty set is the one input where scoping silently inverts: every ` +
        `path-declaring gate is dropped for want of a match while the rest survive, so ` +
        `the run looks scoped and is simply missing them. If the tree really is clean, ` +
        `there is nothing to check -- drop --changed.`
    );
  }
}

export interface ChangedSelection<T> {
  readonly chosen: readonly T[];
  /** The SHAPE, not just the verdict, so a reader can see a number collapse. */
  readonly note: string;
  readonly scoped: number;
  readonly unscoped: number;
  readonly matched: number;
  /** Gates declaring `lists` or `names`, and how many of them the listing delta selected. */
  readonly nameScoped: number;
  readonly nameMatched: number;
}

function arr(v: readonly string[] | undefined): readonly string[] {
  return v ?? [];
}

/** Does the spec declare `lists` or `names`, the reads that scope it without `paths`? */
function namesScoped(s: PathScopedSpec): boolean {
  return arr(s.lists).length > 0 || arr(s.names).length > 0;
}

/** The spec's `list` and `name` lines over one listing, sorted and joined: equal strings mean the name-shaped input did not move. */
function nameShape(entries: readonly NameEntry[], s: PathScopedSpec): string {
  const ls: LsEntry[] = entries.map((e) => ({ mode: e.mode, type: '', oid: '', path: e.path }));
  return [...new Set([...listLines(ls, arr(s.lists)), ...nameLines(ls, arr(s.names))])]
    .sort((a, b) => Number(a > b) - Number(a < b))
    .join('\n');
}

/**
 * Fail-open selection. `matches(file, globs)` is injected so this module owns no glob
 * dialect: `run.ts` already has one, and a second implementation of the same matcher is
 * a second thing to drift.
 *
 * THE FAIL-OPEN CLAUSE IS `spec.paths === undefined`, NOT `!spec.paths?.length`. An
 * entry that declares `paths: []` has said something -- "nothing selects me" -- and
 * conflating that with saying nothing is how a typo becomes an exemption. Neither form
 * is in the lock today; the distinction is written down before one appears.
 */
export function selectChanged<T extends PathScopedSpec>(
  specs: readonly T[],
  changeSet: ChangeSet,
  matches: (file: string, globs: readonly string[]) => boolean
): ChangedSelection<T> {
  refuseUnusableChangeSet(specs, changeSet);
  const unscoped = specs.filter((s) => s.paths === undefined && !namesScoped(s));
  const scoped = specs.filter((s) => s.paths !== undefined || namesScoped(s));
  // THE LISTING DELTA, read only when some gate declares lists or names. A side git cannot list leaves `listed` false, and every name-scoped gate is then selected.
  const named = scoped.filter(namesScoped);
  let before: readonly NameEntry[] | undefined;
  let after: readonly NameEntry[] | undefined;
  if (named.length > 0) {
    before = changeSet.listings?.before();
    after = changeSet.listings?.after();
  }
  const listed = before !== undefined && after !== undefined;
  const nameMoved = (s: PathScopedSpec): boolean =>
    namesScoped(s) && (!listed || nameShape(before ?? [], s) !== nameShape(after ?? [], s));
  const byPaths = (s: PathScopedSpec): boolean =>
    s.paths !== undefined && changeSet.files.some((f) => matches(f, s.paths ?? []));
  // A ref may move with any change; it never scopes a gate, so it only widens one that paths or names already scope.
  const byRefs = (s: PathScopedSpec): boolean => arr(s.refs).length > 0;
  const matched = scoped.filter((s) => byPaths(s) || nameMoved(s) || byRefs(s));
  const nameMatched = named.filter(nameMoved).length;
  // Order is preserved from `specs` rather than concatenating the two buckets: the pool uses array index as a scheduling tiebreaker, so reordering here would change the run without changing the set.
  const keep = new Set<T>([...unscoped, ...matched]);
  const chosen = specs.filter((s) => keep.has(s));
  const note =
    `--changed (${changeSet.files.length} file(s) vs ${changeSet.base}): ` +
    `${chosen.length} selected = ${unscoped.length} declaring no paths (always selected) ` +
    `+ ${matched.length} of ${scoped.length} path-scoped` +
    (named.length > 0
      ? listed
        ? ` (${nameMatched} of ${named.length} lists/names gate(s) whose listing moved)`
        : ` (all ${named.length} lists/names gate(s): the change set could not list ${before === undefined ? 'the base' : 'the judged state'}, so none is dropped)`
      : '');
  return {
    chosen,
    note,
    scoped: scoped.length,
    unscoped: unscoped.length,
    matched: matched.length,
    nameScoped: named.length,
    nameMatched,
  };
}

/**
 * The selection contract's own controls, both directions, for the name-shaped scope (W2.4). Pure fixtures; `matches` is the caller's glob dialect. Returns the failures; empty means pass.
 */
export function selectSelftest(matches: (file: string, globs: readonly string[]) => boolean): {
  failures: string[];
  assertions: number;
} {
  const failures: string[] = [];
  let assertions = 0;
  const check = (cond: boolean, message: string): void => {
    assertions += 1;
    if (!cond) failures.push(message);
  };
  const ent = (p: string, mode = '100644'): NameEntry => ({ mode, path: p });
  const base: NameEntry[] = [
    ent('cfg/a.json'),
    ent('cfg/sub/x.json'),
    ent('src/x.ts'),
    ent('tpl/a.md'),
    ent('tpl/b.md'),
  ];
  const cs = (
    files: string[],
    after: NameEntry[] | undefined,
    before: NameEntry[] | undefined = base
  ): ChangeSet => ({
    files,
    origin: 'resolved',
    base: 'B',
    listings: { before: () => before, after: () => after },
  });
  const specs: PathScopedSpec[] = [
    { id: 'g:lists', lists: ['cfg'] },
    { id: 'g:names', names: ['tpl/*.md'] },
    { id: 'g:paths', paths: ['src/**'] },
    { id: 'g:refs', paths: ['docs/**'], refs: ['HEAD'] },
    { id: 'g:refsonly', refs: ['HEAD'] },
    { id: 'g:whole' },
  ];
  const pick = (c: ChangeSet): string[] => selectChanged(specs, c, matches).chosen.map((s) => s.id);

  const added = pick(cs(['cfg/b.json'], [...base, ent('cfg/b.json')]));
  check(
    added.includes('g:lists'),
    'a child added to a listed directory must select the lists gate'
  );
  const edit = pick(
    cs(
      ['src/x.ts', 'cfg/a.json', 'tpl/a.md'],
      base.map((e) => ({ ...e }))
    )
  );
  check(
    !edit.includes('g:lists') && !edit.includes('g:names'),
    'CONTROL: content edits that leave every listing alone must select no lists/names gate, though they lack paths'
  );
  check(
    edit.includes('g:paths') && edit.includes('g:whole') && edit.includes('g:refsonly'),
    'CONTROL: the same edit still selects the content reader, the whole-tree gate and a refs-only gate (refs do not scope)'
  );
  check(
    !pick(cs(['cfg/sub/y.json'], [...base, ent('cfg/sub/y.json')])).includes('g:lists'),
    'a file added inside an EXISTING child directory leaves the listing alone, so it must not select'
  );
  check(
    pick(cs(['cfg/new/y.json'], [...base, ent('cfg/new/y.json')])).includes('g:lists'),
    'a file opening a NEW child directory changes the listing and must select'
  );
  check(
    pick(
      cs(
        ['cfg/sub/x.json'],
        base.filter((e) => e.path !== 'cfg/sub/x.json')
      )
    ).includes('g:lists'),
    'removing the last file of a child directory removes the child and must select'
  );
  const renamed = base.map((e) => (e.path === 'tpl/a.md' ? ent('tpl/c.md') : e));
  check(
    pick(cs(['tpl/a.md', 'tpl/c.md'], renamed)).includes('g:names'),
    'a renamed names match must select the names gate'
  );
  check(
    !pick(cs(['tpl/deep/a.md'], [...base, ent('tpl/deep/a.md')])).includes('g:names'),
    'CONTROL: an added path the names glob does not match must not select it'
  );
  check(
    pick(
      cs(
        ['tpl/a.md'],
        base.map((e) => (e.path === 'tpl/a.md' ? ent(e.path, '100755') : e))
      )
    ).includes('g:names'),
    'a mode flip of a names match moves its name line and must select'
  );
  const blind = selectChanged(specs, cs(['src/x.ts'], undefined), matches);
  check(
    blind.chosen.some((s) => s.id === 'g:lists') &&
      blind.chosen.some((s) => s.id === 'g:names') &&
      blind.note.includes('could not list the judged state'),
    `a change set that cannot list a side must select every lists/names gate and say so, got ${blind.note}`
  );
  check(
    selectChanged(
      specs,
      { files: ['src/x.ts'], origin: 'resolved', base: 'B' },
      matches
    ).chosen.some((s) => s.id === 'g:lists'),
    'a change set with no listings at all selects the lists gate (fail open)'
  );
  check(
    pick(cs(['src/x.ts'], base)).includes('g:refs'),
    'a path-scoped gate declaring refs is selected by any non-empty change set'
  );
  const shape = selectChanged(specs, cs(['cfg/b.json'], [...base, ent('cfg/b.json')]), matches);
  check(
    shape.unscoped === 2 && shape.nameScoped === 2 && shape.nameMatched === 1,
    `the shape counts lists/names gates as scoped, got unscoped ${shape.unscoped}, nameScoped ${shape.nameScoped}, nameMatched ${shape.nameMatched}`
  );
  return { failures, assertions };
}

if (isEntryPoint(import.meta.filename) && process.argv.includes('--selftest')) {
  const r = selectSelftest((f, globs) => globs.some((g) => matchGlob(g, f)));
  for (const f of r.failures) process.stderr.write(`select selftest FAIL: ${f}\n`);
  process.stdout.write(
    `select selftest: ${r.failures.length === 0 ? 'ok' : 'FAILED'} (${r.assertions} assertions, ${r.failures.length} failure(s))\n`
  );
  process.exit(r.failures.length === 0 ? 0 : 1);
}
