import { describe, expect, it } from 'vitest';
import { DEFAULT_RUSTFS_BUCKET } from '../../constants';
import { OpsRustFSManager } from '../renet-functions/OpsRustFSManager';

/** A manager whose VM executor records the commands it is asked to run and answers HTTP 200. */
function recordingManager(): { manager: OpsRustFSManager; commands: string[] } {
  const commands: string[] = [];
  const executor = {
    executeOnVM: (_host: string, command: string) => {
      commands.push(command);
      return Promise.resolve({ stdout: '\n200', stderr: '', code: 0 });
    },
  };
  const manager = new OpsRustFSManager(
    executor as unknown as ConstructorParameters<typeof OpsRustFSManager>[0],
    '10.0.0.1',
    () => Promise.resolve({ stdout: '', stderr: '', code: 0 })
  );
  return { manager, commands };
}

describe('OpsRustFSManager.verifyAccessFromWorker', () => {
  it('lists the configured test bucket when none is named, not a literal "default"', async () => {
    const { manager, commands } = recordingManager();
    const result = await manager.verifyAccessFromWorker(2, () => '10.0.0.3');
    expect(result.success).toBe(true);
    expect(commands).toHaveLength(1);
    expect(commands[0]).toContain(`/${DEFAULT_RUSTFS_BUCKET}?list-type=2`);
    expect(commands[0]).not.toContain('/default?list-type=2');
  });

  it('lists an explicitly named bucket instead', async () => {
    const { manager, commands } = recordingManager();
    await manager.verifyAccessFromWorker(2, () => '10.0.0.3', 'other-bucket');
    expect(commands[0]).toContain('/other-bucket?list-type=2');
  });
});
