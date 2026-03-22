/** Format milliseconds as human-readable duration (e.g. "1.6s" or "850ms"). */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}
