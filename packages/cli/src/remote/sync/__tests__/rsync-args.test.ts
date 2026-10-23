import { describe, expect, it } from 'vitest';
import { buildRsyncArgs } from '../rsync.js';

describe('buildRsyncArgs', () => {
  it('sends the privileged repo sync the renet sandbox-gateway admits', () => {
    const args = buildRsyncArgs({ isUpload: true }, 'ssh', 'rediacc');
    expect(args).toEqual([
      '-av',
      '--verbose',
      '--inplace',
      '--no-whole-file',
      '--progress',
      '-e',
      'ssh',
      '--rsync-path',
      'sudo rsync',
      '--chown',
      'rediacc:rediacc',
      '--numeric-ids',
      '--no-links',
      '--no-D',
      '--partial',
    ]);
  });

  it('refuses links and devices on a privileged download too', () => {
    const args = buildRsyncArgs({}, 'ssh', 'rediacc');
    expect(args).toContain('--no-links');
    expect(args).toContain('--no-D');
    expect(args).not.toContain('--chown');
  });

  it('leaves an unprivileged transfer alone', () => {
    const args = buildRsyncArgs({ remoteRsyncPath: '/opt/rsync' }, 'ssh');
    expect(args).toContain('/opt/rsync');
    expect(args).not.toContain('--no-D');
  });

  it('builds the skeleton upload as the plain directory-upload args', () => {
    const args = buildRsyncArgs({ isUpload: true }, 'ssh', 'rediacc');
    expect(args).toContain('--rsync-path');
    expect(args).toContain('sudo rsync');
    expect(args).toContain('rediacc:rediacc');
    for (const flag of ['--mkpath', '--delete', '--exclude']) {
      expect(args).not.toContain(flag);
    }
  });

  it('keeps --mkpath on the file transfer and off download', () => {
    expect(buildRsyncArgs({ isUpload: true, mkpath: true }, 'ssh', 'rediacc')).toContain(
      '--mkpath'
    );
    const download = buildRsyncArgs({}, 'ssh', 'rediacc');
    expect(download).not.toContain('--mkpath');
    expect(download).not.toContain('--chown');
  });
});
