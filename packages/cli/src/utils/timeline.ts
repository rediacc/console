/**
 * Unified step timeline rendering for CLI commands.
 * Merges CLI-side steps (config, SSH, provision) with renet-side steps
 * (LUKS, Docker, compose) into a single timeline.
 */

/** Labels shown while step is in progress (spinner). */
const activeLabels: Record<string, string> = {
  config: 'Loading config',
  ssh_connect: 'Connecting',
  renet_provision: 'Provisioning renet',
  machine_verify: 'Verifying machine',
  license: 'Activating license',
  key_deploy: 'Deploying repo key',
  identity_refresh: 'Refreshing license identity',
  dns: 'Ensuring DNS records',
  cert_sync: 'Syncing cert cache',
  service_urls: 'Resolving service URLs',
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
  config: 'Config loaded',
  ssh_connect: 'Connected',
  renet_provision: 'Renet provisioned',
  machine_verify: 'Machine verified',
  license: 'License activated',
  key_deploy: 'Repo key deployed',
  identity_refresh: 'License identity refreshed',
  dns: 'DNS records ensured',
  cert_sync: 'Cert cache synced',
  service_urls: 'Service URLs resolved',
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

/** A single rendered timeline step (CLI-side, renet-side, or orchestrated). */
export interface TimelineStep {
  name: string;
  duration_ms: number;
  detail?: string;
}

/**
 * Detail marker rendered for steps that ran concurrently with other phases
 * (e.g. DNS ∥ cert sync ∥ identity refresh during fork --up).
 */
export const PARALLEL_STEP_DETAIL = '∥';

/**
 * Time an orchestrated phase and record it into `steps` (when provided).
 * Steps are recorded in completion order; parallel phases carry the '∥'
 * detail marker. The step is recorded even when `fn` rejects, so failed
 * phases still show up in the timeline with their real duration.
 */
export async function recordTimelineStep<T>(
  steps: TimelineStep[] | undefined,
  name: string,
  fn: () => Promise<T>,
  options?: { parallel?: boolean }
): Promise<T> {
  const start = Date.now();
  try {
    return await fn();
  } finally {
    steps?.push({
      name,
      duration_ms: Date.now() - start,
      ...(options?.parallel ? { detail: PARALLEL_STEP_DETAIL } : {}),
    });
  }
}

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
