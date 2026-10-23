/**
 * The `Ran:` line of a drafted commit message. A real command is recorded verbatim; the driver's internal helper steps (`npm-steps.ts guard|sync <base64 json>`) are recorded by a short label, because their encoded argument runs to kilobytes and says nothing a reader can use.
 */
import path from 'node:path';
import type { CommandRecord } from './txn.js';

const STEP_RE = /\bnpm-steps\.ts\s+(guard|sync)\s+([A-Za-z0-9+/_-]{16,}={0,2})(?=\s|$)/;

/** The directories (relative to `root`) the encoded steps ran in, or none when the payload does not decode. */
function stepDirs(payload: string, root: string): string[] {
  try {
    const steps = JSON.parse(Buffer.from(payload, 'base64').toString('utf8')) as {
      cwd?: unknown;
    }[];
    const dirs = steps
      .map((s) => (typeof s.cwd === 'string' ? path.relative(root, s.cwd) || '.' : ''))
      .filter((d) => d !== '');
    return [...new Set(dirs)];
  } catch {
    return [];
  }
}

/** One `Ran:` line for a recorded command. Pure apart from the decode. */
export function ranLine(c: CommandRecord, root: string = process.cwd()): string {
  const m = STEP_RE.exec(c.cmd);
  const dirs = m ? stepDirs(m[2], root) : [];
  const what = m ? `npm-steps ${m[1]}${dirs.length > 0 ? ` (${dirs.join(', ')})` : ''}` : c.cmd;
  return `Ran: ${what} (in ${c.cwd}) rc=${c.rc}`;
}
