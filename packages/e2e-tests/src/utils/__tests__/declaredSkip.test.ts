import { describe, expect, it } from 'vitest';
import { announcePrerequisites, resolvePrerequisites } from '../declaredSkip';

const met = { name: 'MET', satisfied: true, how: 'nothing to do' };
const unmet = {
  name: 'VM_WORKERS (two worker VMs)',
  satisfied: false,
  how: 'run `./run.sh ops up`',
};
const unmet2 = {
  name: 'REDIACC_ACCOUNT_SERVER (reachable)',
  satisfied: false,
  how: 'run `./run.sh account dev`',
};

const resolve = (prerequisites: (typeof met)[], env: NodeJS.ProcessEnv = {}) =>
  resolvePrerequisites({
    label: 'cluster licensing',
    declareVar: 'E2E_EXPECT_NO_CLUSTER_VMS',
    prerequisites,
    env,
  });

describe('resolvePrerequisites', () => {
  it('runs when every prerequisite is satisfied', () => {
    expect(resolve([met, met]).kind).toBe('run');
  });

  it('ignores a declaration when nothing is missing (a declaration must not disable a runnable suite)', () => {
    const verdict = resolve([met], { E2E_EXPECT_NO_CLUSTER_VMS: 'no fleet on this runner' });
    expect(verdict.kind).toBe('run');
  });

  // The instrument control. This is the case the whole module exists for: a
  // missing prerequisite with nobody saying why must be a RED, never a skip.
  it('FAILS CLOSED when a prerequisite is missing and no declaration is set', () => {
    const verdict = resolve([met, unmet]);
    expect(verdict.kind).toBe('undeclared');
    if (verdict.kind !== 'undeclared') throw new Error('unreachable');
    expect(verdict.missing).toEqual(['VM_WORKERS (two worker VMs)']);
    expect(verdict.message).toContain('That is a FAILURE, not a skip');
    // The failure text must be actionable on both sides: how to satisfy it,
    // and the exact var that declares the omission.
    expect(verdict.message).toContain('run `./run.sh ops up`');
    expect(verdict.message).toContain(
      "E2E_EXPECT_NO_CLUSTER_VMS='<why this environment has none>'"
    );
  });

  it('names EVERY unmet prerequisite, not just the first', () => {
    const verdict = resolve([unmet, met, unmet2]);
    if (verdict.kind !== 'undeclared') throw new Error(`expected undeclared, got ${verdict.kind}`);
    expect(verdict.missing).toEqual([unmet.name, unmet2.name]);
  });

  it('skips by declaration when the var carries a reason', () => {
    const verdict = resolve([unmet], { E2E_EXPECT_NO_CLUSTER_VMS: 'no KVM fleet on this runner' });
    if (verdict.kind !== 'declared-skip')
      throw new Error(`expected declared-skip, got ${verdict.kind}`);
    expect(verdict.reason).toBe('no KVM fleet on this runner');
    expect(verdict.banner).toContain('SKIPPED BY DECLARATION');
    expect(verdict.banner).toContain('no KVM fleet on this runner');
    expect(verdict.banner).toContain('VM_WORKERS (two worker VMs)');
  });

  // An empty/whitespace value is not a reason. Accepting it would let
  // `E2E_EXPECT_NO_CLUSTER_VMS=` in a shell profile silence the suite with no
  // reader-checkable justification, which is the original defect.
  it('treats an empty or whitespace declaration as no declaration', () => {
    expect(resolve([unmet], { E2E_EXPECT_NO_CLUSTER_VMS: '' }).kind).toBe('undeclared');
    expect(resolve([unmet], { E2E_EXPECT_NO_CLUSTER_VMS: '   ' }).kind).toBe('undeclared');
  });
});

describe('announcePrerequisites', () => {
  it('throws the failure text on an undeclared verdict', () => {
    const verdict = resolve([unmet]);
    expect(() => announcePrerequisites(verdict)).toThrow(/FAILURE, not a skip/);
  });

  it('logs the banner and reports skip on a declared verdict', () => {
    const lines: string[] = [];
    const verdict = resolve([unmet], { E2E_EXPECT_NO_CLUSTER_VMS: 'declared reason' });
    const outcome = announcePrerequisites(verdict, (line) => lines.push(line));
    expect(outcome.skip).toBe(true);
    expect(outcome.reason).toContain('declared reason');
    expect(lines.join('\n')).toContain('SKIPPED BY DECLARATION');
  });

  it('reports no skip and logs nothing on a run verdict', () => {
    const lines: string[] = [];
    const outcome = announcePrerequisites(resolve([met]), (line) => lines.push(line));
    expect(outcome).toEqual({ skip: false, reason: '' });
    expect(lines).toEqual([]);
  });
});
