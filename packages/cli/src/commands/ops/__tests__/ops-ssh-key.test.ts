import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const runOpsJSON = vi.fn();
const spawn = vi.fn();

vi.mock('node:child_process', () => ({ spawn: (...args: unknown[]) => spawn(...args) }));
vi.mock('../../../services/executor/ops-executor.js', () => ({
  opsExecutorService: { runOpsJSON: (...args: unknown[]) => runOpsJSON(...args) },
}));

const { registerOpsSSHCommand } = await import('../ssh.js');

// 8d87920a.1: the action handler passes the renet staging key to ssh only when the file exists.
describe('rdc ops ssh staging key', () => {
  let dataDir: string;
  let savedDataDir: string | undefined;

  beforeEach(() => {
    runOpsJSON.mockReset();
    spawn.mockReset();
    runOpsJSON.mockResolvedValue({ vms: [{ id: 11, ip: '192.168.111.11', status: 'running' }] });
    spawn.mockReturnValue({ on: vi.fn() });
    savedDataDir = process.env.RENET_DATA_DIR;
    dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ops-ssh-key-'));
    process.env.RENET_DATA_DIR = dataDir;
  });

  afterEach(() => {
    if (savedDataDir === undefined) delete process.env.RENET_DATA_DIR;
    else process.env.RENET_DATA_DIR = savedDataDir;
    fs.rmSync(dataDir, { recursive: true });
  });

  async function run(): Promise<string[]> {
    const root = new Command();
    root.exitOverride();
    registerOpsSSHCommand(root.command('ops'), root);
    await root.parseAsync(['node', 'rdc', 'ops', 'ssh', '--vm-id', '11']);
    expect(spawn).toHaveBeenCalledTimes(1);
    return (spawn.mock.calls[0] as unknown[])[1] as string[];
  }

  it('passes -i with IdentitiesOnly when the staging key exists', async () => {
    const key = path.join(dataDir, 'staging', '.ssh', 'id_rsa');
    fs.mkdirSync(path.dirname(key), { recursive: true });
    fs.writeFileSync(key, 'k');
    const args = await run();
    expect(args).toEqual(expect.arrayContaining(['-i', key, 'IdentitiesOnly=yes']));
  });

  it('passes no -i when the staging key is absent', async () => {
    const args = await run();
    expect(args).not.toContain('-i');
    expect(args).not.toContain('IdentitiesOnly=yes');
  });
});
