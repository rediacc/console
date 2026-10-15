/**
 * Two writers of one config file must not lose each other's records. A LocalResourceState is the view a command loads once at start; a long command persisted that whole view late, so a record a shorter command stored in the meantime was written away.
 *
 * Live, 2026-10-15: `repo create rca74-a` exited 0 with its entry in dev.json, and the entry was gone a minute later while a second command used the same config. Real files under the test's config home; every writer goes through the storage lock.
 */

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { getConfigDir } from '@rediacc/shared/paths';
import { beforeEach, describe, expect, it } from 'vitest';
import { configFileStorage } from '../../../adapters/config-file-storage.js';
import type { RdcConfig, RepositoryConfig } from '../../../types/index.js';
import { LocalResourceState } from '../resource-state.js';

const NAME = 'concurrent-writers';

function configPath(): string {
  return join(getConfigDir(), `${NAME}.json`);
}

function onDisk(): RdcConfig {
  return JSON.parse(readFileSync(configPath(), 'utf8')) as RdcConfig;
}

function repo(n: number): RepositoryConfig {
  return {
    repositoryGuid: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`,
    credential: `credential-${n}`,
  } as RepositoryConfig;
}

/** A writer as a command runs one: load the view once, edit it later, persist. */
async function openView(): Promise<LocalResourceState> {
  configFileStorage.clearCache();
  return LocalResourceState.load(await configFileStorage.loadDecrypted(NAME), NAME);
}

beforeEach(() => {
  mkdirSync(getConfigDir(), { recursive: true });
  writeFileSync(
    configPath(),
    JSON.stringify({
      schemaVersion: 3,
      id: '0b7e4f2a-1c3d-4e5f-8a9b-0c1d2e3f4a5b',
      version: 1,
      encryption: { mode: 'plaintext' },
      resources: {
        machines: { m1: { ip: '192.0.2.1', user: 'root' } },
        repositories: { seed: { grand: 'latest', tags: { latest: repo(0) } } },
      },
    })
  );
  configFileStorage.clearCache();
});

describe('concurrent writers of one config keep every record', () => {
  it('a record stored after a view was loaded survives that view persisting', async () => {
    const long = await openView();
    const quick = await openView();

    const quickRepos = quick.getRepositories();
    quickRepos['rca74-a'] = repo(1);
    await quick.setRepositories(quickRepos);

    const longRepos = long.getRepositories();
    longRepos.other = repo(2);
    await long.setRepositories(longRepos);

    expect(Object.keys(onDisk().resources?.repositories ?? {}).sort()).toEqual([
      'other',
      'rca74-a',
      'seed',
    ]);
  });

  it('a removal and an addition by two stale views both land, and other buckets are untouched', async () => {
    const remover = await openView();
    const adder = await openView();

    const machines = adder.getMachines();
    machines.m2 = { ip: '192.0.2.2', user: 'root' };
    await adder.setMachines(machines);

    const repos = remover.getRepositories();
    delete repos['seed:latest'];
    await remover.setRepositories(repos);

    const doc = onDisk();
    expect(doc.resources?.repositories).toBeUndefined();
    expect(Object.keys(doc.resources?.machines ?? {}).sort()).toEqual(['m1', 'm2']);
  });

  it('twenty concurrent writers, each loaded before any persisted, lose nothing', async () => {
    const views = await Promise.all(Array.from({ length: 20 }, () => openView()));

    await Promise.all(
      views.map((view, i) => {
        const repos = view.getRepositories();
        repos[`r${i}`] = repo(100 + i);
        return view.setRepositories(repos);
      })
    );

    const names = Object.keys(onDisk().resources?.repositories ?? {});
    expect(names).toHaveLength(21);
    for (let i = 0; i < 20; i++) expect(names).toContain(`r${i}`);
  });

  it('a view keeps writing correctly after its own persist rebased it', async () => {
    const view = await openView();
    const other = await openView();

    const otherRepos = other.getRepositories();
    otherRepos.theirs = repo(3);
    await other.setRepositories(otherRepos);

    const first = view.getRepositories();
    first.mine = repo(4);
    await view.setRepositories(first);
    const second = view.getRepositories();
    delete second['mine:latest'];
    await view.setRepositories(second);

    expect(Object.keys(onDisk().resources?.repositories ?? {}).sort()).toEqual(['seed', 'theirs']);
  });
});
