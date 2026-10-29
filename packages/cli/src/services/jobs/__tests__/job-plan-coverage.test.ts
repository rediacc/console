/**
 * JOB_PLANS covers the machine plane (PLAN-detached-jobs J0b, C3).
 *
 * Every command whose contract `plane` is `machine` either has a job plan (its form, lock class, timeout class and
 * conversion box, per the J0b audit) or a listed section 24 exception with a reason. The set is keyed on `plane`,
 * not on `detachable`, because J2 changes `detachable`; a new machine-plane command with neither fails here.
 *
 * The lock classes are renet's: each plan's class is read against private/renet/pkg/jobs/overlap.go, the table and
 * fallback rules renet applies at `job start`. A missing overlap.go throws rather than skipping, because a class check
 * that quietly does not run is the failure this exists to prevent.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { CLI_CONTRACT } from '@rediacc/shared/cli-contract';
import { describe, expect, it } from 'vitest';
import {
  JOB_EXCEPTIONS,
  JOB_PLANS,
  type JobPlan,
  LOCK_CLASSES,
  TIMEOUT_CLASSES,
} from '../plans.js';

const OVERLAP_GO = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../../../../../private/renet/pkg/jobs/overlap.go'
);

interface OverlapModel {
  classes: Set<string>;
  byName: Map<string, string>;
  readSuffixes: string[];
  machineScopeWithoutRepo: string[];
  classFor(fn: string): string;
  classForJob(fn: string, repoGuid: string): string;
}

function quoted(list: string): string[] {
  return [...list.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
}

/** A TypeScript reading of overlap.go's ClassFor and ClassForJob, from the Go source itself. */
function loadOverlap(): OverlapModel {
  const src = readFileSync(OVERLAP_GO, 'utf8');
  const ident = new Map<string, string>();
  for (const m of src.matchAll(/^\s*(Class\w+)\s+LockClass\s*=\s*"([^"]+)"/gm))
    ident.set(m[1], m[2]);
  const commands = new Map<string, string>();
  for (const m of src.matchAll(/^\s*(Command\w+)\s*=\s*"([^"]+)"/gm)) commands.set(m[1], m[2]);

  const table = /var classByName = map\[string\]LockClass\{([\s\S]*?)\n\}/.exec(src)?.[1];
  if (!table) throw new Error('overlap.go: classByName table not found');
  const byName = new Map<string, string>();
  for (const m of table.matchAll(/^\s*(?:"([^"]+)"|(Command\w+))\s*:\s*(Class\w+),/gm)) {
    const name = m[1] ?? commands.get(m[2]);
    const cls = ident.get(m[3]);
    if (!name || !cls) throw new Error(`overlap.go: unresolved entry ${m[0].trim()}`);
    byName.set(name, cls);
  }

  const readSuffixes = quoted(/var readSuffixes = \[\]string\{([\s\S]*?)\}/.exec(src)?.[1] ?? '');
  const machineScopeWithoutRepo = quoted(
    /var machineScopeWithoutRepo = \[\]string\{([\s\S]*?)\}/.exec(src)?.[1] ?? ''
  );
  // The literal "scheduled" label is not a class a job can have (overlap.go classScheduled).
  const classes = new Set([...ident.values()]);

  const classFor = (fn: string): string => {
    const listed = byName.get(fn);
    if (listed) return listed;
    if (fn.endsWith('_all')) return 'machine-exclusive';
    if (fn.startsWith('machine_check_')) return 'read';
    if (readSuffixes.some((s) => fn.endsWith(s))) return 'read';
    if (fn.startsWith('repository_')) return 'repo-exclusive';
    return 'read';
  };
  const classForJob = (fn: string, repoGuid: string): string =>
    repoGuid === '' && machineScopeWithoutRepo.includes(fn) ? 'machine-shared' : classFor(fn);

  return { classes, byName, readSuffixes, machineScopeWithoutRepo, classFor, classForJob };
}

const byText = (a: string, b: string): number => a.localeCompare(b);

const overlap = loadOverlap();
const machinePlane = CLI_CONTRACT.commands
  .filter((c) => c.plane === 'machine')
  .map((c) => c.pathKey)
  .sort(byText);

/** A plan with no `fn` is checked through the name it reads its lock from, or the gap it declares. */
function fnlessMismatches(cmd: string, plan: JobPlan): string[] {
  const { lockFrom, lockGap } = plan;
  if (lockFrom && lockGap) return [`${cmd}: names both lockFrom and lockGap`];
  if (lockFrom) {
    const listed = overlap.byName.get(lockFrom);
    if (!listed) return [`${cmd}: lockFrom ${lockFrom} is not in overlap.go`];
    return listed === plan.lock ? [] : [`${cmd}: ${plan.lock} != ${listed} (${lockFrom})`];
  }
  if (lockGap) {
    const actual = overlap.classForJob(lockGap.runs, 'guid');
    return actual === lockGap.overlap
      ? []
      : [
          `${cmd}: overlap.go gives ${lockGap.runs} ${actual}, the declared gap says ${lockGap.overlap}`,
        ];
  }
  return [`${cmd}: no fn, so it needs lockFrom or lockGap`];
}

/** How a plan's declared classes differ from overlap.go's, for the job with and without a repository. */
function classMismatches(cmd: string, plan: JobPlan): string[] {
  if (!plan.fn) return fnlessMismatches(cmd, plan);
  const found: string[] = [];
  const repoScoped = overlap.classForJob(plan.fn, 'guid');
  if (plan.lock !== repoScoped) found.push(`${cmd}: ${plan.lock} != ${repoScoped}`);
  const machineScoped = overlap.classForJob(plan.fn, '');
  const declared = plan.lockWithoutRepo ?? plan.lock;
  if (machineScoped !== repoScoped && declared !== machineScoped) {
    found.push(`${cmd} without a repo: ${declared} != ${machineScoped}`);
  }
  return found;
}

describe('JOB_PLANS coverage', () => {
  it('reads a real overlap table, not an empty one', () => {
    expect(overlap.classes.size).toBeGreaterThanOrEqual(6);
    expect(overlap.byName.size).toBeGreaterThan(40);
    expect(overlap.readSuffixes).toContain('_list');
    expect(overlap.machineScopeWithoutRepo).toContain('repository_trim');
    expect(machinePlane.length).toBeGreaterThan(90);
  });

  it('every machine-plane contract command has a plan or a listed exception', () => {
    const missing = machinePlane.filter((p) => !(p in JOB_PLANS) && !(p in JOB_EXCEPTIONS));
    expect(missing).toEqual([]);
  });

  it('no command has both a plan and an exception', () => {
    expect(Object.keys(JOB_PLANS).filter((p) => p in JOB_EXCEPTIONS)).toEqual([]);
  });

  it('names no command outside the machine plane', () => {
    const known = new Set(machinePlane);
    const stale = [...Object.keys(JOB_PLANS), ...Object.keys(JOB_EXCEPTIONS)].filter(
      (p) => !known.has(p)
    );
    expect(stale).toEqual([]);
  });

  it('every exception carries a reason', () => {
    for (const [cmd, reason] of Object.entries(JOB_EXCEPTIONS)) {
      expect(reason.trim().length, cmd).toBeGreaterThan(10);
    }
  });

  it('the lock classes are exactly renet’s', () => {
    expect([...LOCK_CLASSES].sort(byText)).toEqual([...overlap.classes].sort(byText));
  });

  it('every plan uses a renet lock class and a section 20 timeout class', () => {
    for (const [cmd, plan] of Object.entries(JOB_PLANS)) {
      expect(overlap.classes.has(plan.lock), `${cmd} lock ${plan.lock}`).toBe(true);
      if (plan.lockWithoutRepo) {
        expect(overlap.classes.has(plan.lockWithoutRepo), `${cmd} lockWithoutRepo`).toBe(true);
      }
      expect(TIMEOUT_CLASSES, `${cmd} timeout`).toContain(plan.timeout);
    }
  });

  it('a plan that names its renet function carries the class overlap.go gives it', () => {
    const mismatched = Object.entries(JOB_PLANS).flatMap(([cmd, plan]) =>
      classMismatches(cmd, plan)
    );
    expect(mismatched).toEqual([]);
  });

  it('a plan with no renet function says why (a new command kind or a multi-function chain)', () => {
    for (const [cmd, plan] of Object.entries(JOB_PLANS)) {
      if (plan.fn) continue;
      expect(plan.note?.trim().length ?? 0, `${cmd} has no fn and no note`).toBeGreaterThan(10);
    }
  });

  it('a plan with no fn is checked against overlap.go through lockFrom or a named lockGap', () => {
    const fnless = Object.entries(JOB_PLANS).filter(([, plan]) => !plan.fn);
    expect(fnless.map(([cmd]) => cmd)).toContain('repo canary remove');
    expect(fnless.flatMap(([cmd, plan]) => classMismatches(cmd, plan))).toEqual([]);
  });

  it('a wrong lock on a plan with no fn is caught', () => {
    const wrongFrom: JobPlan = {
      form: 'command-kind',
      lock: 'repo-exclusive',
      timeout: '10m',
      box: 'J17',
      lockFrom: 'backup-status',
    };
    expect(classMismatches('x', wrongFrom)).toHaveLength(1);
    const staleGap: JobPlan = {
      form: 'single',
      lock: 'repo-exclusive',
      timeout: '10m',
      box: 'J16',
      lockGap: { runs: 'kube_delete', overlap: 'machine-exclusive' },
    };
    expect(classMismatches('x', staleGap)).toHaveLength(1);
    const bare: JobPlan = { form: 'single', lock: 'read', timeout: '10m', box: 'J16' };
    expect(classMismatches('x', bare)).toHaveLength(1);
  });

  it('the J4 verbs are the nine J0 verbs', () => {
    const j4 = Object.entries(JOB_PLANS)
      .filter(([, plan]) => plan.box === 'J4')
      .map(([cmd]) => cmd)
      .sort(byText);
    expect(j4).toEqual([
      'backup restore',
      'backup snapshot',
      'backup verify',
      'repo down',
      'repo fork',
      'repo migrate',
      'repo pull',
      'repo push',
      'repo up',
    ]);
  });
});
