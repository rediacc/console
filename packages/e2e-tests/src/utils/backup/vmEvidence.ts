/**
 * Evidence for a worker VM that stopped answering SSH mid-run (suite 31). The runner side is recorded first, because a dead qemu or a full disk on the runner explains the loss; then SSH to the worker is retried and, once it answers, its own `uptime` and kernel log are recorded.
 *
 * Pure over an injected runner so the unit test drives it with a fake.
 */

export interface RunResult {
  code: number;
  output: string;
}

export interface VmEvidenceRunner {
  /** Run a shell command on the CI runner (the host of the VMs). */
  runLocal: (command: string) => Promise<string>;
  /** Run a command on the worker over the bridge. */
  runWorker: (command: string) => Promise<RunResult>;
  sleep: (ms: number) => Promise<void>;
  /** A monotonic clock in ms. */
  now: () => number;
}

export interface VmEvidenceOptions {
  /** REDIACC_VM_DISK_DIR, where the VM disks live. */
  diskDir: string;
  /** How long to keep retrying the worker, default 120 s. */
  retryWindowMs?: number;
  retryIntervalMs?: number;
}

const RETRY_WINDOW_MS = 120_000;
const RETRY_INTERVAL_MS = 5_000;

const SSH_LOSS_TEXT =
  /ssh: connect|connection (?:closed|refused|reset|timed out)|broken pipe|kex_exchange_identification|no route to host/i;

/** True when a worker command failed because the SSH channel was lost, not because the command failed. */
export const isSshLoss = (r: RunResult): boolean => r.code === 255 || SSH_LOSS_TEXT.test(r.output);

const shellQuote = (s: string): string => `'${s.replace(/'/g, `'\\''`)}'`;

/** The runner-side commands, in order. */
const runnerEvidenceCommands = (diskDir: string): string[] => [
  'uptime',
  'free -m',
  'dmesg | tail -200',
  'ps -eo pid,stat,etime,pcpu,pmem,args | grep -i qemu | grep -v grep',
  `df -h ${shellQuote(diskDir)}`,
];

const errText = (e: unknown): string => (e instanceof Error ? e.message : String(e));

const runnerSide = async (runner: VmEvidenceRunner, diskDir: string): Promise<string[]> => {
  const parts: string[] = [];
  for (const cmd of runnerEvidenceCommands(diskDir)) {
    const out = await runner.runLocal(cmd).catch((e: unknown) => `(failed: ${errText(e)})`);
    parts.push(`--- runner: ${cmd}\n${out.trimEnd()}`);
  }
  return parts;
};

const WORKER_PROBE = 'uptime; dmesg | tail -200';

/** Retry the worker until it answers or the window closes; the evidence line either way. */
const workerSide = async (
  runner: VmEvidenceRunner,
  windowMs: number,
  intervalMs: number
): Promise<string> => {
  const start = runner.now();
  for (;;) {
    const r = await runner.runWorker(WORKER_PROBE);
    if (r.code === 0) return `--- worker: ${WORKER_PROBE}\n${r.output.trimEnd()}`;
    if (runner.now() - start + intervalMs > windowMs) break;
    await runner.sleep(intervalMs);
  }
  return `--- worker: did not answer SSH within ${Math.round(windowMs / 1000)} s`;
};

/** Collect the evidence and return it as one text block. */
export const collectVmEvidence = async (
  runner: VmEvidenceRunner,
  opts: VmEvidenceOptions
): Promise<string> => {
  const parts = await runnerSide(runner, opts.diskDir);
  parts.push(
    await workerSide(
      runner,
      opts.retryWindowMs ?? RETRY_WINDOW_MS,
      opts.retryIntervalMs ?? RETRY_INTERVAL_MS
    )
  );
  return parts.join('\n');
};
