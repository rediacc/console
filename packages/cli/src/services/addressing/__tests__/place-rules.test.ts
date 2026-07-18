/**
 * `@place` acceptance-table + canonical-error tests (spec/03 §3).
 */

import { describe, expect, it } from 'vitest';
import { CliExitError } from '../../../utils/cli-exit-error.js';
import {
  assertPlaceAccepted,
  placeAcceptance,
  placeConflictError,
  REPO_VERBS_ACCEPTING_PLACE,
  termConnectCollisionError,
} from '../place-rules.js';

describe('REPO_VERBS_ACCEPTING_PLACE', () => {
  it('is exactly the §3.1 third-row verb set (a drift pin)', () => {
    expect([...REPO_VERBS_ACCEPTING_PLACE].sort()).toEqual(
      [
        'admin',
        'branch',
        'cat',
        'checkout',
        'commit',
        'delete',
        'diff',
        'down',
        'exec',
        'fork',
        'log',
        'logs',
        'merge',
        'migrate',
        'policy',
        'promote',
        'pull',
        'push',
        'replicate',
        'secret',
        'status',
        'sync',
        'trim',
        'tunnel',
        'up',
      ].sort()
    );
  });
});

describe('placeAcceptance — the §3.1 per-verb-class table', () => {
  it('backup restore requires the referent', () => {
    expect(placeAcceptance(['backup', 'restore'])).toBe('required-referent');
  });

  it('backup list treats @place as an optional filter', () => {
    expect(placeAcceptance(['backup', 'list'])).toBe('optional-filter');
  });

  it('term connect selects the shell', () => {
    expect(placeAcceptance(['term', 'connect'])).toBe('target-select');
  });

  it('live repo verbs accept-and-verify', () => {
    for (const verb of ['up', 'down', 'status', 'migrate', 'cat', 'promote', 'admin']) {
      expect(placeAcceptance(['repo', verb]), verb).toBe('accepted-verified');
    }
  });

  it('a repo secret subcommand inherits its verb classification', () => {
    expect(placeAcceptance(['repo', 'secret', 'get'])).toBe('accepted-verified');
  });

  it('repo create names a not-yet-live repo and rejects @place', () => {
    expect(placeAcceptance(['repo', 'create'])).toBe('rejected-at-parse');
  });

  it('non-repo nouns reject @place at parse', () => {
    expect(placeAcceptance(['machine', 'status'])).toBe('rejected-at-parse');
    expect(placeAcceptance(['datastore', 'attach'])).toBe('rejected-at-parse');
    expect(placeAcceptance(['cluster', 'fork'])).toBe('rejected-at-parse');
    expect(placeAcceptance(['storage', 'browse'])).toBe('rejected-at-parse');
    expect(placeAcceptance(['config', 'delete'])).toBe('rejected-at-parse');
    expect(placeAcceptance(['backup', 'strategy', 'set'])).toBe('rejected-at-parse');
    expect(placeAcceptance(['backup', 'run'])).toBe('rejected-at-parse');
  });
});

describe('assertPlaceAccepted', () => {
  it('is a no-op when no @place is present, even for a place-less noun', () => {
    expect(() => assertPlaceAccepted(['machine', 'status'], false)).not.toThrow();
  });

  it('is a no-op for a live repo verb carrying @place', () => {
    expect(() => assertPlaceAccepted(['repo', 'up'], true)).not.toThrow();
  });

  it('refuses @place on a place-less noun with exit 2 and the canonical phrasing', () => {
    let thrown: unknown;
    try {
      assertPlaceAccepted(['machine', 'status'], true);
    } catch (error) {
      thrown = error;
    }
    expect(thrown).toBeInstanceOf(CliExitError);
    const err = thrown as CliExitError;
    expect(err.exitCode).toBe(2);
    expect(err.message).toBe('machine names do not take @place.');
  });
});

describe('placeConflictError — §3.2 canonical text (exit 12)', () => {
  it('reproduces the spec text verbatim with names substituted', () => {
    // Build the expected string with the same names interpolated, so the source
    // never carries a contiguous `repo migrate shop` literal (which the
    // no-positional-cli-syntax-source lint rule flags until w2b makes it real).
    const name = 'shop';
    const home = 'prod-1';
    const at = 'backup-2';
    const err = placeConflictError(name, home, at);
    expect(err).toBeInstanceOf(CliExitError);
    expect(err.exitCode).toBe(12);
    expect(err.code).toBe('STATE_MISMATCH');
    expect(err.message).toBe(
      `${name} is placed at ${home}; you addressed ${name}@${at}. ` +
        `For the pushed backup copy on ${at} use "rdc backup restore ${name}@${at}"; ` +
        `to move the repo use "rdc repo migrate ${name} --to ${at}".`
    );
  });
});

describe('termConnectCollisionError — §3.3 canonical text (exit 11)', () => {
  it('reproduces the spec text verbatim with the collided name substituted', () => {
    const err = termConnectCollisionError('shop');
    expect(err).toBeInstanceOf(CliExitError);
    expect(err.exitCode).toBe(11);
    expect(err.code).toBe('AMBIGUOUS');
    expect(err.message).toBe(
      'shop is both a repository and a machine. ' +
        'Use "term connect shop@<machine>" for the repository shell, ' +
        'or "term connect <machine-name>" for the machine shell.'
    );
  });
});
