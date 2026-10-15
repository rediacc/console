/**
 * Entries rsync refuses to carry, read from its stderr.
 *
 * A privileged sync runs with `--no-links --no-D`, so symlinks, devices and specials are dropped and rsync reports each one as `skipping non-regular file "<name>"` while still exiting 0.
 */
const SKIPPED_PATTERN = /^skipping non-regular file "(.*)"\s*$/gm;

/** Names shown in the warning before the rest is summarised as a count. */
export const SKIPPED_NAMES_SHOWN = 5;

/** Extract the skipped entry names from the accumulated rsync stderr, in order and without duplicates. */
export function parseSkippedEntries(stderr: string): string[] {
  const names: string[] = [];
  for (const match of stderr.matchAll(SKIPPED_PATTERN)) {
    if (!names.includes(match[1])) names.push(match[1]);
  }
  return names;
}

/** The first names for display plus how many were left out. */
export function summarizeSkipped(names: string[]): { shown: string[]; more: number } {
  return {
    shown: names.slice(0, SKIPPED_NAMES_SHOWN),
    more: Math.max(0, names.length - SKIPPED_NAMES_SHOWN),
  };
}

type Translate = (key: string, params: Record<string, unknown>) => string;

/** The one-line warning for the skipped entries, or undefined when nothing was skipped. */
export function formatSkippedWarning(names: string[], translate: Translate): string | undefined {
  if (names.length === 0) return undefined;
  const { shown, more } = summarizeSkipped(names);
  const list = shown.join(', ');
  const listed =
    more > 0 ? translate('commands.sync.skippedMore', { names: list, count: more }) : list;
  return translate('commands.sync.skippedNonRegular', { count: names.length, names: listed });
}
