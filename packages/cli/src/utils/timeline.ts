/**
 * Unified step timeline rendering for CLI commands.
 * Merges CLI-side steps (config, SSH, provision) with renet-side steps
 * (LUKS, Docker, compose) into a single timeline.
 */

/** Labels shown while step is in progress (spinner). */
const activeLabels: Record<string, string> = {
  checkpoint: 'Creating checkpoint',
  repo_create: 'Creating repository',
  cow_clone: 'Cloning (CoW)',
  luks_mount: 'Mounting LUKS',
  luks_unmount: 'Unmounting LUKS',
  docker_daemon: 'Starting Docker daemon',
  docker_stop: 'Stopping Docker',
  compose_up: 'Starting services',
  compose_down: 'Stopping services',
  service_ready: 'Waiting for services',
  snapshot: 'Creating snapshot',
  transfer: 'Transferring',
  preseed: 'Pre-seeding',
  thaw_resume: 'Resuming containers',
  verify: 'Verifying integrity',
  finalize: 'Finalizing',
  repo_resize: 'Resizing repository',
  repo_expand: 'Expanding repository',
  repo_delete: 'Deleting repository',
  filesystem_resize: 'Resizing filesystem',
  filesystem_expand: 'Expanding filesystem',
};

/** Labels shown when step completes (checkmark). */
const doneLabels: Record<string, string> = {
  checkpoint: 'Checkpoint created',
  repo_create: 'Repository created',
  cow_clone: 'CoW clone complete',
  luks_mount: 'LUKS mounted',
  luks_unmount: 'LUKS unmounted',
  docker_daemon: 'Docker daemon ready',
  docker_stop: 'Docker stopped',
  compose_up: 'Services started',
  compose_down: 'Services stopped',
  service_ready: 'Services ready',
  snapshot: 'Snapshot created',
  transfer: 'Transfer complete',
  preseed: 'Pre-seed complete',
  thaw_resume: 'Containers resumed',
  verify: 'Integrity verified',
  finalize: 'Finalized',
  repo_resize: 'Repository resized',
  repo_expand: 'Repository expanded',
  repo_delete: 'Repository deleted',
  filesystem_resize: 'Filesystem resized',
  filesystem_expand: 'Filesystem expanded',
};

/** Format milliseconds as human-readable duration. */
export function formatStepDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/** Get human label for a step in progress (spinner). */
export function getActiveLabel(name: string): string {
  return activeLabels[name] ?? name;
}

/** Get human label for a completed step (checkmark). */
export function getDoneLabel(name: string): string {
  return doneLabels[name] ?? name;
}
