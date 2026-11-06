import { describe, expect, it } from 'vitest';
import { collectVmEvidence, isSshLoss, type VmEvidenceRunner } from '../vmEvidence';

interface Fake extends VmEvidenceRunner {
  local: string[];
  worker: string[];
  slept: number[];
}

const fake = (workerUpAfter: number): Fake => {
  const f: Fake = {
    local: [],
    worker: [],
    slept: [],
    runLocal: (cmd) => {
      f.local.push(cmd);
      return Promise.resolve(`local<${cmd}>`);
    },
    runWorker: (cmd) => {
      f.worker.push(cmd);
      if (f.worker.length <= workerUpAfter) {
        return Promise.resolve({ code: 255, output: 'ssh: connect refused' });
      }
      return Promise.resolve({ code: 0, output: `worker<${cmd}>` });
    },
    sleep: (ms) => Promise.resolve(void f.slept.push(ms)),
    now: () => f.slept.reduce((a, b) => a + b, 0),
  };
  return f;
};

describe('isSshLoss', () => {
  it('recognises exit 255 and the ssh failure texts, not an ordinary failure', () => {
    expect(isSshLoss({ code: 255, output: '' })).toBe(true);
    expect(isSshLoss({ code: 1, output: 'Connection timed out during banner exchange' })).toBe(
      true
    );
    expect(isSshLoss({ code: 1, output: 'dd: write error: No space left on device' })).toBe(false);
    expect(isSshLoss({ code: 0, output: '' })).toBe(false);
  });
});

describe('collectVmEvidence', () => {
  it('records the runner side commands', async () => {
    const f = fake(0);
    const evidence = await collectVmEvidence(f, { diskDir: '/mnt/rediacc-vm' });
    const joined = f.local.join('\n');
    for (const needle of ['uptime', 'free -m', 'dmesg | tail -200', 'qemu', 'df ']) {
      expect(joined).toContain(needle);
    }
    expect(joined).toContain('/mnt/rediacc-vm');
    expect(evidence).toContain('local<uptime>');
  });

  it('retries the worker until it answers, then records uptime and dmesg', async () => {
    const f = fake(3);
    const evidence = await collectVmEvidence(f, { diskDir: '/d', retryIntervalMs: 10_000 });
    expect(f.slept.length).toBe(3);
    expect(f.worker.at(-1)).toBe('uptime; dmesg | tail -200');
    expect(evidence).toContain('worker<uptime; dmesg | tail -200>');
  });

  it('gives up after 120 s and says the worker never answered', async () => {
    const f = fake(Number.POSITIVE_INFINITY);
    const evidence = await collectVmEvidence(f, { diskDir: '/d', retryIntervalMs: 10_000 });
    expect(f.slept.reduce((a, b) => a + b, 0)).toBeLessThanOrEqual(120_000);
    expect(f.slept.length).toBeGreaterThanOrEqual(11);
    expect(evidence).toContain('did not answer SSH within 120 s');
  });
});
