import { RENET_FUNCTIONS } from '@rediacc/shared/renet-contract/data/functions.generated';
import { describe, expect, it } from 'vitest';
import { RENET_FUNCTION_ACCESS, renetAccessFor } from '../renet-function-access.js';

/**
 * The functions that may run against whatever renet a machine already has.
 * Changing this list is a deliberate act: a function moved here stops updating
 * the machine's binary; a function moved out starts replacing it.
 */
const EXPECTED_READ_ONLY = [
  'backup_browse',
  'backup_list',
  'backup_verify',
  'ceph_clone_list',
  'ceph_image_info',
  'ceph_image_list',
  'ceph_snapshot_list',
  'container_inspect',
  'container_list',
  'container_logs',
  'container_stats',
  'kube_health',
  'kube_kubeconfig',
  'machine_ping',
  'machine_ssh_test',
  'machine_version',
  'repository_autostart_list',
  'repository_cat',
  'repository_diff',
  'repository_health',
  'repository_info',
  'repository_list',
  'repository_log',
  'repository_logs',
  'repository_policy_get',
  'repository_status',
  'repository_validate',
].sort();

describe('RENET_FUNCTION_ACCESS', () => {
  it('classifies exactly the expected functions as read-only, in both directions', () => {
    const readOnly = Object.entries(RENET_FUNCTION_ACCESS)
      .filter(([, access]) => access === 'read-only')
      .map(([name]) => name)
      .sort();
    expect(readOnly).toEqual(EXPECTED_READ_ONLY);
  });

  it('classifies every contract function', () => {
    expect(Object.keys(RENET_FUNCTION_ACCESS).sort()).toEqual([...RENET_FUNCTIONS].sort());
  });

  it('keeps arbitrary-command functions on the provision side', () => {
    expect(RENET_FUNCTION_ACCESS.container_exec).toBe('provision');
    expect(RENET_FUNCTION_ACCESS.repository_exec).toBe('provision');
  });

  it('maps a name outside the contract to read-only', () => {
    expect(renetAccessFor('nope')).toBe('read-only');
    expect(renetAccessFor(undefined)).toBe('read-only');
    expect(renetAccessFor('repository_up')).toBe('provision');
    expect(renetAccessFor('repository_list')).toBe('read-only');
  });
});
