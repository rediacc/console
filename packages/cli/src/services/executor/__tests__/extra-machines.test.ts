import { beforeEach, describe, expect, it, vi } from 'vitest';

const getLocalMachine = vi.hoisted(() => vi.fn());

vi.mock('../../config/config-resources.js', () => ({
  configService: { getLocalMachine },
}));

import { resolveExtraMachines } from '../extra-machines.js';

describe('resolveExtraMachines', () => {
  beforeEach(() => {
    getLocalMachine.mockReset();
    getLocalMachine.mockResolvedValue({ ip: '10.0.0.2', port: 22, user: 'u', datastore: '/mnt/x' });
  });

  it('reads an undiscriminated `to` as a datastore peer machine', async () => {
    const peers = await resolveExtraMachines({ to: 'machine-12' }, 'datastore_attach');
    expect(Object.keys(peers ?? {})).toEqual(['machine-12']);
    expect(getLocalMachine).toHaveBeenCalledWith('machine-12');
  });

  it("carries the peer machine's knownHosts into the extra machine", async () => {
    getLocalMachine.mockResolvedValue({
      ip: '10.0.0.2',
      port: 22,
      user: 'u',
      datastore: '/mnt/x',
      knownHosts: '10.0.0.2 ssh-ed25519 AAAA',
    });

    const peers = await resolveExtraMachines({ to: 'machine-12' }, 'datastore_attach');

    expect(peers?.['machine-12']).toMatchObject({
      ip: '10.0.0.2',
      knownHosts: '10.0.0.2 ssh-ed25519 AAAA',
    });
  });

  it('never reads the directory `to` of backup_restore_path as a machine name', async () => {
    const peers = await resolveExtraMachines(
      { lineage: 'l', at: 's', path: 'a.bin', to: '/tmp/restore-here' },
      'backup_restore_path'
    );
    expect(peers).toBeUndefined();
    expect(getLocalMachine).not.toHaveBeenCalled();
  });

  it('control: the same params without the function name would have resolved a machine', async () => {
    await resolveExtraMachines({ to: '/tmp/restore-here' });
    expect(getLocalMachine).toHaveBeenCalledWith('/tmp/restore-here');
  });
});
