import { describe, expect, it } from 'vitest';
import { sftpConfigForMachine } from '../../services/machine/machine-connection.js';
import type { MachineConfig } from '../../types/index.js';
import { fingerprint } from '../../utils/host-keys.js';
import { buildHostKeyMismatchMessage } from '../sftp/client.js';

const OLD_ED25519 = 'AAAAC3NzaC1lZDI1NTE5AAAAICrdYxwn02/Fqco8Pn6DTkW6dG2yogjIOe4K1bxuw06f';
const NEW_ED25519 = 'AAAAC3NzaC1lZDI1NTE5AAAAIDo5MxnUtG9Ie+slGgDyHWlx7r6VWsV0yF9K5vVzZG6/';
const RSA = 'AAAAB3NzaC1yc2EAAAADAQABAAABgQCkAMTTKw+6MbBy9EdCNhXac6xKxzqeErEQrwPvSfTmN5dpxyqp';

const host = '72.61.137.225';
const build = (knownHosts: string, offeredKey = NEW_ED25519) =>
  buildHostKeyMismatchMessage({ machineName: 'hostinger', host, knownHosts, offeredKey });

describe('buildHostKeyMismatchMessage', () => {
  it('names the machine and host', () => {
    const msg = build(`${host} ssh-ed25519 ${OLD_ED25519}`);
    expect(msg).toContain('hostinger');
    expect(msg).toContain(host);
  });

  it('shows both the pinned and the offered fingerprint', () => {
    const msg = build(`${host} ssh-ed25519 ${OLD_ED25519}`);
    expect(msg).toContain(fingerprint(OLD_ED25519));
    expect(msg).toContain(fingerprint(NEW_ED25519));
  });

  it('names all three causes, including a stale local config', () => {
    // The stale-config cause is the one that actually occurred and is the
    // easiest to overlook; omitting it makes the message actively misleading.
    const msg = build(`${host} ssh-ed25519 ${OLD_ED25519}`).toLowerCase();
    expect(msg).toContain('migrated');
    expect(msg).toContain('stale');
    expect(msg).toContain('man-in-the-middle');
  });

  it('states the remedy conditionally rather than as an instruction', () => {
    // Guard against regressing to a "tip: just run scan-keys" hint, which trains the reflex that defeats the point of pinning.
    const msg = build(`${host} ssh-ed25519 ${OLD_ED25519}`);
    expect(msg).toContain('If the change is expected');
    expect(msg).toContain('rdc machine scan-keys hostinger');
    expect(msg).toMatch(/confirm the fingerprint out\s*\n?of band/i);
  });

  it('never offers the IP as the scan-keys argument when the machine name is unknown', () => {
    const msg = buildHostKeyMismatchMessage({
      host,
      knownHosts: `${host} ssh-ed25519 ${OLD_ED25519}`,
      offeredKey: NEW_ED25519,
    });
    expect(msg).toContain('rdc machine scan-keys <machine-name>');
    expect(msg).not.toContain(`scan-keys ${host}`);
  });

  it('treats an empty machine name as unknown in the title and the remedy', () => {
    const msg = buildHostKeyMismatchMessage({
      machineName: '',
      host,
      knownHosts: `${host} ssh-ed25519 ${OLD_ED25519}`,
      offeredKey: NEW_ED25519,
    });
    expect(msg).toContain('rdc machine scan-keys <machine-name>');
    expect(msg).toContain(`Host key mismatch for ${host}`);
  });

  it('carries the machine name from a machine config into the SFTP config', () => {
    const cfg = sftpConfigForMachine({ ip: host, user: 'u' } as MachineConfig, 'key', 'hostinger');
    expect(cfg.machineName).toBe('hostinger');
  });

  it('compares against the pin of the same algorithm only', () => {
    const msg = build(`${host} ssh-ed25519 ${OLD_ED25519}\n${host} ssh-rsa ${RSA}`);
    expect(msg).toContain(fingerprint(OLD_ED25519));
    // The rsa pin is irrelevant to an ed25519 mismatch and would be noise.
    expect(msg).not.toContain(fingerprint(RSA));
  });

  it('falls back to listing all pins when the offered blob is undecodable', () => {
    const msg = build(`${host} ssh-rsa ${RSA}`, 'not-valid-base64!!');
    expect(msg).toContain(fingerprint(RSA));
    expect(msg).toContain('(unknown algorithm)');
  });

  it('handles having no pin recorded at all', () => {
    const msg = build('');
    expect(msg).toContain('(none recorded)');
    expect(msg).toContain(fingerprint(NEW_ED25519));
  });

  it('labels the offered key with its algorithm', () => {
    expect(build(`${host} ssh-ed25519 ${OLD_ED25519}`)).toContain('ssh-ed25519');
  });
});
