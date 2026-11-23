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
 * The preview flag given for polarity `opt-in` (`--dry-run`), or absent for
 * `default` (the command previews unless `--apply`). Only a boolean `true`
 * counts as the flag being given: any other value reaches the executor as a
 * plain value, so it never excuses a run.
 */
export function isPreviewRun(entry: PreviewCapable, params: Record<string, unknown>): boolean {
  const preview = entry.preview;
  if (!preview) return false;
  const given = params[preview.flag] === true;
  return preview.polarity === 'opt-in' ? given : !given;
}
