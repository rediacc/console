/**
 * Marker regions for generated documentation.
 *
 * THE IDIOM IS BORROWED, DELIBERATELY. scripts/gate-bind.ts already owns regions inside
 * .github/workflows/ci-quality.yml with a `# >>> gate-bind (generated)` / `# <<< gate-bind`
 * pair, and the two properties that make it survive a shared tree are copied here verbatim:
 *
 *   1. A generator owns the text BETWEEN markers and nothing else. Hand-written prose above,
 *      below, or between regions is never touched, so a generator and an author can share a
 *      file without fighting.
 *   2. The prose INSIDE the opening marker is preserved. gate-bind's comment on that says it
 *      best: a generator that ate its own explanation every run would train people to stop
 *      reading it.
 *
 * WHAT IS DIFFERENT. gate-bind knows the three lanes it owns. This module knows nothing: it
 * DISCOVERS its targets by scanning tracked markdown for an opening marker naming a provider.
 * A document opts in by carrying the marker; the generator is never edited to add a target.
 * That is the acceptance test in docs/ci-overhaul/08-driver-contract.md section 7 applied to
 * documentation: adding a generated region requires no edit to any dispatcher.
 *
 * WHY A REWRITE AND NOT AN APPEND. The failure this whole phase exists to prevent is a
 * hand-typed number going stale in silence: `.dead-bash-allowlist` said "the 17 gate scripts"
 * against 131, check-ci-parity.ts said "runs 57 gate tests", ci-gates.md said "254 fast gates"
 * against a live 312. A region that is rewritten from the tree cannot drift, and a region that
 * has drifted is a hard red in verify mode rather than a stale sentence nobody re-derives.
 */

/** `<!-- >>> gen-docs: <provider> -->` opens a region owned by that provider. */
export const OPEN_RE = /^<!--\s*>>>\s*gen-docs:\s*([a-z0-9-]+)\s*-->\s*$/;
/** `<!-- <<< gen-docs -->` closes it. */
export const CLOSE_RE = /^<!--\s*<<<\s*gen-docs\s*-->\s*$/;
/** A comment line immediately after the opening marker is PROSE and is preserved. */
const COMMENT_RE = /^<!--/;

export interface Region {
  /** Provider id named by the opening marker. */
  provider: string;
  /** 0-based line index of the opening marker. */
  open: number;
  /** 0-based line index of the closing marker. */
  close: number;
}

export interface RegionError {
  line: number;
  message: string;
}

/**
 * Every region in one file, or the reason the file cannot be rewritten safely.
 *
 * REFUSING IS THE POINT. An unterminated region would make a naive rewriter swallow the rest
 * of the document, and a nested one would make the close ambiguous. Both are reported by line
 * and nothing is written, on the same reasoning as gate-bind's `dropped` list: a destructive
 * rewrite that does not say what it is about to destroy is how a shared file loses content
 * silently.
 */
export function findRegions(text: string): { regions: Region[] } | { errors: RegionError[] } {
  const lines = text.split('\n');
  const regions: Region[] = [];
  const errors: RegionError[] = [];
  let open: { provider: string; line: number } | null = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? '';
    const m = OPEN_RE.exec(line);
    if (m) {
      if (open !== null) {
        errors.push({
          line: i + 1,
          message: `region for "${m[1]}" opens while "${open.provider}" (line ${open.line + 1}) is still open`,
        });
        continue;
      }
      open = { provider: m[1] ?? '', line: i };
      continue;
    }
    if (CLOSE_RE.test(line)) {
      if (open === null) {
        errors.push({ line: i + 1, message: 'closing marker with no open region' });
        continue;
      }
      regions.push({ provider: open.provider, open: open.line, close: i });
      open = null;
    }
  }
  if (open !== null) {
    errors.push({
      line: open.line + 1,
      message: `region for "${open.provider}" is never closed`,
    });
  }
  return errors.length > 0 ? { errors } : { regions };
}

/**
 * Rewrite every region from `render`, preserving prose inside and outside the markers.
 *
 * `render` returns null for a provider the caller does not know. An unknown provider is a
 * REFUSAL rather than an empty region, because emptying a region a human is reading is
 * indistinguishable from "there is nothing to say", which is the vacuity shape this repo keeps
 * paying for.
 */
export function rewriteRegions(
  text: string,
  render: (provider: string) => string[] | null
): { text: string; providers: string[] } | { errors: RegionError[] } {
  const found = findRegions(text);
  if ('errors' in found) return found;

  const lines = text.split('\n');
  const out: string[] = [];
  const providers: string[] = [];
  const errors: RegionError[] = [];
  const byOpen = new Map(found.regions.map((r) => [r.open, r]));

  let i = 0;
  while (i < lines.length) {
    const region = byOpen.get(i);
    if (region === undefined) {
      out.push(lines[i] ?? '');
      i += 1;
      continue;
    }
    out.push(lines[i] ?? '');
    i += 1;
    // Keep the marker's own explanatory comment lines. Same rule as gate-bind: the block explains itself to whoever opens the file, so the generator must not eat it.
    while (i < region.close && COMMENT_RE.test(lines[i] ?? '')) {
      out.push(lines[i] ?? '');
      i += 1;
    }
    const body = render(region.provider);
    if (body === null) {
      errors.push({
        line: region.open + 1,
        message: `no provider named "${region.provider}"`,
      });
    } else {
      out.push(...body);
      providers.push(region.provider);
    }
    i = region.close;
    out.push(lines[i] ?? '');
    i += 1;
  }
  return errors.length > 0 ? { errors } : { text: out.join('\n'), providers };
}
