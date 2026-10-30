/**
 * Render order for the numbered sections of the legal pages.
 *
 * The legal pages read `sections` and `subsections` from the translation
 * files, and each locale stores those keys in its own order (the de and ja
 * privacy policy kept them as "10.", "9.", "5.", ...). Key order is therefore
 * not reading order: the number at the start of each title is. Keys whose
 * title carries no leading number keep their relative order after the
 * numbered ones.
 */

/** The leading dotted number of a title ("2.4 Cookies" -> [2, 4]), or null. */
export function titleNumber(title: unknown): number[] | null {
  if (typeof title !== 'string') return null;
  const m = /^\s*(\d+(?:\.\d+)*)\.?(?:\s|$)/.exec(title);
  return m ? m[1].split('.').map(Number) : null;
}

function compareNumbers(a: number[], b: number[]): number {
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const d = (a[i] ?? -1) - (b[i] ?? -1);
    if (d !== 0) return d;
  }
  return 0;
}

/** The keys of `entries` in the order their titles are numbered. */
export function orderedKeys(entries: Record<string, { title?: unknown }>): string[] {
  const keys = Object.keys(entries);
  return keys
    .map((key, index) => ({ key, index, num: titleNumber(entries[key]?.title) }))
    .sort((x, y) => {
      if (x.num && y.num) return compareNumbers(x.num, y.num) || x.index - y.index;
      if (x.num) return -1;
      if (y.num) return 1;
      return x.index - y.index;
    })
    .map((e) => e.key);
}
