/**
 * Whether a console run is a preview of its command, decided the same way by
 * the account server (which enforces step-up) and the web dialog (which skips
 * the confirmation for a preview). A preview is not an action (ruling C11).
 */

/** The slice of a contract command this decision reads. */
interface PreviewCapable {
  preview?: { flag: string; polarity: 'opt-in' | 'default' };
}

/**
 * A run is a preview only when it cannot act, so every doubtful value reads as an action:
 * - polarity `opt-in` (`--dry-run`): a preview only when the flag is exactly `true`; any other value never excuses a run.
 * - polarity `default` (previews unless `--apply`): a preview only when the act flag is absent or exactly `false`; any
 *   other value (`'true'`, `1`, `'yes'`) may reach the executor as an apply, so it counts as acting and keeps step-up.
 */
export function isPreviewRun(entry: PreviewCapable, params: Record<string, unknown>): boolean {
  const preview = entry.preview;
  if (!preview) return false;
  const value = params[preview.flag];
  if (preview.polarity === 'opt-in') return value === true;
  return value === undefined || value === false;
}
