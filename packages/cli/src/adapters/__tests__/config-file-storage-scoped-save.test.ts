/**
 * Review finding 6b10a50c.1: a whole-document save() under a request scope with a
 * writeback was replayed as the stale document itself, so a replay after a lost
 * compare-and-swap overwrote another device's concurrent change. The save is now
 * replayed as its edit on the newest copy.
 */

import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { describe, expect, it } from 'vitest';
import {
  type ConfigWriteback,
  createOutputState,
  createRequestConfigScope,
  runInRequestContext,
} from '../../services/core/request-context.js';
import { ConfigFileStorage } from '../config-file-storage.js';
import { omitKey } from '../../utils/omit-key.js';

function base(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-0000000000d1',
    version: 4,
    resources: {
      machines: {
        m1: { ip: '10.0.0.1', user: 'root', port: 22 },
        old: { ip: '10.0.0.9', user: 'root', port: 22 },
      },
      repositories: {},
    },
    state: {},
    encryption: { mode: 'plaintext' },
  } as unknown as RdcConfig;
}

/** A store whose first push loses to another device adding machine `laptop`. */
function racingWriteback(start: RdcConfig): {
  writeback: ConfigWriteback;
  stored: () => RdcConfig;
} {
  let stored = structuredClone(start);
  let raced = false;
  return {
    stored: () => stored,
    writeback: {
      write(edit) {
        let next = edit(structuredClone(stored));
        if (!raced) {
          raced = true;
          stored = {
            ...stored,
            version: stored.version + 1,
            resources: {
              ...stored.resources,
              machines: {
                ...stored.resources?.machines,
                laptop: { ip: '10.0.0.7', user: 'root', port: 22 },
              },
            },
          } as RdcConfig;
          next = edit(structuredClone(stored));
        }
        stored = { ...next, version: stored.version + 1 } as RdcConfig;
        return Promise.resolve(stored);
      },
    },
  };
}

async function saveInScope(mutate: (config: RdcConfig) => RdcConfig): Promise<RdcConfig> {
  const start = base();
  const { writeback, stored } = racingWriteback(start);
  const scope = { ...createRequestConfigScope(start), writeback };
  const storage = new ConfigFileStorage(mkdtempSync(path.join(tmpdir(), 'rdc-scoped-save-')));
  await runInRequestContext(
    { output: createOutputState(), stdout: [], stderr: [], config: scope },
    async () => {
      const read = await storage.load();
      await storage.save(mutate(read));
    }
  );
  return stored();
}

describe('save() under a request scope replays its edit, not its document', () => {
  it("keeps another device's concurrent machine when the first push loses", async () => {
    const stored = await saveInScope((read) => ({
      ...read,
      resources: {
        ...read.resources,
        machines: { ...read.resources?.machines, m1: { ip: '10.0.0.2', user: 'root', port: 22 } },
      },
    }));
    expect(
      Object.keys(stored.resources?.machines ?? {}).sort((x, y) => x.localeCompare(y))
    ).toEqual(['laptop', 'm1', 'old']);
    expect(stored.resources?.machines?.m1?.ip).toBe('10.0.0.2');
  });

  it('a key the caller dropped is deleted on the newest copy, the concurrent one kept', async () => {
    const stored = await saveInScope((read) => {
      const machines = omitKey(read.resources?.machines ?? {}, 'old');
      return { ...read, resources: { ...read.resources, machines } };
    });
    expect(
      Object.keys(stored.resources?.machines ?? {}).sort((x, y) => x.localeCompare(y))
    ).toEqual(['laptop', 'm1']);
  });

  it('an edit made in place on the loaded object is still pushed', async () => {
    const stored = await saveInScope((read) => {
      const machines = read.resources?.machines;
      if (!machines) throw new Error('the loaded config has no machines');
      machines.m1 = { ip: '10.0.0.3', user: 'root', port: 22 };
      return read;
    });
    expect(stored.resources?.machines?.m1?.ip).toBe('10.0.0.3');
    expect(
      Object.keys(stored.resources?.machines ?? {}).sort((x, y) => x.localeCompare(y))
    ).toEqual(['laptop', 'm1', 'old']);
  });
});
