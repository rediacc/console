import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { buildOpsSSHArgs, renetStagingKeyPath, vmSSHEndpoint } from '../ssh.js';

const BASE = [
  '-o',
  'StrictHostKeyChecking=no',
  '-o',
  'UserKnownHostsFile=/dev/null',
  '-o',
  'LogLevel=ERROR',
];

// O8: on Windows/Hyper-V `rdc ops ssh --vm-id 11` passed "rdc@127.0.0.1:22211" and ssh failed with
// "Could not resolve hostname 127.0.0.1:22211".
describe('ops ssh argv', () => {
  it('passes a forwarded port with -p and the bare host', () => {
    expect(buildOpsSSHArgs({ vm: { ip: '127.0.0.1', ssh_port: 22211 }, user: 'rdc' })).toEqual([
      ...BASE,
      '-p',
      '22211',
      'rdc@127.0.0.1',
    ]);
  });

  it('leaves port 22 implicit for a KVM VM', () => {
    expect(
      buildOpsSSHArgs({ vm: { ip: '192.168.111.11' }, user: 'rdc', command: 'hostname' })
    ).toEqual([...BASE, 'rdc@192.168.111.11', '--', 'hostname']);
  });

  it('splits a legacy host:port ip from an older renet', () => {
    const args = buildOpsSSHArgs({ vm: { ip: '127.0.0.1:22211' }, user: 'rdc' });
    expect(args).toEqual([...BASE, '-p', '22211', 'rdc@127.0.0.1']);
    expect(args.join(' ')).not.toContain('localhost');
  });

  it('parses bracketed and bare IPv6', () => {
    expect(vmSSHEndpoint({ ip: '[::1]:22203' })).toEqual({ host: '::1', port: 22203 });
    expect(vmSSHEndpoint({ ip: '[fe80::1]' })).toEqual({ host: 'fe80::1', port: undefined });
    expect(vmSSHEndpoint({ ip: 'fe80::1' })).toEqual({ host: 'fe80::1', port: undefined });
    expect(vmSSHEndpoint({ ip: 'fd00::5', ssh_port: 2222 })).toEqual({
      host: 'fd00::5',
      port: 2222,
    });
  });

  it('prefers ssh_port over a packed port', () => {
    expect(vmSSHEndpoint({ ip: '127.0.0.1:22211', ssh_port: 22212 })).toEqual({
      host: '127.0.0.1',
      port: 22212,
    });
  });

  it('passes the staging key with IdentitiesOnly', () => {
    const key = path.join('/home/u', '.renet', 'staging', '.ssh', 'id_rsa');
    expect(
      buildOpsSSHArgs({ vm: { ip: '127.0.0.1', ssh_port: 22211 }, user: 'rdc', keyPath: key })
    ).toEqual([...BASE, '-p', '22211', '-i', key, '-o', 'IdentitiesOnly=yes', 'rdc@127.0.0.1']);
  });
});

describe('renetStagingKeyPath', () => {
  const tail = path.join('staging', '.ssh', 'id_rsa');

  it('defaults to ~/.renet', () => {
    expect(renetStagingKeyPath({}, '/home/u')).toBe(path.join('/home/u', '.renet', tail));
  });

  it('honours RENET_DATA_DIR first', () => {
    expect(renetStagingKeyPath({ RENET_DATA_DIR: '/d', CI: 'true' }, '/home/u')).toBe(
      path.join('/d', tail)
    );
  });

  it('follows renet under CI', () => {
    expect(renetStagingKeyPath({ CI: 'true', RUNNER_TEMP: '/rt' }, '/home/u')).toBe(
      path.join('/rt', 'renet', tail)
    );
    expect(renetStagingKeyPath({ CI: 'true' }, '/home/u')).toBe(path.join('/tmp/renet', tail));
  });
});
