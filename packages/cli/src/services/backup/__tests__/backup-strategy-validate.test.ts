/**
 * Destination targets: one enabled destination per store, and a target must be a registered store when the CLI has the
 * account's store list. Offline (no list) the validator checks shape and duplicates only.
 */
import { describe, expect, it } from 'vitest';
import type { BackupStrategyConfig, BackupStrategyDestination } from '../../../types/index.js';
import {
  destinationTarget,
  strategyUnschedulableReason,
  uncheckedTargets,
} from '../backup-strategy-validate.js';

const dest = (name: string, target?: string): BackupStrategyDestination => ({
  name,
  kind: 'hosted-service',
  ...(target === undefined ? {} : { target }),
});

const strategyOf = (destinations: BackupStrategyDestination[]): BackupStrategyConfig => ({
  schedule: '0 3 * * *',
  destinations,
});

const reason = (destinations: BackupStrategyDestination[], stores?: readonly string[]) =>
  strategyUnschedulableReason(strategyOf(destinations), destinations, stores);

describe('destination targets', () => {
  it('treats an absent target as home', () => {
    expect(destinationTarget(dest('a'))).toBe('home');
    expect(destinationTarget(dest('a', 'eu-west'))).toBe('eu-west');
  });

  it('admits two destinations on different targets, which the old single-endpoint rule refused', () => {
    expect(reason([dest('a'), dest('b', 'eu-west')])).toBeUndefined();
  });

  it('refuses two enabled destinations on one target, naming it', () => {
    expect(reason([dest('a', 'eu-west'), dest('b', 'eu-west')])).toMatch(/target "eu-west"/);
  });

  it('counts an absent target and an explicit home as the same store', () => {
    expect(reason([dest('a'), dest('b', 'home')])).toMatch(/target "home"/);
  });

  it('refuses a target that is not a store id', () => {
    expect(reason([dest('a', 'Not A Slug')])).toMatch(/not a store id/);
  });

  it('refuses an unregistered target and lists the registered ids', () => {
    const msg = reason([dest('a'), dest('b', 'ghost')], ['home', 'eu-west']);
    expect(msg).toMatch(/"ghost".*not a registered store/);
    expect(msg).toMatch(/home, eu-west/);
  });

  it('admits registered targets', () => {
    expect(reason([dest('a'), dest('b', 'eu-west')], ['home', 'eu-west'])).toBeUndefined();
  });

  it('checks shape and duplicates only offline, and reports which targets went unchecked', () => {
    const list = [dest('a'), dest('b', 'ghost')];
    expect(reason(list)).toBeUndefined();
    expect(uncheckedTargets(list, undefined)).toEqual(['ghost']);
    expect(uncheckedTargets(list, ['home'])).toEqual([]);
  });
});
