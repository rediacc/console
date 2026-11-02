/**
 * The J22 invariant (PLAN-detached-jobs): a verb leaves BACKGROUND_UNSAFE in the same change that converts it.
 *
 * BACKGROUND_UNSAFE (packages/cli/src/services/executor/proxy-command.ts) lists the verbs `--background` must refuse
 * until each runs as one job. CONVERTED lists the verbs whose conversion box has landed. A verb in both is a converted
 * verb still refused, or a refused verb claimed converted; either is a box ticked against the wrong state.
 */
import { CLI_CONTRACT } from '@rediacc/shared/cli-contract';
import { describe, expect, it } from 'vitest';
import { assertDetachable, BACKGROUND_UNSAFE } from '../../executor/proxy-command.js';
import { CONVERTED, JOB_PLANS } from '../plans.js';

const contract = new Map(CLI_CONTRACT.commands.map((c) => [c.pathKey, c]));
const unsafe = Object.keys(BACKGROUND_UNSAFE).sort((a, b) => a.localeCompare(b));

describe('BACKGROUND_UNSAFE and CONVERTED', () => {
  it('each of the ten J0 verbs is either still refused or converted, and nothing else is refused', () => {
    const ten = [
      'backup restore',
      'backup snapshot',
      'backup verify',
      'repo checkout',
      'repo commit',
      'repo fork',
      'repo migrate',
      'repo pull',
      'repo push',
      'repo up',
    ];
    expect(ten.filter((verb) => !(verb in BACKGROUND_UNSAFE) && !CONVERTED.has(verb))).toEqual([]);
    expect(unsafe.filter((verb) => !ten.includes(verb))).toEqual([]);
  });

  it('no verb is both refused and converted', () => {
    expect(unsafe.filter((verb) => CONVERTED.has(verb))).toEqual([]);
  });

  it('every refused verb is a detachable machine-plane command with a job plan', () => {
    for (const verb of unsafe) {
      const entry = contract.get(verb);
      expect(entry, `${verb} is not in the contract`).toBeDefined();
      expect(entry?.plane, verb).toBe('machine');
      expect(entry?.detachable, `${verb} is not detachable, so the entry is dead`).toBe(true);
      expect(JOB_PLANS[verb], `${verb} has no job plan`).toBeDefined();
    }
  });

  it('every refused verb is refused with its reason', () => {
    for (const verb of unsafe) {
      expect(() => assertDetachable(verb, contract.get(verb)), verb).toThrow(
        BACKGROUND_UNSAFE[verb]
      );
    }
  });

  it('every converted verb has a job plan and is no longer refused', () => {
    for (const verb of CONVERTED) {
      expect(JOB_PLANS[verb], `${verb} has no job plan`).toBeDefined();
      expect(BACKGROUND_UNSAFE[verb], verb).toBeUndefined();
    }
  });
});
