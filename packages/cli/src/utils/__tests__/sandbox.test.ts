import { describe, expect, it } from 'vitest';
import { buildSandboxPrefix, buildTermSandboxOptions, shellEscapeForBashC } from '../sandbox.js';

describe('buildSandboxPrefix', () => {
  it('returns empty string when no read-write paths', () => {
    const result = buildSandboxPrefix({
      allowedReadWrite: [],
      allowedReadOnly: ['/usr'],
      allowedExecute: ['/bin'],
    });
    expect(result).toBe('');
  });

  it('builds correct prefix with all options', () => {
    const result = buildSandboxPrefix({
      allowedReadWrite: ['/mnt/rediacc/mounts/abc123', '/tmp'],
      allowedReadOnly: ['/usr', '/etc'],
      allowedExecute: ['/bin'],
      dockerSocket: '/var/run/rediacc/docker-3200.sock',
    });

    expect(result).toContain('renet sandbox-exec');
    expect(result).toContain('--allow-rw /mnt/rediacc/mounts/abc123');
    expect(result).toContain('--allow-rw /tmp');
    expect(result).toContain('--allow-ro /usr');
    expect(result).toContain('--allow-ro /etc');
    expect(result).toContain('--allow-exec /bin');
    expect(result).toContain('--docker-socket /var/run/rediacc/docker-3200.sock');
    expect(result).toMatch(/--$/);
  });

  it('omits docker-socket when not provided', () => {
    const result = buildSandboxPrefix({
      allowedReadWrite: ['/tmp'],
      allowedReadOnly: [],
      allowedExecute: [],
    });

    expect(result).not.toContain('--docker-socket');
    expect(result).toMatch(/--$/);
  });

  it('quotes paths with spaces', () => {
    const result = buildSandboxPrefix({
      allowedReadWrite: ['/path with spaces'],
      allowedReadOnly: [],
      allowedExecute: [],
    });

    expect(result).toContain("--allow-rw '/path with spaces'");
  });
});

describe('buildTermSandboxOptions', () => {
  it('returns null for machine-only connections (no workingDirectory)', () => {
    expect(buildTermSandboxOptions(undefined)).toBeNull();
    expect(buildTermSandboxOptions({})).toBeNull();
    expect(buildTermSandboxOptions({ user: 'rediacc' })).toBeNull();
  });

  it('returns correct options for repo connections', () => {
    const result = buildTermSandboxOptions({
      workingDirectory: '/mnt/rediacc/mounts/abc123',
      user: 'muhammed',
      environment: {
        DOCKER_SOCKET: '/var/run/rediacc/docker-3200.sock',
      },
    });

    expect(result).not.toBeNull();
    expect(result!.allowedReadWrite).toContain('/mnt/rediacc/mounts/abc123');
    expect(result!.allowedReadWrite).toContain('/tmp');
    expect(result!.allowedReadWrite).toContain('/dev');
    expect(result!.allowedReadOnly).toContain('/home/muhammed');
    expect(result!.allowedReadOnly).toContain('/usr');
    expect(result!.allowedReadOnly).toContain('/etc');
    expect(result!.allowedReadOnly).toContain('/var/run/rediacc');
    expect(result!.allowedExecute).toContain('/usr');
    expect(result!.allowedExecute).toContain('/bin');
    expect(result!.dockerSocket).toBe('/var/run/rediacc/docker-3200.sock');
  });

  it('defaults user to rediacc', () => {
    const result = buildTermSandboxOptions({
      workingDirectory: '/mnt/rediacc/mounts/abc123',
    });

    expect(result).not.toBeNull();
    expect(result!.allowedReadOnly).toContain('/home/rediacc');
  });

  it('omits dockerSocket when not in environment', () => {
    const result = buildTermSandboxOptions({
      workingDirectory: '/mnt/rediacc/mounts/abc123',
      environment: {},
    });

    expect(result).not.toBeNull();
    expect(result!.dockerSocket).toBeUndefined();
  });
});

describe('shellEscapeForBashC', () => {
  it('passes through simple strings', () => {
    expect(shellEscapeForBashC('echo hello')).toBe('echo hello');
  });

  it('escapes single quotes', () => {
    expect(shellEscapeForBashC("echo 'hello'")).toBe("echo '\\''hello'\\''");
  });

  it('escapes multiple single quotes', () => {
    expect(shellEscapeForBashC("it's a test's")).toBe("it'\\''s a test'\\''s");
  });

  it('preserves double quotes and other characters', () => {
    expect(shellEscapeForBashC('echo "hello" $VAR')).toBe('echo "hello" $VAR');
  });
});
