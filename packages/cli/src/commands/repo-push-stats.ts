/**
 * Transfer statistics for `repo push` / `repo migrate`.
 *
 * `renet backup push` emits a single machine-readable line on stdout:
 *   {"push_result": {..., "transferMode": "delta", "transferredBytes": N, ...}}
 * The line rides the subprocess -> bridge -> CLI stdout relay, so it arrives
 * interleaved with log lines and carries a `[backup_push] `-style prefix.
 */

import { t } from '../i18n/index.js';
import type { LocalExecuteResult } from '../services/local-executor.js';
import { outputService } from '../services/output.js';
import { formatBytes, formatDuration } from '../utils/format.js';

/** Stats emitted by `renet backup push` as the `push_result` stdout line. */
export interface PushResultStats {
  repository: string;
  destination: string;
  destinationType: string;
  /** Final image size on the destination (sparse-inflated; NOT bytes shipped). */
  size: number;
  transferredAt: string;
  method: string;
  duration: string;
  /** What actually happened: "delta" only when the delta path completed. */
  transferMode: 'delta' | 'full';
  /** Bytes that crossed the wire; -1 = unknown (stats never fail a push). */
  transferredBytes: number;
  /** Base GUID the delta was computed against (delta transfers only). */
  deltaBase?: string;
  /** Duration of the transfer phase in milliseconds. */
  transferMs: number;
}

/**
 * Extract the `push_result` stats from captured renet stdout. Lines may carry
 * bridge `[function] ` prefixes and sit between unrelated log/JSON lines
 * (mirrors the steps extractor in local-executor and repo-diff's extractJson).
 */
export function extractPushResult(stdout: string | undefined): PushResultStats | undefined {
  if (!stdout) return undefined;
  for (const rawLine of stdout.split('\n')) {
    const line = rawLine.trim();
    const jsonStart = line.indexOf('{');
    if (jsonStart < 0) continue;
    try {
      const parsed = JSON.parse(line.slice(jsonStart)) as { push_result?: PushResultStats };
      const stats = parsed.push_result;
      if (
        stats &&
        typeof stats === 'object' &&
        typeof stats.transferMode === 'string' &&
        typeof stats.transferredBytes === 'number'
      ) {
        return stats;
      }
    } catch {
      // Not valid JSON (log line, partial output) — keep scanning.
    }
  }
  return undefined;
}

/** First GUID group ("3f2c1a9b") — enough to identify a base, short enough to read. */
function shortBase(guid: string | undefined): string {
  if (!guid) return '';
  return guid.length > 8 ? `${guid.slice(0, 8)}…` : guid;
}

/**
 * Print the push completion line with real transfer numbers, e.g.
 *   delta: Pushed "my-app" to machine-12 — 49.7 MB transferred in 6.2s (delta vs base 3f2c1a9b…, image 1.0 GB)
 *   full:  Pushed "my-app" to machine-12 — 1.0 GB transferred in 41s (full)
 * Unknown byte counts (-1) omit the byte figure.
 */
export function renderPushStats(repo: string, machine: string, stats: PushResultStats): void {
  const duration = formatDuration(stats.transferMs);
  if (stats.transferredBytes < 0) {
    outputService.success(t('commands.repo.push.statsNoBytes', { repo, machine, duration }));
    return;
  }
  const transferred = formatBytes(stats.transferredBytes);
  if (stats.transferMode === 'delta') {
    outputService.success(
      t('commands.repo.push.statsDelta', {
        repo,
        machine,
        transferred,
        duration,
        base: shortBase(stats.deltaBase),
        image: formatBytes(stats.size),
      })
    );
  } else {
    outputService.success(
      t('commands.repo.push.statsFull', { repo, machine, transferred, duration })
    );
  }
}

/**
 * Parse + print real transfer stats after a successful `repo push` (local
 * adapter only; the cloud path has no captured stdout and keeps its output
 * as-is). The human line is machine-target only; --json prints for both.
 */
export function reportPushStats(
  repo: string,
  targetName: string,
  resolvedType: 'machine' | 'storage',
  local: LocalExecuteResult | undefined,
  asJson: boolean
): void {
  const stats = extractPushResult(local?.stdout);
  if (!stats) return;
  if (asJson) {
    outputService.print(stats, 'json');
  } else if (resolvedType === 'machine') {
    renderPushStats(repo, targetName, stats);
  }
}
