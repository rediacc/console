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

describe('replicate destinations', () => {
  const replica = (name: string, from?: string, target?: string): BackupStrategyDestination => ({
    ...dest(name, target),
    mode: 'replicate',
    ...(from === undefined ? {} : { from }),
  });
  const home = dest('primary');

  it('admits a replica of an enabled upload destination', () => {
    expect(reason([home, replica('copy', 'home', 'eu-west')])).toBeUndefined();
  });

  it('refuses a replica with no source', () => {
    expect(reason([home, replica('copy', undefined, 'eu-west')])).toMatch(/needs `from`/);
  });

  it('refuses a replica whose target is its source', () => {
    const msg = reason([home, replica('copy', 'home', 'home')]);
    expect(msg).toMatch(/duplicate|name the target "home"|into itself/);
    expect(reason([dest('up', 'eu-west'), replica('copy', 'eu-west', 'eu-west')])).toBeDefined();
  });

  it('refuses a source that no enabled upload destination writes to', () => {
    expect(reason([home, replica('copy', 'office', 'eu-west')])).toMatch(
      /"office".*not the target of another enabled upload destination/
    );
  });

  it('refuses a source whose upload destination is disabled (the scheduler passes enabled ones only)', () => {
    expect(reason([replica('copy', 'home', 'eu-west')])).toBeDefined();
  });

  it('refuses a chain: a replica of a replica', () => {
    const msg = reason([home, replica('a', 'home', 'eu-west'), replica('b', 'eu-west', 'office')]);
    expect(msg).toMatch(/itself a replicate destination/);
  });

  it('refuses a strategy whose destinations are all replicas', () => {
    expect(reason([replica('copy', 'home', 'eu-west')])).toMatch(
      /no machine would upload|not the target/
    );
  });

  it('still refuses an unregistered replica target', () => {
    expect(reason([home, replica('copy', 'home', 'ghost')], ['home'])).toMatch(
      /"ghost".*not a registered store/
    );
  });
});
