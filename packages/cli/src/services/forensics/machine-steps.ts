/**
 * The machine steps of `rdc incident declare` (PLAN-forensics-investigation D4): the forensic fork
 * and the switch to Full capture run as child `rdc` commands, `repo fork <ref> --tag <tag>` and
 * `forensics level <ref> full`, so each step takes the exact path the operator would type, with
 * its orchestration, rollback and job handling, and a failure ends the child rather than this
 * process, which still has the outcome to report to the account record.
 */
import { spawn } from 'node:child_process';
import { stripVTControlCharacters } from 'node:util';
import { getEffectiveConfigName } from '../config/config-name.js';
import { writeStderr } from '../core/request-context.js';

/** One step's outcome; `detail` carries the child's last error line, at most 500 characters. */
export interface StepRun {
  ok: boolean;
  detail?: string;
}

export interface MachineSteps {
  fork(ref: string, tag: string): Promise<StepRun>;
  level(ref: string, level: 'full'): Promise<StepRun>;
}

/** The server keeps a step detail of at most 500 characters. */
const DETAIL_MAX = 500;
const STDERR_KEEP = 8192;
/** Node flags a child must not inherit: a debugger port the parent already holds. */
const PARENT_ONLY_NODE_FLAG = /^--(inspect|debug)/;

/** The rdc binary: the SEA itself, or node with its loader flags and the script it runs. */
function rdcBinary(): { command: string; prefix: string[] } {
  if (!process.argv[1] || process.execPath === process.argv[1]) {
    return { command: process.execPath, prefix: [] };
  }
  const flags = process.execArgv.filter((flag) => !PARENT_ONLY_NODE_FLAG.test(flag));
  return { command: process.execPath, prefix: [...flags, process.argv[1]] };
}

/** The last non-empty line of a child's stderr, the line that names its failure. */
export function failureDetail(stderr: string, code: number): string {
  const last = stripVTControlCharacters(stderr)
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line !== '')
    .at(-1);
  return (last ?? `exit ${code}`).slice(0, DETAIL_MAX);
}

/**
 * Run `rdc <argv>` under this run's config. The child's stdout and stderr both reach this
 * process's stderr as progress, so the parent's stdout stays one document in `--output json`.
 */
function runRdc(argv: string[]): Promise<StepRun> {
  const bin = rdcBinary();
  const args = [...bin.prefix, '--config', getEffectiveConfigName(), ...argv];
  return new Promise((resolve) => {
    const child = spawn(bin.command, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let stderr = '';
    child.stdout.on('data', (chunk: Buffer) => writeStderr(chunk));
    child.stderr.on('data', (chunk: Buffer) => {
      writeStderr(chunk);
      stderr = `${stderr}${chunk.toString('utf-8')}`.slice(-STDERR_KEEP);
    });
    child.on('error', (error) => resolve({ ok: false, detail: failureDetail(error.message, 1) }));
    child.on('close', (code) =>
      resolve(code === 0 ? { ok: true } : { ok: false, detail: failureDetail(stderr, code ?? 1) })
    );
  });
}

export const childMachineSteps: MachineSteps = {
  fork: (ref, tag) => runRdc(['repo', 'fork', ref, '--tag', tag]),
  level: (ref, level) => runRdc(['forensics', 'level', ref, level]),
};
