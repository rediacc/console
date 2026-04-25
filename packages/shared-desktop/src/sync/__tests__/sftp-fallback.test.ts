import { createHash } from 'node:crypto';
import { chmodSync, mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { mockConnect, mockClose, mockExec, mockExecStreaming } = vi.hoisted(() => ({
  mockConnect: vi.fn(),
  mockClose: vi.fn(),
  mockExec: vi.fn(),
  mockExecStreaming: vi.fn(),
}));

vi.mock('../../sftp/client.js', () => ({
  SFTPClient: class MockSFTPClient {
    connected = false;
    connect = mockConnect;
    close = mockClose;
    exec = mockExec;
    execStreaming = mockExecStreaming;
  },
}));

import { isExcluded, sftpUploadFile, sftpUploadPaths } from '../sftp-fallback.js';

const config = {
  host: '127.0.0.1',
  port: 22,
  username: 'tester',
  privateKey: 'KEY',
} as const;

function execText(_cmd: string): string {
  // Default success behavior: exec returns empty stdout for mkdir/chmod/chown/ln
  return '';
}

beforeEach(() => {
  mockConnect.mockReset();
  mockClose.mockReset();
  mockExec.mockReset();
  mockExecStreaming.mockReset();
  mockConnect.mockResolvedValue(undefined);
  mockClose.mockReturnValue(undefined);
  mockExec.mockImplementation((cmd: string) => Promise.resolve(execText(cmd)));
  mockExecStreaming.mockResolvedValue(0);
});

describe('isExcluded (rsync-style patterns)', () => {
  // Bare pattern matches BASENAME (final path segment); pattern with leading `/`
  // anchors to root; pattern with `/` (not leading) matches path-relative anywhere;
  // trailing `/` restricts to directories. Walk pruning happens at the dir level.
  const cases: { path: string; isDir: boolean; pattern: string; expect: boolean }[] = [
    { path: 'foo.log', isDir: false, pattern: '*.log', expect: true },
    { path: 'sub/foo.log', isDir: false, pattern: '*.log', expect: true },
    { path: 'foo.txt', isDir: false, pattern: '*.log', expect: false },
    // Walk would prune the dir entry before descending; check at dir level.
    { path: 'node_modules', isDir: true, pattern: 'node_modules', expect: true },
    { path: 'pkg/node_modules', isDir: true, pattern: 'node_modules', expect: true },
    { path: 'src', isDir: true, pattern: 'src/', expect: true },
    { path: 'sub/src', isDir: true, pattern: 'src/', expect: true },
    { path: 'src/x.ts', isDir: false, pattern: 'src/', expect: false },
    { path: 'src', isDir: false, pattern: 'src/', expect: false },
    { path: 'build', isDir: true, pattern: '/build', expect: true },
    { path: 'build/out.js', isDir: false, pattern: '/build', expect: true },
    { path: 'sub/build/out.js', isDir: false, pattern: '/build', expect: false },
    { path: 'src/a/b.ts', isDir: false, pattern: '**/*.ts', expect: true },
    { path: 'a.ts', isDir: false, pattern: '**/*.ts', expect: true },
    { path: 'foo', isDir: false, pattern: 'f?o', expect: true },
    { path: 'foo/bar', isDir: false, pattern: 'f?o', expect: false },
    { path: 'baz/foo', isDir: false, pattern: 'f?o', expect: true },
  ];

  for (const c of cases) {
    it(`pattern '${c.pattern}' on '${c.path}' (${c.isDir ? 'dir' : 'file'}) -> ${c.expect}`, () => {
      expect(isExcluded(c.path, c.isDir, [c.pattern])).toBe(c.expect);
    });
  }
});

describe('compilePatterns + isExcludedCompiled (hot-path API)', () => {
  // Mirror behavior of isExcluded but with compilation hoisted out of the
  // loop. Walk callers should use this to avoid recompiling regex per file.
  it('compiles once and matches consistently on subsequent calls', async () => {
    const { compilePatterns, isExcludedCompiled } = await import('../sftp-patterns.js');
    const compiled = compilePatterns(['*.log', 'node_modules/', '/build']);
    // Compiled object identity is stable — important for hot loops that
    // capture and reuse the result across many isExcludedCompiled calls.
    expect(compiled).toHaveLength(3);
    expect(isExcludedCompiled('foo.log', false, compiled)).toBe(true);
    expect(isExcludedCompiled('node_modules', true, compiled)).toBe(true);
    expect(isExcludedCompiled('node_modules', false, compiled)).toBe(false);
    expect(isExcludedCompiled('build', true, compiled)).toBe(true);
    expect(isExcludedCompiled('foo.txt', false, compiled)).toBe(false);
    // Re-running with the same compiled list does not allocate new RegExp
    // objects — that's the whole point of separating compile from match.
    expect(isExcludedCompiled('bar/foo.log', false, compiled)).toBe(true);
  });

  it('empty pattern set never excludes', async () => {
    const { compilePatterns, isExcludedCompiled } = await import('../sftp-patterns.js');
    const compiled = compilePatterns([]);
    expect(compiled).toHaveLength(0);
    expect(isExcludedCompiled('any/path', false, compiled)).toBe(false);
    expect(isExcludedCompiled('any/path', true, compiled)).toBe(false);
  });
});

describe('sftpUploadFile', () => {
  let workDir: string;
  let localFile: string;

  beforeEach(() => {
    workDir = mkdtempSync(join(tmpdir(), 'sftp-upload-test-'));
    localFile = join(workDir, 'src.bin');
    writeFileSync(localFile, 'hello world');
  });

  afterEach(() => {
    rmSync(workDir, { recursive: true, force: true });
  });

  it('dryRun returns 1 file + size, never connects', async () => {
    const r = await sftpUploadFile(localFile, 'remote/x.bin', config, { dryRun: true });
    expect(r.success).toBe(true);
    expect(r.filesTransferred).toBe(1);
    expect(r.bytesTransferred).toBe(11);
    expect(mockConnect).not.toHaveBeenCalled();
    expect(mockExecStreaming).not.toHaveBeenCalled();
  });

  it('happy-path: mkdir -p parent, base64 -d > target, chmod, no chown', async () => {
    const r = await sftpUploadFile(localFile, 'a/b/c.bin', config);
    expect(r.success).toBe(true);
    expect(r.filesTransferred).toBe(1);
    expect(r.bytesTransferred).toBe(11);

    const execCmds = mockExec.mock.calls.map(([cmd]) => cmd as string);
    expect(execCmds).toContainEqual(expect.stringMatching(/^mkdir -p 'a\/b'$/));
    expect(execCmds.some((c) => c.startsWith('chmod ') && c.endsWith(`'a/b/c.bin'`))).toBe(true);
    expect(execCmds.some((c) => c.startsWith('sudo chown'))).toBe(false);

    expect(mockExecStreaming).toHaveBeenCalledTimes(1);
    const [cmd, opts] = mockExecStreaming.mock.calls[0];
    expect(cmd).toBe(`base64 -d > 'a/b/c.bin'`);
    expect(opts.stdin).toBe(Buffer.from('hello world').toString('base64'));
  });

  it('applies sudo chown -h when universalUser is set (no symlink dereference)', async () => {
    await sftpUploadFile(localFile, 'a/b.bin', config, { universalUser: 'svc' });
    const cmds = mockExec.mock.calls.map(([cmd]) => cmd as string);
    // -h prevents chown from following symlinks: uploading a symlink like
    // `link -> /etc/passwd` must NOT change ownership of the target.
    expect(cmds.some((c) => c.startsWith(`sudo chown -h 'svc:svc' 'a/b.bin'`))).toBe(true);
  });

  it('non-zero exit code -> success false, error message includes code', async () => {
    mockExecStreaming.mockResolvedValueOnce(7);
    const r = await sftpUploadFile(localFile, 'x.bin', config);
    expect(r.success).toBe(false);
    expect(r.errors.some((e) => e.includes('exit code 7'))).toBe(true);
    expect(r.filesTransferred).toBe(0);
  });

  it('empty file round-trips correctly', async () => {
    const empty = join(workDir, 'empty.bin');
    writeFileSync(empty, '');
    const r = await sftpUploadFile(empty, 'e.bin', config);
    expect(r.success).toBe(true);
    expect(r.bytesTransferred).toBe(0);
    expect(mockExecStreaming.mock.calls[0][1].stdin).toBe('');
  });

  it('verify pass: sha256 matches', async () => {
    const expected = createHash('sha256').update(Buffer.from('hello world')).digest('hex');
    mockExec.mockImplementation((cmd: string) => {
      if (cmd.startsWith('sha256sum')) return Promise.resolve(`${expected}  remote/x.bin\n`);
      return Promise.resolve('');
    });
    const r = await sftpUploadFile(localFile, 'remote/x.bin', config, { verify: true });
    expect(r.success).toBe(true);
    expect(r.verifyFailures).toBe(0);
  });

  it('verify mismatch: success false, verifyFailures bumped', async () => {
    mockExec.mockImplementation((cmd: string) => {
      if (cmd.startsWith('sha256sum')) return Promise.resolve(`0000  remote/x.bin\n`);
      return Promise.resolve('');
    });
    const r = await sftpUploadFile(localFile, 'remote/x.bin', config, { verify: true });
    expect(r.success).toBe(false);
    expect(r.verifyFailures).toBe(1);
    expect(r.errors.some((e) => e.includes('verify mismatch'))).toBe(true);
  });

  it('preserves executable bit via chmod', async () => {
    const exe = join(workDir, 'run.sh');
    writeFileSync(exe, '#!/bin/sh\necho hi\n');
    chmodSync(exe, 0o755);
    await sftpUploadFile(exe, 'bin/run.sh', config);
    const cmds = mockExec.mock.calls.map(([c]) => c as string);
    expect(cmds.some((c) => c === `chmod 755 'bin/run.sh'`)).toBe(true);
  });

  it('connects and closes even on errors', async () => {
    mockExecStreaming.mockRejectedValueOnce(new Error('boom'));
    const r = await sftpUploadFile(localFile, 'x.bin', config);
    expect(r.success).toBe(false);
    expect(mockConnect).toHaveBeenCalled();
    expect(mockClose).toHaveBeenCalled();
  });
});

describe('sftpUploadPaths', () => {
  let workDir: string;

  beforeEach(() => {
    workDir = mkdtempSync(join(tmpdir(), 'sftp-uploadpaths-test-'));
  });

  afterEach(() => {
    rmSync(workDir, { recursive: true, force: true });
  });

  it('preserves mode bits per file', async () => {
    const dir = join(workDir, 'tree');
    mkdirSync(dir);
    const exe = join(dir, 'run.sh');
    const txt = join(dir, 'note.txt');
    writeFileSync(exe, 'echo hi');
    writeFileSync(txt, 'hello');
    chmodSync(exe, 0o755);
    chmodSync(txt, 0o644);

    await sftpUploadPaths([{ path: dir, isFile: false }], 'dest', config);

    const cmds = mockExec.mock.calls.map(([c]) => c as string);
    expect(cmds.some((c) => c === `chmod 755 'dest/run.sh'`)).toBe(true);
    expect(cmds.some((c) => c === `chmod 644 'dest/note.txt'`)).toBe(true);
  });

  it('preserves symlinks via ln -sfn', async () => {
    const dir = join(workDir, 'tree');
    mkdirSync(dir);
    writeFileSync(join(dir, 'real.txt'), 'real');
    symlinkSync('real.txt', join(dir, 'link.txt'));

    await sftpUploadPaths([{ path: dir, isFile: false }], 'dest', config);

    const cmds = mockExec.mock.calls.map(([c]) => c as string);
    expect(cmds.some((c) => c === `ln -sfn 'real.txt' 'dest/link.txt'`)).toBe(true);
    // The real file is uploaded normally:
    const streaming = mockExecStreaming.mock.calls.map(([c]) => c as string);
    expect(streaming).toContain(`base64 -d > 'dest/real.txt'`);
  });

  it('mkdir is per-dir; one failed dir does not abort others', async () => {
    const dir = join(workDir, 'tree');
    mkdirSync(join(dir, 'a'), { recursive: true });
    mkdirSync(join(dir, 'b'), { recursive: true });
    writeFileSync(join(dir, 'a', 'one.txt'), '1');
    writeFileSync(join(dir, 'b', 'two.txt'), '2');

    mockExec.mockImplementation((cmd: string) => {
      if (cmd === `mkdir -p 'dest/a'`) throw new Error('permission denied');
      return Promise.resolve('');
    });

    const r = await sftpUploadPaths([{ path: dir, isFile: false }], 'dest', config);
    // Both files attempted; the failing dir reported in errors.
    expect(r.errors.some((e) => e.includes('mkdir dest/a'))).toBe(true);
    // mkdir for dest/b still attempted:
    const cmds = mockExec.mock.calls.map(([c]) => c as string);
    expect(cmds).toContain(`mkdir -p 'dest/b'`);
  });

  it('chowns all written paths once when universalUser is set', async () => {
    const dir = join(workDir, 'tree');
    mkdirSync(dir);
    writeFileSync(join(dir, 'a.txt'), 'a');
    writeFileSync(join(dir, 'b.txt'), 'b');

    await sftpUploadPaths([{ path: dir, isFile: false }], 'dest', config, { universalUser: 'svc' });
    const cmds = mockExec.mock.calls.map(([c]) => c as string);
    const chownCalls = cmds.filter((c) => c.startsWith('sudo chown'));
    expect(chownCalls.length).toBeGreaterThanOrEqual(1);
    // All file paths are in the single chown call (one chunk).
    expect(chownCalls.some((c) => c.includes(`'dest/a.txt'`) && c.includes(`'dest/b.txt'`))).toBe(
      true
    );
  });

  it('exclude patterns filter walked files', async () => {
    const dir = join(workDir, 'tree');
    mkdirSync(join(dir, 'sub'), { recursive: true });
    writeFileSync(join(dir, 'a.txt'), 'a');
    writeFileSync(join(dir, 'b.log'), 'b');
    writeFileSync(join(dir, 'sub', 'c.log'), 'c');

    const r = await sftpUploadPaths([{ path: dir, isFile: false }], 'dest', config, {
      exclude: ['*.log'],
    });
    // Only a.txt should have been transferred.
    const streaming = mockExecStreaming.mock.calls.map(([c]) => c as string);
    expect(streaming).toContain(`base64 -d > 'dest/a.txt'`);
    expect(streaming.some((c) => c.includes('b.log'))).toBe(false);
    expect(streaming.some((c) => c.includes('c.log'))).toBe(false);
    expect(r.filesTransferred).toBe(1);
  });

  it('verify mismatch in single-file source surfaces in errors + verifyFailures', async () => {
    const f = join(workDir, 'one.bin');
    writeFileSync(f, 'data');

    mockExec.mockImplementation((cmd: string) => {
      if (cmd.startsWith('sha256sum')) return Promise.resolve(`0000  dest/one.bin\n`);
      return Promise.resolve('');
    });
    const r = await sftpUploadPaths([{ path: f, isFile: true }], 'dest', config, { verify: true });
    expect(r.verifyFailures).toBe(1);
    expect(r.success).toBe(false);
    expect(r.errors.some((e) => e.includes('verify mismatch'))).toBe(true);
  });

  it('dryRun counts files without invoking transfer commands', async () => {
    const dir = join(workDir, 'tree');
    mkdirSync(dir);
    writeFileSync(join(dir, 'a.txt'), 'aa');
    writeFileSync(join(dir, 'b.txt'), 'bbb');

    const r = await sftpUploadPaths([{ path: dir, isFile: false }], 'dest', config, {
      dryRun: true,
    });
    expect(r.filesTransferred).toBe(2);
    expect(r.bytesTransferred).toBe(5);
    expect(mockConnect).not.toHaveBeenCalled();
    expect(mockExecStreaming).not.toHaveBeenCalled();
  });
});
