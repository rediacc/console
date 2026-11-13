import { afterEach, describe, expect, it, vi } from 'vitest';
import type { OpsCommandRunner } from './OpsCommandRunner';
import type { OpsVMExecutor } from './OpsVMExecutor';
import { OpsVMLifecycle } from './OpsVMLifecycle';

// renet's disk preflight refuses before touching any VM. Its line names /var/lib/libvirt/images, which used to match the 'libvirt' infrastructure pattern and be reported as "KVM/libvirt not available ... Run: sudo renet ops host setup", hiding a capacity problem behind a setup hint.

const DISK_REFUSAL =
  'cluster startup failed: Refusing to provision: VM disk directory /var/lib/libvirt/images/rediacc-vms has 79.9 GiB free but this run needs about 86.2 GiB (short by 6.3 GiB).';

const build = (stderr: string) => {
  const commandRunner = {
    runWithEnv: vi.fn().mockResolvedValue({ stdout: '', stderr, code: 1 }),
  };
  const vmExecutor = {
    waitForVM: vi.fn().mockResolvedValue(true),
    executeOnVM: vi.fn().mockResolvedValue({ code: 0, stdout: '', stderr: '' }),
  };
  const lifecycle = new OpsVMLifecycle(
    commandRunner as unknown as OpsCommandRunner,
    vmExecutor as unknown as OpsVMExecutor,
    () => ['192.168.111.11'],
    () => ['192.168.111.11'],
    () => []
  );
  return { lifecycle, vmExecutor };
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe('resetVMs reports a disk-space refusal verbatim', () => {
  it('fails the reset with renet text and no setup hint, without probing the old fleet', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const { lifecycle, vmExecutor } = build(DISK_REFUSAL);

    const { success } = await lifecycle.resetVMs();

    const printed = error.mock.calls.flat().join('\n');
    expect(success).toBe(false);
    expect(printed).toContain('Refusing to provision');
    expect(printed).toContain('short by 6.3 GiB');
    expect(printed).not.toContain('KVM/libvirt not available');
    expect(printed).not.toContain('sudo renet ops host setup');
    expect(vmExecutor.waitForVM).not.toHaveBeenCalled();
  });

  it('reports the tmpfs refusal the same way, the other line that opens with the phrase', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const { lifecycle, vmExecutor } = build(
      'cluster startup failed: Refusing to provision: VM disk directory /dev/shm/vms is on a RAM-backed filesystem (tmpfs/ramfs); disks there fill memory and pause the VMs.'
    );

    const { success } = await lifecycle.resetVMs();

    const printed = error.mock.calls.flat().join('\n');
    expect(success).toBe(false);
    expect(printed).toContain('RAM-backed filesystem');
    expect(printed).not.toContain('sudo renet ops host setup');
    expect(vmExecutor.waitForVM).not.toHaveBeenCalled();
  });

  it('CONTROL: a genuine libvirt failure still gets the infrastructure hint', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const { lifecycle } = build('failed to connect socket to libvirt-sock');

    const { success } = await lifecycle.resetVMs();

    const printed = error.mock.calls.flat().join('\n');
    expect(success).toBe(false);
    expect(printed).toContain('KVM/libvirt not available');
    expect(printed).toContain('sudo renet ops host setup');
  });
});
