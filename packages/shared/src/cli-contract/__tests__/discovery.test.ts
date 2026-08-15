/**
 * Discovery-registry integrity (§A2). Proves every resource kind has a source,
 * every command source names a command that exists in the live contract, and
 * every `needs` entry is itself a config-sourced kind (so a picker's context can
 * always be resolved without recursion into another command).
 */

import { describe, expect, it } from 'vitest';
import {
  DISCOVERY_FAMILIES,
  type DiscoveryFamily,
  RESOURCE_DISCOVERY,
  RESOURCE_KINDS,
} from '../discovery.js';
import { getCommand } from '../index.js';
import type { ResourceKind } from '../types.js';

/** The kinds whose values come straight from a config family. */
const CONFIG_SOURCED = new Set<ResourceKind>(
  RESOURCE_KINDS.filter((k) => RESOURCE_DISCOVERY[k].source === 'config')
);

describe('RESOURCE_DISCOVERY completeness', () => {
  it('has an entry for every resource kind', () => {
    for (const kind of RESOURCE_KINDS) {
      expect(RESOURCE_DISCOVERY[kind], `missing discovery for "${kind}"`).toBeDefined();
    }
  });

  it('covers all 12 kinds and no more', () => {
    expect(RESOURCE_KINDS).toHaveLength(12);
    expect(Object.keys(RESOURCE_DISCOVERY).sort()).toEqual([...RESOURCE_KINDS].sort());
  });
});

describe('config-sourced discovery', () => {
  it('names a real config family', () => {
    const families = new Set<DiscoveryFamily>(DISCOVERY_FAMILIES);
    for (const kind of RESOURCE_KINDS) {
      const src = RESOURCE_DISCOVERY[kind];
      if (src.source !== 'config') continue;
      expect(families.has(src.family), `${kind} → unknown family "${src.family}"`).toBe(true);
    }
  });
});

describe('command-sourced discovery', () => {
  it('names a command that resolves in the live contract', () => {
    for (const kind of RESOURCE_KINDS) {
      const src = RESOURCE_DISCOVERY[kind];
      if (src.source !== 'command') continue;
      expect(getCommand(src.pathKey), `${kind} → unknown command "${src.pathKey}"`).toBeDefined();
    }
  });

  it('has a non-empty extract path', () => {
    for (const kind of RESOURCE_KINDS) {
      const src = RESOURCE_DISCOVERY[kind];
      if (src.source !== 'command') continue;
      expect(src.extract.length, `${kind} has an empty extract`).toBeGreaterThan(0);
    }
  });

  it('lists only config-sourced kinds in `needs`', () => {
    for (const kind of RESOURCE_KINDS) {
      const src = RESOURCE_DISCOVERY[kind];
      if (src.source !== 'command') continue;
      for (const need of src.needs) {
        expect(
          CONFIG_SOURCED.has(need),
          `${kind} needs "${need}", which is not config-sourced`
        ).toBe(true);
      }
    }
  });
});
