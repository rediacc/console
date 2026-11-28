import { describe, expect, it } from 'vitest';
import { disabledAiModes, mergePolicies } from '../merge.js';
import { type PolicyDocument, PolicyDocumentSchema, PolicyRuleSchema } from '../schema.js';

const doc = (partial: Partial<PolicyDocument> = {}): PolicyDocument =>
  PolicyDocumentSchema.parse({ version: 1, defaults: {}, ...partial });

const caller = { userEmail: 'ada@example.com', teamSlug: 'platform' };

describe('aiModesDisabled in the schema', () => {
  it('accepts auto and skip only', () => {
    expect(PolicyRuleSchema.safeParse({ aiModesDisabled: ['auto', 'skip'] }).success).toBe(true);
    expect(PolicyRuleSchema.safeParse({ aiModesDisabled: [] }).success).toBe(true);
    expect(PolicyRuleSchema.safeParse({ aiModesDisabled: ['ask'] }).success).toBe(false);
    expect(PolicyRuleSchema.safeParse({ aiModesDisabled: 'skip' }).success).toBe(false);
  });
});

describe('disabledAiModes: the org and team lists union', () => {
  it('disables nothing when neither policy sets a list', () => {
    expect(disabledAiModes(mergePolicies(doc(), doc()), caller)).toEqual([]);
    expect(disabledAiModes(mergePolicies(), caller)).toEqual([]);
  });

  it('a team cannot re-enable a mode the org disabled', () => {
    const org = doc({ defaults: { aiModesDisabled: ['skip'] } });
    const team = doc({
      defaults: { aiModesDisabled: [] },
      teams: { platform: { aiModesDisabled: [] } },
      users: { [caller.userEmail]: { aiModesDisabled: [] } },
    });
    expect(disabledAiModes(mergePolicies(org, team), caller)).toEqual(['skip']);
  });

  it('a team disables more than the org', () => {
    const org = doc({ defaults: { aiModesDisabled: ['skip'] } });
    const team = doc({ defaults: { aiModesDisabled: ['auto'] } });
    expect(disabledAiModes(mergePolicies(org, team), caller)).toEqual(['auto', 'skip']);
  });

  it('the org-level config reads the org list alone', () => {
    const org = doc({ defaults: { aiModesDisabled: ['auto'] } });
    expect(disabledAiModes(mergePolicies(org), caller)).toEqual(['auto']);
  });

  it('inside one document the most specific tier wins', () => {
    const org = doc({
      defaults: { aiModesDisabled: ['auto', 'skip'] },
      users: { [caller.userEmail]: { aiModesDisabled: ['skip'] } },
    });
    expect(disabledAiModes(mergePolicies(org), caller)).toEqual(['skip']);
    expect(disabledAiModes(mergePolicies(org), { userEmail: 'bob@example.com' })).toEqual([
      'auto',
      'skip',
    ]);
  });

  it('a team list the org locks is ignored and reported', () => {
    const org = doc({ locked: ['aiModesDisabled'] });
    const team = doc({ defaults: { aiModesDisabled: ['auto'] } });
    const effective = mergePolicies(org, team);
    expect(disabledAiModes(effective, caller)).toEqual([]);
    expect(effective.ignoredLocked).toEqual(['defaults.aiModesDisabled']);
  });
});
