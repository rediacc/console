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
  /** Absolute epoch ms when the step started (enables the waterfall chart). */
  startedAtMs?: number;
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
      startedAtMs: start,
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

// ---------------------------------------------------------------------------
// End-of-command timing summary: proportional bars + waterfall.
// Pure string builders so they are unit-testable; callers decide whether to
// print (TTY only) and pass the wall-clock duration they displayed as Total.
// ---------------------------------------------------------------------------

const BAR_WIDTH = 24;
const WATERFALL_WIDTH = 44;
const LABEL_WIDTH = 26;
/** Steps below this share of wall time fold into a single "other" row. */
const FOLD_THRESHOLD = 0.01;
/** Unattributed share above this gets a warning marker. */
const UNATTRIBUTED_WARN = 0.05;
/** Runs shorter than this render no chart (nothing worth analyzing). */
const DEFAULT_MIN_WALL_MS = 5000;
/**
 * Steps whose duration is driven by the repository's own containers
 * (Rediaccfile up: image pulls, app init, healthchecks) rather than the
 * Rediacc pipeline. Used for the platform-vs-workload attribution line.
 */
const WORKLOAD_STEP_NAMES = new Set(['compose_up', 'service_ready']);
/** Show the attribution note when service startup exceeds this share. */
const WORKLOAD_NOTE_THRESHOLD = 0.5;

export interface TimingSummaryOptions {
  /** Command start (epoch ms); anchors the waterfall axis. */
  epochMs?: number;
  /** Skip rendering entirely below this wall time (default 5000ms). */
  minWallMs?: number;
}

function padLabel(label: string, width: number): string {
  return label.length > width ? `${label.slice(0, width - 1)}…` : label.padEnd(width);
}

function pct(ms: number, wallMs: number): string {
  return `${Math.round((ms / wallMs) * 100)}%`.padStart(4);
}

/** Total wall time covered by at least one step (interval union). */
function unionCoverageMs(steps: TimelineStep[]): number {
  const spans = steps
    .filter((s) => s.startedAtMs !== undefined)
    .map((s) => [s.startedAtMs as number, (s.startedAtMs as number) + s.duration_ms] as const)
    .sort((a, b) => a[0] - b[0]);
  let covered = 0;
  let end = Number.NEGATIVE_INFINITY;
  for (const [from, to] of spans) {
    if (to <= end) continue;
    covered += to - Math.max(from, end);
    end = to;
  }
  return covered;
}

/** Wall time not covered by any recorded step (offset-less steps count by duration). */
export function unattributedMs(steps: TimelineStep[], wallMs: number): number {
  const offsetless = steps
    .filter((s) => s.startedAtMs === undefined)
    .reduce((sum, s) => sum + s.duration_ms, 0);
  return Math.max(0, wallMs - unionCoverageMs(steps) - offsetless);
}

interface BarRow {
  label: string;
  durationMs: number;
  parallel: boolean;
  warn?: boolean;
}

function rowMark(row: BarRow): string {
  if (row.parallel) return ' ∥';
  if (row.warn) return ' ⚠';
  return '';
}

function buildBarRows(steps: TimelineStep[], wallMs: number): BarRow[] {
  const big: BarRow[] = [];
  const small: TimelineStep[] = [];
  for (const step of steps) {
    if (step.duration_ms / wallMs >= FOLD_THRESHOLD) {
      big.push({
        label: getDoneLabel(step.name),
        durationMs: step.duration_ms,
        parallel: step.detail === PARALLEL_STEP_DETAIL,
      });
    } else {
      small.push(step);
    }
  }
  big.sort((a, b) => b.durationMs - a.durationMs);
  if (small.length > 0) {
    const sum = small.reduce((acc, s) => acc + s.duration_ms, 0);
    big.push({ label: `other (${small.length} steps)`, durationMs: sum, parallel: false });
  }
  const gap = unattributedMs(steps, wallMs);
  if (gap > 0) {
    big.push({
      label: 'unattributed',
      durationMs: gap,
      parallel: false,
      warn: gap / wallMs > UNATTRIBUTED_WARN,
    });
  }
  return big;
}

/** Section A: per-step proportional bars, largest first. */
export function buildTimingBars(steps: TimelineStep[], wallMs: number): string {
  const rows = buildBarRows(steps, wallMs);
  const maxMs = Math.max(...rows.map((r) => r.durationMs), 1);
  const lines = rows.map((row) => {
    const len = Math.max(1, Math.round((row.durationMs / maxMs) * BAR_WIDTH));
    const bar = '█'.repeat(len).padEnd(BAR_WIDTH + 1);
    const mark = rowMark(row);
    const duration = formatStepDuration(row.durationMs).padStart(7);
    return `  ${padLabel(row.label, LABEL_WIDTH)} ${bar}${duration} ${pct(row.durationMs, wallMs)}${mark}`;
  });
  return lines.join('\n');
}

/** Axis line for the waterfall: 0s … mid … wall. */
function waterfallAxis(wallMs: number): string {
  const left = '0s';
  const mid = formatStepDuration(wallMs / 2);
  const right = formatStepDuration(wallMs);
  const head = ' '.repeat(LABEL_WIDTH + 2);
  const half = Math.floor(WATERFALL_WIDTH / 2);
  const ruler = `├${'─'.repeat(Math.max(0, half - 1))}┼${'─'.repeat(Math.max(0, WATERFALL_WIDTH - half - 2))}┤`;
  const labels =
    left +
    mid.padStart(half + Math.floor(mid.length / 2) - left.length + 1) +
    right.padStart(WATERFALL_WIDTH - half - Math.ceil(mid.length / 2) - 1);
  return `${head}${labels}\n${head}${ruler}`;
}

/**
 * Section B: waterfall of steps that recorded a start offset, anchored at
 * epochMs (or the earliest recorded start). Parallel steps use a light bar.
 */
export function buildTimingWaterfall(
  steps: TimelineStep[],
  wallMs: number,
  epochMs?: number
): string | null {
  const timed = steps
    .filter((s) => s.startedAtMs !== undefined)
    .sort((a, b) => (a.startedAtMs as number) - (b.startedAtMs as number));
  if (timed.length < 2) return null;
  const t0 = epochMs ?? timed[0].startedAtMs ?? 0;
  const lines = timed.map((step) => {
    const offset = Math.max(0, (step.startedAtMs as number) - t0);
    const startCol = Math.min(WATERFALL_WIDTH - 1, Math.round((offset / wallMs) * WATERFALL_WIDTH));
    const len = Math.max(1, Math.round((step.duration_ms / wallMs) * WATERFALL_WIDTH));
    const glyph = step.detail === PARALLEL_STEP_DETAIL ? '░' : '▓';
    const bar = ' '.repeat(startCol) + glyph.repeat(Math.min(len, WATERFALL_WIDTH - startCol));
    return `  ${padLabel(getDoneLabel(step.name), LABEL_WIDTH)} ${bar}`;
  });
  return `${waterfallAxis(wallMs)}\n${lines.join('\n')}`;
}

/** Platform-vs-workload split: everything that is not service startup is ours. */
export function workloadSplit(
  steps: TimelineStep[],
  wallMs: number
): { platformMs: number; workloadMs: number } {
  const workloadMs = steps
    .filter((s) => WORKLOAD_STEP_NAMES.has(s.name))
    .reduce((sum, s) => sum + s.duration_ms, 0);
  return { platformMs: Math.max(0, wallMs - workloadMs), workloadMs };
}

/**
 * Attribution footer: separates the Rediacc pipeline from service startup,
 * which is defined by the repository's own Rediaccfile/containers. Factual
 * and neutral — when service startup dominates, an informational note makes
 * clear which part the pipeline controls (and finished quickly).
 */
export function buildAttribution(steps: TimelineStep[], wallMs: number): string | null {
  const { platformMs, workloadMs } = workloadSplit(steps, wallMs);
  if (workloadMs === 0) return null;
  const line =
    `  Rediacc pipeline ${formatStepDuration(platformMs)} (${Math.round((platformMs / wallMs) * 100)}%)` +
    ` · service startup ${formatStepDuration(workloadMs)} (${Math.round((workloadMs / wallMs) * 100)}%)`;
  if (workloadMs / wallMs < WORKLOAD_NOTE_THRESHOLD) return line;
  const note =
    `  ℹ Service startup is this repository's container boot (images, init,\n` +
    `    healthchecks — defined by its Rediaccfile), so it varies per app.\n` +
    `    The fork pipeline itself completed in ${formatStepDuration(platformMs)}.`;
  return `${line}\n${note}`;
}

/**
 * Combined end-of-run timing summary (bars + waterfall). Returns null when
 * the run was too short to be worth charting or there is nothing to show.
 */
export function buildTimingSummary(
  steps: TimelineStep[],
  wallMs: number,
  options?: TimingSummaryOptions
): string | null {
  if (steps.length === 0 || wallMs < (options?.minWallMs ?? DEFAULT_MIN_WALL_MS)) return null;
  const sections = [buildTimingBars(steps, wallMs)];
  const attribution = buildAttribution(steps, wallMs);
  if (attribution) sections.push('', attribution);
  const waterfall = buildTimingWaterfall(steps, wallMs, options?.epochMs);
  if (waterfall) sections.push('', waterfall);
  return sections.join('\n');
}
