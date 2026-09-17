#!/usr/bin/env node
/**
 * `--changed` must fail OPEN on scope and REFUSE on a change set it cannot trust.
 *
 * WHAT IT GUARDS. Measured on this tree 2026-09-09 from
 * scripts/ci-runner/gates.lock.json: 474 entries, 464 with `gate: true`, and exactly
 * 46 of those declare `paths`. 418 declare none. So `paths` is not a scoping table,
 * it is a scoping table for 10% of the estate, and the other 90% must be selected by
 * every non-empty change set or `--changed` quietly runs a tenth of CI.
 *
 * THE HALF THAT WAS MISSING, and it is the vacuity this whole estate exists against.
 * The change set is `git diff --name-only <merge-base>`, and BOTH "nothing changed"
 * and "git could not answer" arrive as the empty list. Under fail-open the empty list
 * is the single input where the rule inverts: no file matches any glob, so every one
 * of the 46 path-declaring gates is dropped, while the 418 survive. The run then
 * reports green having skipped exactly the gates somebody scoped on purpose.
 *
 * MEASURED, BEFORE THE FIX, ON THE REAL INVOCATION (both against a clean --depth 1
 * clone whose full `--list` shows 448 gates):
 *
 *     $ CI_RUNNER_BASE=refs/heads/__no_such_ref__ npx tsx scripts/ci-runner/run.ts --list --changed
 *     ci-runner: --changed could not resolve a merge base against refs/heads/__no_such_ref__; selecting every gate
 *     rc=0, 403 gate lines
 *
 * "Selecting every gate" over a selection that dropped 45 of them. An instrument that
 * reports work it did not do is the same defect as a gate that cannot fail.
 *
 * WHAT THIS FILE DRIVES, and why it is not a unit test. Every case below runs
 * `scripts/ci-runner/run.ts` as a PROCESS with the real manifest or a real JSON
 * manifest on disk, and reads its real stdout, stderr and exit code. A control that
 * imported `selectChanged()` and called it would have passed on the day the runner
 * silently ignored the module.
 *
 * THE FAKE `git` IS A FAKE ENVIRONMENT, NOT A FAKE SUBJECT. The empty-change-set case
 * needs a clean tree, and this tree is never clean -- it holds several sessions'
 * uncommitted work, and `git stash` is forbidden here for that reason. So a shim
 * named `git` goes on PATH ahead of the real one, answering `merge-base` with a real
 * sha and `diff --name-only` with nothing. run.ts, select.ts, the manifest and the
 * 464 real specs are all the genuine article; only the tree's cleanliness is
 * simulated, at exactly the boundary run.ts reads it through. Its CONTROL (the same
 * shim returning one file) is what proves the shim is not itself the red.
 *
 * ---- gate ----
 * step: Changed-file selection contract
 * lane: quality-code
 * needs: node
 * selftest: true
 * why: --changed scopes by `paths` and 419 of 465 gates declare none, so an empty or
 *   unanswerable change set silently drops every scoped gate and reports green
 * ---- end gate ----
 */

import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import {
  type ChangeSet,
  ChangeSetRefusal,
  refuseUnusableChangeSet,
  selectChanged,
} from '../ci-runner/select';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const RUNNER = path.join(REPO_ROOT, 'scripts', 'ci-runner', 'run.ts');
const LOCK = path.join(REPO_ROOT, 'scripts', 'ci-runner', 'gates.lock.json');

interface LockEntry {
  id: string;
  gate?: boolean;
  paths?: string[];
}

interface Run {
  rc: number;
  out: string;
  err: string;
}

const failures: string[] = [];
let controls = 0;

function ok(label: string): void {
  controls += 1;
  process.stdout.write(`  PASS  ${label}\n`);
}

function no(label: string, detail: string): void {
  controls += 1;
  failures.push(`${label}\n        ${detail}`);
  process.stdout.write(`  FAIL  ${label}\n        ${detail}\n`);
}

function check(condition: boolean, label: string, detail: string): void {
  if (condition) ok(label);
  else no(label, detail);
}

/**
 * A REFUSAL, not a finding. Used only where the gate cannot see its subject at all:
 * an empty lock, an empty tracked-file corpus, a runner it cannot launch. Those are
 * not results about the runner, they are the absence of a result, and folding them
 * into the tally would let "asserted nothing" print a passing count.
 */
function refuse(text: string): never {
  process.stderr.write(`\u2717 ${text}\n`);
  process.exit(1);
}

/**
 * A MISSING TOOL IS A LOUD FAILURE WITH THE FIX IN THE MESSAGE. `npx tsx` resolving
 * to nothing, or `tsx` not being installed, would otherwise arrive as a non-zero exit
 * with an unhelpful stream and read as the gate finding something.
 */
function runRunner(args: string[], env: NodeJS.ProcessEnv = {}, pathPrefix?: string): Run {
  const merged = { ...process.env, ...env };
  if (pathPrefix !== undefined) merged.PATH = `${pathPrefix}${path.delimiter}${merged.PATH ?? ''}`;
  const proc = spawnSync('npx', ['tsx', RUNNER, ...args], {
    cwd: REPO_ROOT,
    encoding: 'utf-8',
    env: merged,
    maxBuffer: 64 * 1024 * 1024,
  });
  if (proc.error !== undefined) {
    refuse(
      `cannot drive the runner: ${proc.error.message}. This gate has asserted NOTHING. ` +
        `Install dependencies first: npm install && npm run install:natives`
    );
  }
  return { rc: proc.status ?? -1, out: proc.stdout ?? '', err: proc.stderr ?? '' };
}

/** `gate <id> ...` lines from `--list`. `prereq` rows are not selections. */
function selectedIds(out: string): Set<string> {
  const ids = new Set<string>();
  for (const line of out.split('\n')) {
    const m = /^gate\s+(\S+)/.exec(line);
    if (m) ids.add(m[1]);
  }
  return ids;
}

function readLock(): LockEntry[] {
  const parsed: unknown = JSON.parse(fs.readFileSync(LOCK, 'utf-8'));
  if (!Array.isArray(parsed)) throw new Error(`${LOCK} does not contain an array`);
  return parsed as LockEntry[];
}

/**
 * A shim directory holding a `git` that answers exactly what the case needs.
 *
 * THE FILE LIST GOES IN A FILE, NOT IN THE SCRIPT. The first version of this shim
 * used `printf '%s' "a\nb\n"`, and bash does not interpret `\n` inside double
 * quotes, so a 5422-line change set arrived as ONE line ending in a literal
 * backslash-n. The refusal cases still behaved (non-empty is non-empty), and the
 * MATCHING control went red saying the selector had stopped scoping. It had not;
 * the fixture had. A control that does not fire is a claim about the control first.
 */
function fakeGit(dir: string, sha: string, diffLines: string[]): string {
  const bin = path.join(dir, 'bin');
  fs.mkdirSync(bin, { recursive: true });
  const data = path.join(dir, 'changed.txt');
  fs.writeFileSync(data, diffLines.map((l) => `${l}\n`).join(''));
  const body = [
    '#!/usr/bin/env bash',
    '# Fixture only. Written to a temp dir at runtime; nothing here is tracked.',
    'case "$1 $2" in',
    `  "merge-base HEAD"*) echo "${sha}" ;;`,
    `  "diff --name-only"*) cat ${JSON.stringify(data)} ;;`,
    '  *) exit 0 ;;',
    'esac',
    '',
  ].join('\n');
  const file = path.join(bin, 'git');
  fs.writeFileSync(file, body, { mode: 0o755 });
  return bin;
}

function head(): string {
  return execFileSync('git', ['rev-parse', 'HEAD'], { cwd: REPO_ROOT, encoding: 'utf-8' }).trim();
}

// --------------------------------------------------------------------------- The selftest: the pure contract, both directions.

function selftest(): number {
  process.stdout.write('changed-selection: controls first, then the verdict\n');
  const cs = (files: string[], origin: ChangeSet['origin'] = 'resolved'): ChangeSet => ({
    files,
    origin,
    base: 'origin/main',
    reason: origin === 'unresolved' ? 'fixture' : undefined,
  });
  const specs = [
    { id: 'a', paths: undefined },
    { id: 'b', paths: ['docs/**'] },
    { id: 'c', paths: ['src/**'] },
  ];
  const matches = (f: string, globs: readonly string[]): boolean =>
    globs.some((g) => f.startsWith(g.replace('/**', '/')));

  const sel = selectChanged(specs, cs(['docs/x.md']), matches);
  check(
    sel.chosen.map((s) => s.id).join(',') === 'a,b',
    'fail-open: the no-paths gate is selected and only the matching scoped one joins it',
    `got ${sel.chosen.map((s) => s.id).join(',') || '(none)'}`
  );
  check(
    sel.note.includes('1 declaring no paths (always selected)') && sel.note.includes('1 of 2'),
    'the note prints the SHAPE, not just a verdict',
    `got ${sel.note}`
  );
  // THE CONTROL THAT MAKES THE ONE ABOVE MEAN SOMETHING: a change set matching NO glob must still take the unscoped gate. Without this, a selector that simply returned everything would pass the first case.
  const none = selectChanged(specs, cs(['unrelated/x']), matches);
  check(
    none.chosen.map((s) => s.id).join(',') === 'a',
    'CONTROL: a change set matching no glob still selects the no-paths gate, and nothing else',
    `got ${none.chosen.map((s) => s.id).join(',') || '(none)'}`
  );
  check(
    selectChanged(specs, cs(['docs/x', 'src/y']), matches).chosen.length === 3,
    'CONTROL: a change set touching both scopes selects all three, or the filter is stuck',
    'expected 3'
  );

  const refuses = (cset: ChangeSet, sps: { id: string; paths?: string[] }[], needle: string) => {
    try {
      selectChanged(sps, cset, matches);
      return `did not throw (needle ${needle})`;
    } catch (err) {
      if (!(err instanceof ChangeSetRefusal)) return `threw ${String(err)}`;
      return err.message.includes(needle) ? '' : `message lacks ${needle}: ${err.message}`;
    }
  };
  check(
    refuses(cs([]), specs, 'ZERO changed files') === '',
    'an EMPTY change set refuses; it does not select the unscoped subset',
    refuses(cs([]), specs, 'ZERO changed files')
  );
  check(
    refuses(cs([], 'unresolved'), specs, 'gave no answer') === '',
    'an UNRESOLVED change set refuses, and says so differently from an empty one',
    refuses(cs([], 'unresolved'), specs, 'gave no answer')
  );
  check(
    refuses(cs(['x']), [], 'ZERO gates') === '',
    'ZERO gates in is a refusal: a selection over an empty manifest is vacuous',
    refuses(cs(['x']), [], 'ZERO gates')
  );
  // The two refusals must not be one message wearing two hats. A reader fixing a shallow clone needs to be told it is a shallow clone.
  let emptyMsg = '';
  let unresolvedMsg = '';
  try {
    refuseUnusableChangeSet(specs, cs([]));
  } catch (err) {
    emptyMsg = (err as Error).message;
  }
  try {
    refuseUnusableChangeSet(specs, cs([], 'unresolved'));
  } catch (err) {
    unresolvedMsg = (err as Error).message;
  }
  check(
    emptyMsg !== unresolvedMsg && emptyMsg !== '' && unresolvedMsg !== '',
    'the two refusals carry DIFFERENT messages, so the remedy is the right one',
    `empty=${emptyMsg.slice(0, 40)} unresolved=${unresolvedMsg.slice(0, 40)}`
  );
  // `paths: []` says "nothing selects me" and must NOT be treated as "says nothing".
  const explicitEmpty = selectChanged([{ id: 'z', paths: [] }, ...specs], cs(['docs/x']), matches);
  check(
    !explicitEmpty.chosen.some((s) => s.id === 'z'),
    'CONTROL: `paths: []` is a statement, not a blank -- it is NOT treated as unscoped',
    'z was selected'
  );
  return finish('selftest');
}

function finish(label: string): number {
  if (failures.length > 0) {
    process.stderr.write(`\n✗ ${label}: ${failures.length} of ${controls} control(s) failed\n`);
    for (const f of failures) process.stderr.write(`  - ${f}\n`);
    return 1;
  }
  process.stdout.write(`✓ ${label}: ${controls} control(s) passed\n`);
  return 0;
}

// --------------------------------------------------------------------------- The real runner, as a process.

function main(): number {
  process.stdout.write('changed-selection: driving scripts/ci-runner/run.ts as a process\n');

  const lock = readLock();
  const gates = lock.filter((e) => e.gate === true);
  const unscoped = gates.filter((e) => e.paths === undefined).map((e) => e.id);
  const scoped = gates.filter((e) => e.paths !== undefined).map((e) => e.id);
  // ZERO INPUTS IS A FAILURE, NEVER A PASS.
  if (gates.length === 0) {
    refuse(
      `${LOCK} declares ZERO gates, so this gate is not seeing the estate and its green ` +
        `would mean nothing. Regenerate the lock: npm run gen:gates-lock`
    );
  }
  const tracked = execFileSync('git', ['ls-files'], {
    cwd: REPO_ROOT,
    encoding: 'utf-8',
    maxBuffer: 64 * 1024 * 1024,
  })
    .split('\n')
    .filter(Boolean);
  if (tracked.length === 0) {
    refuse(
      `\`git ls-files\` returned nothing from ${REPO_ROOT}, so every change set below would ` +
        `be synthetic and this gate would assert nothing about a real corpus`
    );
  }
  process.stdout.write(
    `  shape: ${lock.length} lock entries, ${gates.length} gates, ${scoped.length} declaring ` +
      `paths, ${unscoped.length} always-selected, ${tracked.length} tracked files\n`
  );

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'changed-sel-'));
  try {
    const sha = head();

    // --- 1. FAIL OPEN, real manifest, a change set of the WHOLE TRACKED TREE --- THE CHANGE SET IS FED THROUGH A SHIM RATHER THAN TAKEN FROM THE AMBIENT DIFF, and that is a correctness requirement, not a convenience. On push-to-main the merge base IS HEAD, so the ambient diff is empty and the runner correctly REFUSES -- which would turn this gate red on the one event where
    // nothing is wrong. The assertion therefore rides a change set this gate constructs and
    // knows the answer for; the ambient path is asserted separately, below, as a
    // disjunction that is true in every state.
    const allBin = fakeGit(path.join(tmp, 'all'), sha, tracked);
    const all = runRunner(['--list', '--changed'], { CI_RUNNER_BASE: 'HEAD' }, allBin);
    const chosen = selectedIds(all.out);
    check(
      all.rc === 0,
      'a change set naming every tracked file is accepted',
      `rc=${all.rc} err=${all.err.slice(0, 300)}`
    );
    const missing = unscoped.filter((id) => !chosen.has(id));
    check(
      missing.length === 0,
      `fail-open: all ${unscoped.length} gate(s) declaring no paths are selected`,
      `${missing.length} were dropped, e.g. ${missing.slice(0, 5).join(', ')}. A gate with no ` +
        `\`paths\` must be selected by every non-empty change set: ${unscoped.length} of ` +
        `${gates.length} declare none, so dropping them turns --changed into a fraction of CI ` +
        `wearing CI's name`
    );
    const scopedHit = scoped.filter((id) => chosen.has(id));
    check(
      [...chosen].every((id) => unscoped.includes(id) || scoped.includes(id)),
      'CONTROL: the selection contains nothing the lock does not declare a gate',
      `stray: ${[...chosen]
        .filter((id) => !unscoped.includes(id) && !scoped.includes(id))
        .slice(0, 5)
        .join(', ')}`
    );
    process.stdout.write(
      `  observed: ${scopedHit.length} of ${scoped.length} path-scoped gate(s) match at least ` +
        `one tracked file (the remainder are C2's subject, not this gate's)\n`
    );

    // --- 2. BOTH DIRECTIONS on a synthetic manifest, through the real argv path --
    const witness = tracked[0];
    const manifest = path.join(tmp, 'm.json');
    fs.writeFileSync(
      manifest,
      JSON.stringify([
        { id: 'probe:unscoped', run: 'true', gate: true },
        { id: 'probe:matching', run: 'true', gate: true, paths: [witness] },
        { id: 'probe:elsewhere', run: 'true', gate: true, paths: ['no/such/dir/**'] },
      ])
    );
    const oneBin = fakeGit(path.join(tmp, 'one'), sha, [witness]);
    const syn = runRunner(
      ['--list', '--changed', '--manifest', manifest],
      { CI_RUNNER_BASE: 'HEAD' },
      oneBin
    );
    const got = selectedIds(syn.out);
    check(
      got.has('probe:unscoped'),
      'MUST FIRE: a gate with no `paths` is selected by a ONE-file change set, which is ' +
        'the smallest non-empty input and where fail-open is easiest to lose',
      `rc=${syn.rc} selected=${[...got].join(',') || '(none)'} err=${syn.err.trim().slice(0, 200)}`
    );
    check(
      got.has('probe:matching'),
      'CONTROL: a scoped gate whose glob matches the changed file is selected',
      `selected=${[...got].join(',') || '(none)'}`
    );
    check(
      !got.has('probe:elsewhere'),
      'MUST NOT FIRE: a scoped gate whose glob matches nothing is NOT selected -- without ' +
        'this the two above are satisfied by a selector that returns everything',
      'probe:elsewhere was selected, so scoping does nothing'
    );

    // --- 3. AN UNRESOLVABLE BASE REFUSES ---------------------------------------
    const broke = runRunner(['--list', '--changed'], {
      CI_RUNNER_BASE: 'refs/heads/__gate_probe_no_such_ref__',
    });
    check(
      broke.rc !== 0,
      'a differ that cannot answer REFUSES (rc != 0)',
      `rc=${broke.rc}; it selected ${selectedIds(broke.out).size} gate(s) and called it green. ` +
        `"Could not resolve a merge base" is not "nothing changed"`
    );
    check(
      broke.err.includes('cannot scope this run') && broke.out.trim() === '',
      'the refusal is on STDERR and stdout stays empty, so no reader mistakes it for a list',
      `out=${broke.out.slice(0, 120)} err=${broke.err.slice(0, 200)}`
    );

    // --- 4. AN EMPTY CHANGE SET REFUSES, and the shim gets its own control ------
    const emptyBin = fakeGit(path.join(tmp, 'empty'), sha, []);
    const empty = runRunner(['--list', '--changed'], { CI_RUNNER_BASE: 'HEAD' }, emptyBin);
    check(
      empty.rc !== 0,
      'an EMPTY change set REFUSES; it does not report green over the unscoped subset',
      `rc=${empty.rc}; it selected ${selectedIds(empty.out).size} gate(s). "Nothing changed" ` +
        `and "the differ broke" are the same shape, and the empty set is where fail-open ` +
        `inverts: all ${scoped.length} path-scoped gates drop for want of a match`
    );
    check(
      empty.err.includes('ZERO changed files'),
      'the empty-set refusal names ITS OWN reason, not the unresolved one',
      `err=${empty.err.slice(0, 250)}`
    );
    // FIX THE CONTROL FIRST. A shim that broke the runner some other way would make the two cases above red for a reason that has nothing to do with the change set. The one-file run in section 2 is that control and it used the SAME shim writer, so this restates it against the REAL manifest rather than the synthetic one.
    const oneReal = runRunner(['--list', '--changed'], { CI_RUNNER_BASE: 'HEAD' }, oneBin);
    check(
      oneReal.rc === 0 && selectedIds(oneReal.out).size > 0,
      'CONTROL: the SAME shim returning ONE changed file runs green over the real manifest, ' +
        'so the two refusals above are the change set and not the fixture',
      `rc=${oneReal.rc} selected=${selectedIds(oneReal.out).size} err=${oneReal.err.slice(0, 200)}`
    );

    // --- 5. THE AMBIENT PATH, asserted as a disjunction true in every state -----
    // The real differ against the real base. On a PR it answers with files; on
    // push-to-main the merge base is HEAD and it correctly refuses; on a shallow
    // clone it cannot resolve. All three are legitimate, and ANYTHING ELSE is not: a green whose selection has lost an unscoped gate, or a red carrying neither refusal, both mean the real path has stopped behaving like the shimmed one.
    const ambient = runRunner(['--list', '--changed']);
    const ambientIds = selectedIds(ambient.out);
    const ambientOk =
      ambient.rc === 0
        ? unscoped.every((id) => ambientIds.has(id))
        : ambient.err.includes('ZERO changed files') || ambient.err.includes('gave no answer');
    check(
      ambientOk,
      'the AMBIENT run (real git, real base) either selects every no-paths gate or refuses ' +
        'with one of the two named reasons -- no third outcome',
      `rc=${ambient.rc} selected=${ambientIds.size} missing=${unscoped.filter((id) => !ambientIds.has(id)).length} err=${ambient.err.trim().slice(0, 250)}`
    );
    process.stdout.write(
      `  ambient: rc=${ambient.rc}, ${ambientIds.size} gate(s) selected against ` +
        `${process.env.CI_RUNNER_BASE ?? 'origin/main'}` +
        (ambient.rc === 0
          ? '\n'
          : ` (refused: ${ambient.err.trim().split('\n').slice(-1)[0].slice(0, 90)})\n`)
    );
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }

  return finish(
    `changed-selection over ${gates.length} gate(s) (${scoped.length} path-scoped, ` +
      `${unscoped.length} always-selected)`
  );
}

const argv = process.argv.slice(2);
process.exit(argv.includes('--selftest') ? selftest() : main());
