/**
 * The executor refuses to authorize against a policy whose deny rules protect
 * nothing.
 *
 * `readPolicyDocument` already refuses a MALFORMED document, on the grounds that
 * "quietly ignoring them would be the worst possible failure, since it would look
 * like the rules were in force." A stale deny glob is that failure exactly, only
 * quieter: the document is well-formed, it parses, and the command it forbids has
 * been renamed, so the rule denies nothing and the forbidden command runs.
 *
 * These tests are written against the LIVE contract on purpose. `repo takeover`
 * is not a hypothetical stale name — it is the real pre-P4 name of what is now
 * `repo promote` (spec 03 §5.4), so this is the rename that would have fired.
 */
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { describe, expect, it } from 'vitest';
import { authorize } from '../policy.js';
import type { SessionPrincipal } from '../sessions.js';

const PRINCIPAL: SessionPrincipal = {
  orgId: 'org-1',
  teamId: null,
  userId: 'user-1',
  userEmail: 'dev@example.com',
  orgRole: 'member',
};

const configWithPolicy = (policy: unknown): RdcConfig => ({ policy }) as unknown as RdcConfig;

describe('stale deny globs at the executor', () => {
  it('refuses to authorize anything while a deny rule names a command that does not exist', () => {
    const config = configWithPolicy({
      version: 1,
      defaults: { commands: { allow: ['repo *'], deny: ['repo takeover'] } },
    });

    // Without this refusal, `repo promote` would be ALLOWED here: it matches
    // `repo *`, and the deny that was written to stop it no longer matches
    // anything. The organization's rule would have died in the rename.
    expect(() => authorize({ principal: PRINCIPAL, commandPath: 'repo promote', config })).toThrow(
      /repo takeover/
    );
  });

  it('says a rename is the likely cause, so the author can re-key rather than delete', () => {
    const config = configWithPolicy({
      version: 1,
      defaults: { commands: { allow: ['repo *'], deny: ['repo takeover'] } },
    });

    expect(() => authorize({ principal: PRINCIPAL, commandPath: 'repo list', config })).toThrow(
      /renamed/
    );
  });

  it('authorizes normally when every deny rule names a live command', () => {
    const config = configWithPolicy({
      version: 1,
      defaults: { commands: { allow: ['repo *'], deny: ['repo delete'] } },
    });

    // The detector must not cry wolf: a policy whose rules all resolve has to
    // keep working, allow side and deny side both.
    expect(authorize({ principal: PRINCIPAL, commandPath: 'repo list', config }).allowed).toBe(
      true
    );
    expect(() => authorize({ principal: PRINCIPAL, commandPath: 'repo delete', config })).toThrow(
      /denies/
    );
  });

  it('tolerates a stale ALLOW glob, which already fails closed', () => {
    // `machine query` was renamed to `machine status`. The allow glob is stale,
    // but a stale allow refuses the command rather than permitting it — it is
    // self-announcing. Refusing to start over one would turn a safe condition
    // into a total executor outage, so only the deny side is fatal.
    const config = configWithPolicy({
      version: 1,
      defaults: { commands: { allow: ['machine query', 'repo list'] } },
    });

    expect(authorize({ principal: PRINCIPAL, commandPath: 'repo list', config }).allowed).toBe(
      true
    );
  });
});
