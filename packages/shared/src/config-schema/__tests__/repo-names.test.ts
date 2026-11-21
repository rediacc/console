/**
 * repoNamesByGuid joins a repository GUID to the name an operator knows it by.
 * The notices portal page and the CLI both print these names instead of GUIDs.
 */

import { describe, expect, it } from 'vitest';
import type { RdcConfig } from '../index.js';
import { machineOfPlacement, repoNamesByGuid, shortGuid } from '../repo-names.js';

const GRAND = '11111111-1111-4111-8111-111111111111';
const FORK = '22222222-2222-4222-8222-222222222222';
const RBD = '33333333-3333-4333-8333-333333333333';
const GONE = '44444444-4444-4444-8444-444444444444';

const config = {
  resources: {
    datastores: {
      fast: { backend: { kind: 'local', machine: 'box1', path: '/mnt/fast' } },
      pool: { backend: { kind: 'rbd', pool: 'p', image: 'i' } },
    },
    repositories: {
      mail: {
        placement: { datastore: 'fast' },
        grand: 'prod',
        tags: { prod: { repositoryGuid: GRAND }, test: { repositoryGuid: FORK } },
      },
      wiki: {
        placement: { datastore: 'pool' },
        grand: 'prod',
        tags: { prod: { repositoryGuid: RBD } },
      },
    },
    deletedRepositories: [{ name: 'old', tag: 'prod', repositoryGuid: GONE }],
  },
} as unknown as RdcConfig;

describe('repoNamesByGuid', () => {
  const names = repoNamesByGuid(config);

  it('maps the grand tag to the bare family and a fork to name:tag', () => {
    expect(names.get(GRAND)).toMatchObject({
      ref: 'mail',
      family: 'mail',
      tag: 'prod',
      isGrand: true,
      deleted: false,
    });
    expect(names.get(FORK)).toMatchObject({ ref: 'mail:test', tag: 'test', isGrand: false });
  });

  it('gives the machine of a local datastore placement and null for RBD', () => {
    expect(names.get(GRAND)).toMatchObject({ machine: 'box1', datastore: 'fast' });
    expect(names.get(RBD)).toMatchObject({ machine: null, datastore: 'pool' });
  });

  it('marks a deletedRepositories GUID deleted', () => {
    expect(names.get(GONE)).toMatchObject({
      ref: 'old:prod',
      family: 'old',
      deleted: true,
      machine: null,
    });
  });

  it('leaves an unknown GUID absent', () => {
    expect(names.has('99999999-9999-4999-8999-999999999999')).toBe(false);
  });

  it('a GUID that is both live and in deletedRepositories stays live', () => {
    const both = {
      resources: {
        ...config.resources,
        deletedRepositories: [{ name: 'mail', tag: 'prod', repositoryGuid: GRAND }],
      },
    } as unknown as RdcConfig;
    expect(repoNamesByGuid(both).get(GRAND)).toMatchObject({ ref: 'mail', deleted: false });
  });

  it('shortGuid keeps the first 8 characters', () => {
    expect(shortGuid(GRAND)).toBe('11111111');
  });

  it('machineOfPlacement resolves a machine placement directly', () => {
    expect(machineOfPlacement({ machine: 'm' }, {})).toEqual({ machine: 'm', datastore: null });
    expect(machineOfPlacement(undefined, {})).toEqual({ machine: null, datastore: null });
  });

  it('machineOfPlacement names no machine for a datastore the config does not list', () => {
    expect(machineOfPlacement({ datastore: 'ghost' }, {})).toEqual({
      machine: null,
      datastore: 'ghost',
    });
  });
});
