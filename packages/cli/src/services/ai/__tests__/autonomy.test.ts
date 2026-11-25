/**
 * The autonomy gate (AI3 of agent/plans/PLAN-console-ai-assistant.md): which calls `decide()`
 * allowed still wait for the user, per mode and risk; a disabled mode read as Ask; exact-only
 * chat allow rules.
 */

import type { DecisionTarget } from '@rediacc/shared/policy';
import { describe, expect, it } from 'vitest';
import {
  AI_HOLD_ASK,
  AI_HOLD_DESTRUCTIVE,
  AI_HOLD_GRAND,
  AI_HOLD_JUDGE,
  AiConversationStore,
  autonomyHold,
  DEFAULT_AI_MODE,
  effectiveMode,
  riskOf,
} from '../autonomy.js';

const principal = {
  orgId: 'org-1',
  teamId: null,
  userId: 'user-owner',
  userEmail: 'owner@example.com',
  orgRole: 'owner' as const,
};

const MODES = ['ask', 'auto', 'skip'] as const;

const hold = (
  mode: (typeof MODES)[number],
  risk: Parameters<typeof autonomyHold>[0]['risk'],
  extra: { exactlyAllowed?: boolean; judge?: () => Promise<boolean> } = {}
) => autonomyHold({ mode, risk, pathKey: 'repo up', exactlyAllowed: false, ...extra });

describe('riskOf', () => {
  const fork: DecisionTarget = { repo: { name: 'shop', state: 'fork' }, isOpsVm: false };
  const grand: DecisionTarget = { repo: { name: 'shop', state: 'grand' }, isOpsVm: false };
  const unresolved: DecisionTarget = {
    repo: { name: 'shop', state: 'unresolved' },
    isOpsVm: false,
  };
  const opsGrand: DecisionTarget = { ...grand, isOpsVm: true };

  it('reads severity, preview and the grand target', () => {
    expect(riskOf({ severity: 'none', preview: false, target: grand })).toBe('safe');
    expect(riskOf({ severity: 'destructive', preview: true, target: fork })).toBe('safe');
    expect(riskOf({ severity: 'caution', preview: false, target: fork })).toBe('caution');
    expect(riskOf({ severity: 'destructive', preview: false, target: fork })).toBe('destructive');
    expect(riskOf({ severity: 'caution', preview: false, target: grand })).toBe('grand');
    expect(riskOf({ severity: 'caution', preview: false, target: unresolved })).toBe('grand');
    expect(riskOf({ severity: 'caution', preview: false, target: opsGrand })).toBe('caution');
  });
});

describe('autonomyHold', () => {
  it('runs a read in every mode', async () => {
    for (const mode of MODES) expect(await hold(mode, 'safe')).toBeNull();
  });

  it('holds a grand target in every mode, Skip and an exact rule included', async () => {
    for (const mode of MODES) {
      expect(
        await hold(mode, 'grand', { exactlyAllowed: true, judge: async () => true })
      ).toMatchObject({
        code: AI_HOLD_GRAND,
      });
    }
  });

  it('holds a destructive command in Skip mode too', async () => {
    for (const mode of MODES) {
      expect(await hold(mode, 'destructive', { exactlyAllowed: true })).toMatchObject({
        code: AI_HOLD_DESTRUCTIVE,
      });
    }
  });

  it('holds a caution command in Ask, runs it in Skip, and asks the judge in Auto', async () => {
    expect(await hold('ask', 'caution')).toMatchObject({ code: AI_HOLD_ASK });
    expect(await hold('skip', 'caution')).toBeNull();
    expect(await hold('auto', 'caution', { judge: async () => true })).toBeNull();
    expect(await hold('auto', 'caution', { judge: async () => false })).toMatchObject({
      code: AI_HOLD_JUDGE,
    });
    expect(await hold('auto', 'caution')).toMatchObject({ code: AI_HOLD_JUDGE });
  });

  it('never asks the judge outside Auto mode', async () => {
    let asked = 0;
    const judge = () => {
      asked += 1;
      return Promise.resolve(true);
    };
    await hold('ask', 'caution', { judge });
    await hold('skip', 'caution', { judge });
    await hold('auto', 'destructive', { judge });
    expect(asked).toBe(0);
  });

  it('lets an exact rule run a caution command in Ask mode', async () => {
    expect(await hold('ask', 'caution', { exactlyAllowed: true })).toBeNull();
  });
});

describe('effectiveMode', () => {
  it('reads a disabled mode as Ask and leaves the rest', () => {
    expect(effectiveMode('skip', ['skip'])).toBe('ask');
    expect(effectiveMode('auto', ['auto', 'skip'])).toBe('ask');
    expect(effectiveMode('auto', ['skip'])).toBe('auto');
    expect(effectiveMode('ask', ['auto', 'skip'])).toBe('ask');
  });
});

describe('AiConversationStore', () => {
  const UP = { pathKey: 'repo up', params: {}, positionals: { ref: 'shop:trial' } };

  it('starts every conversation in Ask, and keeps modes per principal and conversation', () => {
    const store = new AiConversationStore();
    expect(DEFAULT_AI_MODE).toBe('ask');
    store.set(principal, 'conv-1', 'skip');
    expect(store.get(principal, 'conv-1')).toBe('skip');
    expect(store.get(principal, 'conv-2')).toBe('ask');
    expect(store.get({ ...principal, userId: 'user-other' }, 'conv-1')).toBe('ask');
  });

  it('matches an allow rule on the exact argv only', () => {
    const store = new AiConversationStore();
    store.allowExact(principal, 'conv-1', UP);
    expect(store.allowsExact(principal, 'conv-1', { ...UP, params: {} })).toBe(true);
    expect(store.allowsExact(principal, 'conv-1', { ...UP, params: { 'no-start': true } })).toBe(
      false
    );
    expect(store.allowsExact(principal, 'conv-1', { ...UP, positionals: { ref: 'shop:*' } })).toBe(
      false
    );
    expect(store.allowsExact(principal, 'conv-2', UP)).toBe(false);
    expect(store.allowsExact({ ...principal, userId: 'user-other' }, 'conv-1', UP)).toBe(false);
  });
});
