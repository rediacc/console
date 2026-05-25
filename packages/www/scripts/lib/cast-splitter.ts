import { readFileSync, writeFileSync } from 'node:fs';

export interface CastHeader {
  version: 2;
  width: number;
  height: number;
  timestamp?: number;
  env?: Record<string, string>;
}

export type CastEvent = [time: number, kind: string, data: string];

export interface ParsedCast {
  header: CastHeader;
  events: CastEvent[];
}

export function parseCast(path: string): ParsedCast {
  const lines = readFileSync(path, 'utf8')
    .split('\n')
    .filter((l) => l.length > 0);
  const header = JSON.parse(lines[0]) as CastHeader;
  if (header.version !== 2) {
    throw new Error(`Unsupported cast version ${header.version} at ${path}`);
  }
  const events: CastEvent[] = lines.slice(1).map((l) => JSON.parse(l) as CastEvent);
  return { header, events };
}

export function markerTimestamps(cast: ParsedCast): number[] {
  return cast.events.filter(([, k]) => k === 'm').map(([t]) => t);
}

export interface SegmentSpec {
  startSec: number;
  endSec: number;
}

/**
 * Build sub-casts for the supplied [start, end] windows. Prior "o" events are
 * concatenated and emitted at t=0 so the segment opens with a fully restored
 * terminal state instead of a blank screen.
 */
export function writeSegments(
  cast: ParsedCast,
  segments: SegmentSpec[],
  outDir: string,
  basename: string
): string[] {
  const paths: string[] = [];
  segments.forEach((seg, idx) => {
    const priorOutput = cast.events
      .filter(([t, k]) => k === 'o' && t < seg.startSec)
      .map(([, , d]) => d)
      .join('');
    const out: string[] = [JSON.stringify(cast.header)];
    if (priorOutput.length > 0) {
      out.push(JSON.stringify([0, 'o', priorOutput]));
    }
    for (const [t, k, d] of cast.events) {
      if (k !== 'o') continue;
      if (t < seg.startSec) continue;
      if (t >= seg.endSec) break;
      out.push(JSON.stringify([Number((t - seg.startSec).toFixed(6)), k, d]));
    }
    const file = `${outDir}/${basename}-anim-${String(idx).padStart(2, '0')}.cast`;
    writeFileSync(file, `${out.join('\n')}\n`);
    paths.push(file);
  });
  return paths;
}

/**
 * Re-time the output events of a slice cast so the terminal output streams in at
 * a steady, readable cadence instead of dumping in an instant burst. Some
 * commands (e.g. a deploy log) print dozens of lines within a few milliseconds;
 * replayed at recorded speed that is an unreadable flash. Re-timing only changes
 * WHEN each output chunk is fed to the terminal — the chunks and their order are
 * untouched — so the rendered terminal state is byte-identical, just paced.
 *
 * For each event the virtual clock advances by `max(min(origGap, maxGapSec),
 * lineCount * lineCadenceSec)`: real pauses are preserved but capped (so long
 * idle waits compress) while dense bursts are stretched to `lineCadenceSec` per
 * line. The first event (the restored prior-terminal state) keeps its timestamp.
 * Returns the new total duration (last event time).
 */
export function writeRestreamedSegment(
  srcCast: string,
  outCast: string,
  opts: { lineCadenceSec: number; maxGapSec: number }
): number {
  const { header, events } = parseCast(srcCast);
  const out: string[] = [JSON.stringify(header)];
  let clock = 0;
  let prevOrig = 0;
  let started = false;
  for (const [t, k, d] of events) {
    if (k !== 'o') continue;
    if (!started) {
      out.push(JSON.stringify([Number(t.toFixed(6)), k, d]));
      clock = t;
      prevOrig = t;
      started = true;
      continue;
    }
    const origGap = Math.max(0, t - prevOrig);
    const lineCount = (d.match(/\n/g) || []).length;
    clock += Math.max(Math.min(origGap, opts.maxGapSec), lineCount * opts.lineCadenceSec);
    out.push(JSON.stringify([Number(clock.toFixed(6)), k, d]));
    prevOrig = t;
  }
  writeFileSync(outCast, `${out.join('\n')}\n`);
  return clock;
}

/**
 * Compute anim segments from marker timestamps. Returns N+1 windows where N
 * = number of markers: [0..m0], [m0..m1], ..., [mN-1..end].
 */
export function animWindows(markers: number[], castEndSec: number): SegmentSpec[] {
  const points = [0, ...markers, castEndSec];
  const out: SegmentSpec[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    out.push({ startSec: points[i], endSec: points[i + 1] });
  }
  return out;
}

export function castDurationSec(cast: ParsedCast): number {
  let max = 0;
  for (const [t] of cast.events) {
    if (t > max) max = t;
  }
  return max;
}

/**
 * Count newlines emitted by "o" events within (startSec, endSec). Used as a
 * proxy for "how much terminal output the viewer needs to read" so we can
 * scale the post-command read-pause proportionally.
 */
export function countOutputLines(cast: ParsedCast, startSec: number, endSec: number): number {
  let lines = 0;
  for (const [t, kind, data] of cast.events) {
    if (kind !== 'o') continue;
    if (t < startSec) continue;
    if (t >= endSec) break;
    lines += (data.match(/\r?\n/g) ?? []).length;
  }
  return lines;
}

/**
 * Timestamp of the last output ('o') event strictly before `beforeSec` (within
 * [startSec, beforeSec)). The command's output dump prints within milliseconds
 * of the empty "command done" prompt, so the main-animation cutoff (which sits
 * just before that prompt) can otherwise land BEFORE the output and show an
 * empty screen during the whole narration. Used to extend the cutoff so the
 * output is included in the main animation. Returns null if no such event.
 */
export function lastOutputTime(
  cast: ParsedCast,
  startSec: number,
  beforeSec: number
): number | null {
  let last: number | null = null;
  for (const [t, kind] of cast.events) {
    if (kind !== 'o') continue;
    if (t < startSec) continue;
    if (t >= beforeSec) break;
    last = t;
  }
  return last;
}

/**
 * Count the terminal DISPLAY rows the output in [startSec, endSec) occupies,
 * accounting for line wrapping at `cols` (a long line with no newline still
 * fills multiple rows — e.g. an inline key in a printed config). Output is taken
 * from the last clear-screen onward (run_cmd clears before each command), ANSI
 * escapes are stripped, and each logical line counts ceil(len/cols) rows. Used
 * to decide whether a step's output scrolled off the recorded viewport.
 */
export function countDisplayRows(
  cast: ParsedCast,
  startSec: number,
  endSec: number,
  cols: number
): number {
  const ESC = String.fromCharCode(27);
  const BEL = String.fromCharCode(7);
  let text = '';
  for (const [t, kind, data] of cast.events) {
    if (kind !== 'o') continue;
    if (t < startSec) continue;
    if (t >= endSec) break;
    text += data;
  }
  // Keep only what's on screen after the last clear (run_cmd emits ESC[3J ESC[2J).
  const clearIdx = Math.max(text.lastIndexOf(`${ESC}[2J`), text.lastIndexOf(`${ESC}[3J`));
  if (clearIdx >= 0) text = text.slice(clearIdx);
  // Strip CSI / OSC escape sequences so they don't count toward visible width.
  // Regexes built from String.fromCharCode so no literal control char appears.
  const clean = text
    .replace(new RegExp(`${ESC}\\[[0-9;?]*[a-zA-Z]`, 'g'), '')
    .replace(new RegExp(`${ESC}\\][^${BEL}]*${BEL}`, 'g'), '');
  let rows = 0;
  for (const rawLine of clean.split('\n')) {
    // A carriage return rewrites the line in place; the widest segment wins.
    const widest = rawLine.split('\r').reduce((m, s) => Math.max(m, s.length), 0);
    rows += Math.max(1, Math.ceil(widest / cols));
  }
  return rows;
}

/**
 * Find the last time within (startSec, endSec) where an output event prints
 * a shell prompt (matched by the literal "user@" host marker). The fresh
 * post-eval prompt printed by `run_cmd` is what signals "command done", and
 * the MP4 renderer uses this point to split cast-narrated into pre-prompt
 * playback + post-prompt freeze.
 *
 * Returns null if no prompt found in the window.
 */
export function findLastPromptTime(
  cast: ParsedCast,
  startSec: number,
  endSec: number
): number | null {
  const PROMPT_PATTERN = /user@rediacc/;
  let lastTime: number | null = null;
  for (const [t, kind, data] of cast.events) {
    if (kind !== 'o') continue;
    if (t <= startSec) continue;
    if (t >= endSec) break;
    if (PROMPT_PATTERN.test(data)) {
      lastTime = t;
    }
  }
  return lastTime;
}
