import { displayWidth } from './terminal-cells.js';

/**
 * Structured logs BELOW error level. They are not a correctness failure, they are
 * a "should never have been on camera" failure: the widest lines in the corpus
 * were 227-358 column `level=info` go-executor relays. Kept separate from
 * ERROR_PATTERNS so the two failures read differently in the report.
 */
export const NOISE_PATTERNS = [/\blevel=(info|warning|warn|debug|trace)\b/, /^time="\d{4}-/];

/**
 * Is this line over-width ONLY because of a single URL nothing may break?
 *
 * `rdc vscode connect --browser` prints a 162-column line whose bulk is one URL
 * with an auth token in it. Wrapping a URL makes it uncopyable, which is worse
 * for the viewer than one long line, so the pipeline deliberately does not wrap
 * it. A gate that demands the impossible gets suppressed, so it is exempted
 * here EXPLICITLY rather than by widening the check.
 *
 * Deliberately narrow, and narrower than the first version: the token must be a
 * URL. Exempting any unbreakable token was tried and the gate's OWN selftest
 * caught it - the 150-column control is a single long token, so that version
 * silently stopped detecting the thing the gate exists for. Only URLs carry the
 * copy-paste argument; a long path, hash or joined field has no such defence and
 * still fails.
 */
export function overflowIsOneUnbreakableUrl(line, width) {
  const tokens = line.split(/\s+/).filter(Boolean);
  const urls = tokens.filter((tok) => /^https?:\/\//.test(tok));
  const longest = urls.reduce((a, b) => (b.length > a.length ? b : a), '');
  if (longest.length <= width) return false;
  const withoutIt = line.replace(longest, '').trimEnd();
  return displayWidth(withoutIt) <= width;
}

/**
 * Same exemption for ONE absolute filesystem path in an otherwise-short line.
 * `rdc repo up` prints `docker compose ... -f /mnt/rediacc/mounts/<guid>/
 * .rediacc/compose-tmp/run-<pid>-<rand>/compose-<id>.yml`, and the path lands on
 * a line of its own: a single unbreakable token. Scoped like the URL case: the
 * line must be over-long only because of that token. The token must also look
 * like a real path, every segment at most 64 columns, so a long joined field or
 * hash that merely starts with `/` (the gate's own long-token control) still fails.
 */
export function overflowIsOneUnbreakablePath(line, width) {
  const tokens = line.split(/\s+/).filter(Boolean);
  const paths = tokens.filter(
    (tok) => tok.startsWith('/') && tok.split('/').every((seg) => seg.length <= 64)
  );
  const longest = paths.reduce((a, b) => (b.length > a.length ? b : a), '');
  if (longest.length <= width) return false;
  const withoutIt = line.replace(longest, '').trimEnd();
  return displayWidth(withoutIt) <= width;
}

/** Patterns that indicate a command produced error output. */
export const ERROR_PATTERNS = [
  /^error:\s/i,
  /unknown command/i,
  /command not found/,
  /required option .* not specified/i,
  /too many arguments/i,
  /missing required argument/i,
  /^fatal:/i,
  /panic:/,
  /level=(error|fatal)/,
];

/** On-camera shell hacks that must never appear in a typed command. */
export const MARKER_HACK_PATTERNS = [
  { pattern: /\|\|\s*true/, message: 'typed command carries "|| true"' },
  { pattern: /2>\s*\/dev\/null/, message: 'typed command carries "2>/dev/null"' },
  { pattern: />\s*\/dev\/null/, message: 'typed command suppresses output with >/dev/null' },
  { pattern: /\btimeout\s+[\d.]+/, message: 'typed command is wrapped in "timeout"' },
];
/** Patterns forbidden in on-camera tutorial script commands. */
export const FORBIDDEN_SCRIPT_PATTERNS = [
  {
    pattern: />\s*\/dev\/null/,
    message: 'Output suppressed with >/dev/null',
    suggestion: 'Tutorial commands should show their output',
  },
  {
    pattern: /2>&1\s*\|?\s*>/,
    message: 'Stderr redirected to suppress output',
    suggestion: 'Tutorial commands should show their output',
  },
  {
    pattern: /\|\|\s*true/,
    message: 'Failure masked with "|| true"',
    suggestion: 'Fix the underlying product issue or use run_cmd_expect_fail',
  },
  {
    pattern: /2>\s*\/dev\/null/,
    message: 'Stderr hidden with 2>/dev/null',
    suggestion: 'Fix the noisy output at the source instead of hiding it',
  },
  {
    pattern: /\btimeout\s+[\d.]+/,
    message: 'Command wrapped in "timeout"',
    suggestion: 'Use run_cmd_interrupt for long-running commands',
  },
];
