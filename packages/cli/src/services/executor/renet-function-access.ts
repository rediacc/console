/**
 * Which renet access each bridge function needs, see {@link RenetAccess}.
 *
 * A `Record` over the generated {@link RenetFunctionName} union, so a renet
 * function added to the contract breaks tsc here until someone classifies it.
 * `'read-only'` functions run whatever renet the machine already has (with a
 * drift warning); everything that changes the machine, and everything that
 * runs an arbitrary command (`container_exec`, `repository_exec`), provisions.
 */

import {
  RENET_FUNCTIONS,
  type RenetFunctionName,
} from '@rediacc/shared/renet-contract/data/functions.generated';
import type { RenetAccess } from '../renet/renet-execution.js';

export const RENET_FUNCTION_ACCESS: Record<RenetFunctionName, RenetAccess> = {
  backup_browse: 'read-only',
  backup_delete: 'provision',
  backup_list: 'read-only',
  backup_pull: 'provision',
  backup_push: 'provision',
  backup_restore: 'provision',
  backup_snapshot: 'provision',
  backup_verify: 'read-only',
  ceph_client_mount: 'provision',
  ceph_client_unmount: 'provision',
  ceph_clone_delete: 'provision',
  ceph_clone_flatten: 'provision',
  ceph_clone_image: 'provision',
  ceph_clone_list: 'read-only',
  ceph_clone_mount: 'provision',
  ceph_clone_unmount: 'provision',
  ceph_image_create: 'provision',
  ceph_image_delete: 'provision',
  ceph_image_format: 'provision',
  ceph_image_info: 'read-only',
  ceph_image_list: 'read-only',
  ceph_image_map: 'provision',
  ceph_image_resize: 'provision',
  ceph_image_unmap: 'provision',
  ceph_snapshot_create: 'provision',
  ceph_snapshot_delete: 'provision',
  ceph_snapshot_list: 'read-only',
  ceph_snapshot_protect: 'provision',
  ceph_snapshot_rollback: 'provision',
  ceph_snapshot_unprotect: 'provision',
  container_exec: 'provision',
  container_inspect: 'read-only',
  container_kill: 'provision',
  container_list: 'read-only',
  container_logs: 'read-only',
  container_pause: 'provision',
  container_remove: 'provision',
  container_restart: 'provision',
  container_start: 'provision',
  container_stats: 'read-only',
  container_stop: 'provision',
  container_unpause: 'provision',
  kube_health: 'read-only',
  kube_kubeconfig: 'read-only',
  machine_ping: 'read-only',
  machine_ssh_test: 'read-only',
  machine_uninstall: 'provision',
  machine_version: 'read-only',
  network_used: 'read-only',
  repository_autostart_disable: 'provision',
  repository_autostart_disable_all: 'provision',
  repository_autostart_enable: 'provision',
  repository_autostart_enable_all: 'provision',
  repository_autostart_list: 'read-only',
  repository_cat: 'read-only',
  repository_commit: 'provision',
  repository_commit_meta: 'provision',
  repository_create: 'provision',
  repository_delete: 'provision',
  repository_diff: 'read-only',
  repository_down: 'provision',
  repository_down_all: 'provision',
  repository_exec: 'provision',
  repository_expand: 'provision',
  repository_fork: 'provision',
  repository_health: 'read-only',
  repository_info: 'read-only',
  repository_list: 'read-only',
  repository_log: 'read-only',
  repository_logs: 'read-only',
  repository_merge: 'provision',
  repository_mount: 'provision',
  repository_ownership: 'provision',
  repository_policy_get: 'read-only',
  repository_policy_set: 'provision',
  repository_promote: 'provision',
  repository_prune: 'provision',
  repository_resize: 'provision',
  repository_status: 'read-only',
  repository_template_apply: 'provision',
  repository_trim: 'provision',
  repository_unmount: 'provision',
  repository_up: 'provision',
  repository_up_all: 'provision',
  repository_validate: 'read-only',
  setup: 'provision',
};

const KNOWN_FUNCTIONS: ReadonlySet<string> = new Set<string>(RENET_FUNCTIONS);

/**
 * The access a dispatch of `functionName` needs. A name outside the contract is
 * `'read-only'`: an unclassified function must never swap the machine's binary.
 */
export function renetAccessFor(functionName: string | undefined): RenetAccess {
  if (functionName === undefined || !KNOWN_FUNCTIONS.has(functionName)) return 'read-only';
  return RENET_FUNCTION_ACCESS[functionName as RenetFunctionName];
}
