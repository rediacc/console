/**
 * Parsers for what the backup-storage verbs print.
 *
 * Split out of backup-storage.ts, which is a Commander registration file: these
 * are pure functions over captured stdout with no CLI, network, or config
 * dependency, which is what makes them directly testable. They live beside the
 * command rather than under services/ for the same reason
 * datastore-prune-parser.ts does -- the parsing IS the command's contract with
 * renet's output, and it belongs next to the caller that owns that contract.
 */

/** The verdict `renet backup verify` prints, when it can be recovered. */
export interface VerifyVerdict {
  status: string;
  level?: string;
  checkedCells?: number;
}

/**
 * Recover the verify verdict from the verb's captured stdout.
 *
 * renet emits one JSON object, but it can arrive with relay prefixes or log
 * lines around it, so this scans for the LAST line that parses and carries a
 * `status` rather than assuming the whole buffer is JSON. Returns undefined
 * rather than throwing: a verdict we cannot parse must not turn a successful
 * verification into a crash, and the caller falls back to the exit code.
 */
export function parseVerifyVerdict(stdout: string | undefined): VerifyVerdict | undefined {
  if (!stdout) return undefined;
  let found: VerifyVerdict | undefined;
  for (const line of stdout.split('\n')) {
    const start = line.indexOf('{');
    if (start === -1) continue;
    try {
      const parsed: unknown = JSON.parse(line.slice(start));
      if (parsed && typeof parsed === 'object' && 'status' in parsed) {
        found = parsed as VerifyVerdict;
      }
    } catch {
      // Not JSON, or a partial line. Keep scanning; a stray log line must not
      // hide a verdict that appears later in the buffer.
    }
  }
  return found;
}

/** One filesystem object as `renet backup browse` reports it. */
interface BrowseEntry {
  path: string;
  type: string;
  size: number;
  modTime: string;
}

/** The listing plus what it is a listing OF. */
export interface BrowseListing {
  source: string;
  entries: BrowseEntry[];
  truncated: boolean;
  totalSize: number;
}

/**
 * Candidate JSON payloads on one line of captured output.
 *
 * TWO shapes, and the second is the one that cost this wave a CI round: a
 * verb's stdout can arrive WRAPPED inside a log line as
 * `msg="[backup_browse] {...}"` with the quotes escaped, in which case scanning
 * for a bare `{` finds the brace but JSON.parse chokes on the escapes.
 */
function browseJsonCandidates(line: string): string[] {
  const out: string[] = [];
  const wrapped = /msg="\[[a-z_]+\] (\{.*?\})"\s*$/.exec(line);
  if (wrapped) {
    // JSON.parse the quoted span rather than replaceAll('\\"', '"').
    //
    // The naive unescape handled ONLY escaped quotes, so a filename containing
    // a newline or a backslash -- both legal on Linux -- came back as invalid
    // JSON. It failed safe (parseBrowseResult returns undefined, browse names
    // the error), but "fails safe" here means REFUSING a repository that is
    // perfectly fine, and the operator would have no way to tell that from a
    // real fault. Wrapping the span in quotes and parsing it as a JSON string
    // literal applies the same unescaping rules the writer used, for every
    // escape rather than one of them.
    try {
      out.push(JSON.parse(`"${wrapped[1]}"`) as string);
    } catch {
      // Not a decodable string literal: fall through to the bare-JSON attempt
      // below rather than discarding the line.
    }
  }
  const start = line.indexOf('{');
  if (start !== -1) out.push(line.slice(start));

  return out;
}

/** True when a parsed value is shaped like a browse listing and not another verb's record. */
function isBrowseListing(parsed: unknown): parsed is BrowseListing {
  return (
    parsed !== null &&
    typeof parsed === 'object' &&
    'entries' in parsed &&
    'source' in parsed &&
    Array.isArray((parsed as BrowseListing).entries)
  );
}

/**
 * Recover the listing from the verb's captured stdout.
 *
 * Handles both shapes browseJsonCandidates produces -- the bare object and the
 * one wrapped inside an escaped log line -- and narrows with isBrowseListing so
 * another verb's JSON record on the same buffer cannot be mistaken for a
 * listing.
 *
 * Returns undefined rather than throwing, so an unparseable buffer surfaces as
 * a named error instead of a stack trace.
 */
export function parseBrowseResult(stdout: string | undefined): BrowseListing | undefined {
  if (!stdout) return undefined;
  let found: BrowseListing | undefined;
  for (const raw of stdout.split('\n')) {
    for (const candidate of browseJsonCandidates(raw.trim())) {
      try {
        const parsed: unknown = JSON.parse(candidate);
        if (isBrowseListing(parsed)) found = parsed;
      } catch {
        // Not JSON, or a partial line. Keep scanning: a stray log line must not
        // hide a listing that appears later in the buffer.
      }
    }
  }

  return found;
}
