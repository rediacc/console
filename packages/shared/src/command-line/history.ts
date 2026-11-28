/**
 * Command history navigation (D1 and D4 of PLAN-console-command-line).
 *
 * Up walks to older entries, Down back toward newer ones, and Down past the
 * newest restores the draft that was in the box when the walk began. The draft
 * also filters the walk: entries that do not start with it are skipped, so a
 * half-typed `rdc repo` walks only the repo lines. An empty draft walks all.
 */
export class HistoryCursor {
  private entries: string[];
  private matches: number[] = [];
  /** Index into `matches` while browsing, else -1. */
  private position = -1;
  private draft = '';

  /** @param entries oldest first, newest last */
  constructor(entries: readonly string[] = []) {
    this.entries = [...entries];
  }

  /** True between the first Up and the Down that restores the draft. */
  get browsing(): boolean {
    return this.position !== -1;
  }

  /** Replace the entries (the run index answered) and drop any walk in progress. */
  setEntries(entries: readonly string[]): void {
    this.entries = [...entries];
    this.reset();
  }

  /** Add the newest entry and drop any walk in progress. Blank lines and an exact repeat of the newest entry are not kept. */
  push(entry: string): void {
    this.reset();
    if (entry.trim() === '' || this.entries.at(-1) === entry) return;
    this.entries.push(entry);
  }

  /** End the walk without restoring: the user edited the box, so its text is the new draft. */
  reset(): void {
    this.position = -1;
    this.matches = [];
    this.draft = '';
  }

  /** The text for Up pressed with `current` in the box: the next older match, or `current` when there is none. */
  up(current: string): string {
    if (this.position === -1) {
      this.draft = current;
      this.matches = this.entries.flatMap((entry, i) => (entry.startsWith(current) ? [i] : []));
      if (this.matches.length === 0) return current;
      this.position = this.matches.length - 1;
    } else if (this.position > 0) {
      this.position--;
    }
    return this.entries[this.matches[this.position]];
  }

  /** The text for Down: the next newer match, then the draft; `current` when no walk is in progress. */
  down(current: string): string {
    if (this.position === -1) return current;
    if (this.position < this.matches.length - 1) {
      this.position++;
      return this.entries[this.matches[this.position]];
    }
    const draft = this.draft;
    this.reset();
    return draft;
  }
}
