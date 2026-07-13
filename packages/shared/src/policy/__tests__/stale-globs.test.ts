/**
 * Stale command globs — the fail-open half of the policy layer.
 *
 * The first test here is the one that matters: it demonstrates, against the real
 * evaluator, that a deny rule whose command has been RENAMED silently permits
 * the very command it was written to forbid. Everything else in this file exists
 * to prove the detector catches that, and does not cry wolf on live rules.
 */
import { describe, expect, it } from 'vitest';
import { evaluatePolicy } from '../evaluate.js';
import type { PolicyDocument } from '../schema.js';
import { findStaleCommandGlobs, staleDenyRefusal } from '../stale-globs.js';

/** A command set standing in for the contract, before and after a P4 rename. */
const BEFORE_RENAME = ['repo list', 'repo takeover', 'cluster destroy'] as const;
const AFTER_RENAME = ['repo list', 'repo promote', 'cluster destroy'] as const;

const doc = (rule: PolicyDocument['defaults']): PolicyDocument => ({
  version: 1,
  defaults: rule,
});

describe('the hazard itself', () => {
  it('a renamed command makes its deny rule silently stop denying', () => {
    // An organization forbids the takeover of a repository.
    const policy = doc({ commands: { allow: ['repo *'], deny: ['repo takeover'] } });

    const ask = (commandPath: string) =>
      evaluatePolicy(policy, {
        userEmail: 'dev@example.com',
        orgRole: 'member',
        commandPath,
      });

    // Before the rename the rule works.
    expect(ask('repo takeover').allowed).toBe(false);

    // P4 renames the leaf to `repo promote` (spec 03 §5.4, R2-F16). The document
    // is untouched, still valid, still parses. And the forbidden operation is now
    // ALLOWED — no error, no warning, nothing in the audit trail saying the rule
    // died. THIS is why an unmatched deny is a hard failure and not a warning.
    expect(ask('repo promote').allowed).toBe(true);

    // The detector is what turns that silence into a refusal.
    expect(findStaleCommandGlobs(policy, AFTER_RENAME).deny).toEqual(['repo takeover']);
  });
});

describe('findStaleCommandGlobs', () => {
  it('says nothing when every glob matches a live command', () => {
    const policy = doc({ commands: { allow: ['repo *'], deny: ['repo takeover'] } });

    expect(findStaleCommandGlobs(policy, BEFORE_RENAME)).toEqual({ deny: [], allow: [] });
  });

  it('reports a stale allow glob separately from a stale deny glob', () => {
    const policy = doc({
      commands: { allow: ['machine query'], deny: ['repo takeover'] },
    });

    expect(findStaleCommandGlobs(policy, AFTER_RENAME)).toEqual({
      allow: ['machine query'],
      deny: ['repo takeover'],
    });
  });

  it('accepts a wildcard that spans segments', () => {
    // `repo *` reaches `repo list`, so it is live. A detector that demanded exact
    // paths would red on every real policy ever written.
    const policy = doc({ commands: { allow: ['repo *'], deny: ['cluster *'] } });

    expect(findStaleCommandGlobs(policy, AFTER_RENAME)).toEqual({ deny: [], allow: [] });
  });

  it('reports a wildcard whose whole subtree is gone', () => {
    const policy = doc({ commands: { allow: ['*'], deny: ['queue *'] } });

    expect(findStaleCommandGlobs(policy, AFTER_RENAME).deny).toEqual(['queue *']);
  });

  it('searches team and user rules, not only the defaults', () => {
    const policy: PolicyDocument = {
      version: 1,
      defaults: { commands: { allow: ['repo *'] } },
      teams: { platform: { commands: { allow: ['repo *'], deny: ['repo takeover'] } } },
      users: { 'dev@example.com': { commands: { allow: ['*'], deny: ['machine query'] } } },
    };

    // A deny buried in a team or user rule fails open exactly like one in the
    // defaults, so it has to be reachable by the detector.
    expect(findStaleCommandGlobs(policy, AFTER_RENAME).deny).toEqual([
      'machine query',
      'repo takeover',
    ]);
  });

  it('deduplicates a glob repeated across rules', () => {
    const policy: PolicyDocument = {
      version: 1,
      defaults: { commands: { allow: ['repo *'], deny: ['repo takeover'] } },
      teams: { platform: { commands: { allow: ['repo *'], deny: ['repo takeover'] } } },
    };

    expect(findStaleCommandGlobs(policy, AFTER_RENAME).deny).toEqual(['repo takeover']);
  });
});

describe('staleDenyRefusal', () => {
  it('names the glob and says a rename is the likely cause', () => {
    const message = staleDenyRefusal(['repo takeover']);

    // The author has to learn WHICH rule stopped being a rule, or they cannot
    // re-key it — and re-keying, not deleting, is almost always the right fix.
    expect(message).toContain('"repo takeover"');
    expect(message).toContain('renamed');
  });
});
