/**
 * Entries rsync refuses to carry, read from its output (the sender prints them on stdout).
 *
 * A privileged sync runs with `--no-links --no-D`, so symlinks, devices and specials are dropped and rsync reports each one as `skipping non-regular file "<name>"` while still exiting 0.
 */
const SKIPPED_PATTERN = /(?:^|\r)skipping non-regular file "(.*)"\s*$/gm;

/** The longest unterminated tail kept. A skip line is a path (at most PATH_MAX) and a fixed prefix, so a longer tail is no skip line. */
export const SKIP_SCAN_MAX_LINE = 8192;

/**
 * Keeps only the "skipping non-regular file" lines of a stream that arrives in chunks, so a long sync with progress
 * output holds those lines and one partial line, not every byte rsync printed. A line split across chunks is joined first.
 * A tail longer than SKIP_SCAN_MAX_LINE without a line end is dropped through to its end, so a stream that never
 * emits one cannot grow the carry or be re-copied on every push without bound.
 */
export function createSkipLineScan(): { push(chunk: string): void; text(): string } {
  const kept: string[] = [];
  let carry = '';
  let discarding = false;
  const keep = (line: string): void => {
    if (line.includes('skipping non-regular file')) kept.push(line);
  };
  return {
    push(chunk: string): void {
      let incoming = chunk;
      if (discarding) {
        // The rest of an overlong line is dropped up to its end; a chunk with no line end is dropped whole.
        const end = incoming.search(/[\r\n]/);
        if (end === -1) return;
        incoming = incoming.slice(end);
        discarding = false;
      }
      const lines = `${carry}${incoming}`.split(/[\r\n]/);
      carry = lines.pop() ?? '';
      for (const line of lines) keep(line);
      if (carry.length > SKIP_SCAN_MAX_LINE) {
        carry = '';
        discarding = true;
      }
    },
    text(): string {
      const tail = carry.includes('skipping non-regular file') ? [carry] : [];
      return [...kept, ...tail].join('\n');
    },
  };
}

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

/** Code points that reorder or break a terminal line without drawing: the directional marks (ALM, LRM, RLM), the bidi embeddings, overrides and isolates, and the line and paragraph separators (review 589a76af.1, af20ae8b.1). */
const INVISIBLE_LAYOUT = new Set([
  0x061c, 0x200e, 0x200f, 0x2028, 0x2029, 0x202a, 0x202b, 0x202c, 0x202d, 0x202e, 0x2066, 0x2067,
  0x2068, 0x2069,
]);

/**
 * A name as the terminal may show it. A download's names are the remote machine's, and an escape sequence or a bidi override in
 * one would drive or reorder the terminal (review ef6dbb53.2), so a control character (C0, DEL, C1) is spelled as a backslash,
 * `x` and two hex digits (ESC shows as \x1b), a layout code point as a backslash, `u` and four (\u202e), and a literal
 * backslash is doubled so an escaped byte and the same text typed in a name never look alike (review 589a76af.2).
 */
export function displayName(name: string): string {
  let out = '';
  for (const ch of name) out += displayChar(ch);
  return out;
}

/** One character as displayName shows it. */
function displayChar(ch: string): string {
  if (ch === '\\') return '\\\\';
  const code = ch.codePointAt(0) ?? 0;
  if (code < 0x20 || (code >= 0x7f && code <= 0x9f))
    return `\\x${code.toString(16).padStart(2, '0')}`;
  if (INVISIBLE_LAYOUT.has(code)) return `\\u${code.toString(16).padStart(4, '0')}`;
  return ch;
}

/** The first names for display plus how many were left out. */
export function summarizeSkipped(names: string[]): { shown: string[]; more: number } {
  return {
    shown: names.slice(0, SKIPPED_NAMES_SHOWN).map(displayName),
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

/** Write the skipped-entries warning (stderr in the CLI; the exit code is untouched), or nothing when nothing was skipped. */
export function warnSkippedEntries(
  names: string[],
  translate: Translate,
  write: (text: string) => void
): void {
  const warning = formatSkippedWarning(names, translate);
  if (warning !== undefined) write(`${warning}\n`);
}
