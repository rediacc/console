import { describe, expect, it } from 'vitest';
import {
  ensureLandlockActive,
  type LandlockBootProbe,
  lsmHasLandlock,
  lsmWithLandlock,
} from '../landlockBoot';

const OL10_LSM = 'lockdown,capability,yama,selinux,bpf,ima,evm';

/** A scripted VM: `lsmAfter` is what the list reads once `systemctl reboot` ran. */
function fakeVm(lsmBefore: string, lsmAfter: string, grubbyCode = 0) {
  const commands: string[] = [];
  let rebooted = false;
  const reply = (stdout: string, code = 0, stderr = '') => ({ stdout, stderr, code });
  const answers: [string, () => ReturnType<typeof reply>][] = [
    ['sys/kernel/security/lsm', () => reply(`${rebooted ? lsmAfter : lsmBefore}\n`)],
    ['boot_id', () => reply(rebooted ? 'boot-2\n' : 'boot-1\n')],
    ['grubby', () => reply('', grubbyCode, grubbyCode === 0 ? '' : 'no grubby')],
    [
      'reboot',
      () => {
        rebooted = true;
        return reply('', 255);
      },
    ],
  ];
  const probe: LandlockBootProbe = {
    executeOnVM: (_ip, command) => {
      commands.push(command);
      return Promise.resolve(
        (answers.find(([needle]) => command.includes(needle))?.[1] ?? (() => reply('')))()
      );
    },
  };
  return { probe, commands };
}

const FAST = { pollMs: 1, rebootTimeoutMs: 1000 };

describe('lsm list helpers', () => {
  it('detects landlock as a whole list entry', () => {
    expect(lsmHasLandlock('lockdown,capability,landlock,yama')).toBe(true);
    expect(lsmHasLandlock(OL10_LSM)).toBe(false);
    expect(lsmHasLandlock('landlockish,yama')).toBe(false);
  });

  it('appends landlock once to the measured OL10 list', () => {
    expect(lsmWithLandlock(OL10_LSM)).toBe(`${OL10_LSM},landlock`);
    expect(lsmWithLandlock(`${OL10_LSM},landlock`)).toBe(`${OL10_LSM},landlock`);
  });
});

describe('ensureLandlockActive', () => {
  it('leaves a VM that already boots with landlock alone: no grubby, no reboot', async () => {
    const { probe, commands } = fakeVm('lockdown,capability,landlock,yama', '');
    await expect(ensureLandlockActive(probe, '10.0.0.1', FAST)).resolves.toBe('active');
    expect(commands.some((c) => c.includes('grubby') || c.includes('reboot'))).toBe(false);
  });

  it('adds landlock to lsm=, reboots once and confirms it on the OL10 list', async () => {
    const { probe, commands } = fakeVm(OL10_LSM, `${OL10_LSM},landlock`);
    await expect(ensureLandlockActive(probe, '10.0.0.1', FAST)).resolves.toBe('rebooted');
    expect(commands.find((c) => c.includes('grubby'))).toContain(`--args=lsm=${OL10_LSM},landlock`);
    expect(commands.filter((c) => c.includes('reboot'))).toHaveLength(1);
  });

  it('fails loudly, naming the VM, when grubby cannot add it', async () => {
    const { probe } = fakeVm(OL10_LSM, OL10_LSM, 127);
    await expect(ensureLandlockActive(probe, '10.0.0.7', FAST)).rejects.toThrow(
      /10\.0\.0\.7.*grubby could not add it/
    );
  });

  it('fails loudly when landlock is still absent after the reboot', async () => {
    const { probe } = fakeVm(OL10_LSM, OL10_LSM);
    await expect(ensureLandlockActive(probe, '10.0.0.7', FAST)).rejects.toThrow(
      /still absent after adding it/
    );
  });
});
