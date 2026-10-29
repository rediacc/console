/**
 * A dirty renet working tree no longer blocks a provisioning upload: the binary is built from the
 * committed HEAD in a scratch clone and that build is uploaded.
 *
 * THE DEFECT THIS PINS (2026-10-23). The upload guard refused every production `rdc repo up`
 * whenever any session had uncommitted edits in private/renet, and the hostinger observability
 * stack could only be restarted by a raw `sudo renet repository up` over `term connect`.
 *
 * git and the build run through injected seams (and a mocked `execFileSync` for the dirty probe);
 * the filesystem is real, under a temp dir.
 */

import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { RenetCleanBuildDeps } from '../renet-execution.js';

const { mockExecFileSync, mockProvision, mockInfo } = vi.hoisted(() => ({
  mockExecFileSync: vi.fn(),
  mockProvision: vi.fn(),
  mockInfo: vi.fn(),
}));

vi.mock('node:child_process', async (importOriginal) => ({
  ...(await importOriginal<typeof import('node:child_process')>()),
  execFileSync: mockExecFileSync,
}));
vi.mock('../renet-provisioner.js', () => ({
  renetProvisioner: { inspect: vi.fn(), provision: mockProvision },
}));
vi.mock('../../core/output.js', () => ({
  outputService: { warn: vi.fn(), info: mockInfo },
}));
vi.mock('../../core/embedded-assets.js', () => ({ isSEA: () => false }));
vi.mock('../../machine/machine-connection.js', () => ({
  sftpConfigForMachine: vi.fn(() => ({ host: '10.0.0.5', username: 'root', privateKey: 'k' })),
  withSharedOrPooledSftp: vi.fn(),
}));
vi.mock('../provision-state.js', () => ({
  isSetupVerifiedFresh: vi.fn(() => Promise.resolve(false)),
  recordSetupVerified: vi.fn(() => Promise.resolve()),
}));

const SHA = 'a'.repeat(40);
const OLD_SHA = 'b'.repeat(40);
const MACHINE = { ip: '10.0.0.5', user: 'root', port: 22 };

let tmp: string;
let superproject: string;
let top: string;
let workingBinary: string;

/** The dirty probe (`renetSourceState`) answers through execFileSync. */
function porcelain(lines: string) {
  mockExecFileSync.mockImplementation((_cmd: string, args: string[]) => {
    if (args.includes('--show-toplevel')) return `${top}\n`;
    if (args.includes('--porcelain')) return lines;
    throw new Error(`unexpected git ${args.join(' ')}`);
  });
}

interface FakeOptions {
  cloneLeftDirty?: boolean;
  /** Overrides the buildinfo every `go version -m` answers. */
  stamp?: string;
  /** Flavor of the working-tree binary; the default is nolicense. */
  workingFlavor?: 'nolicense' | 'enforce';
}

const nolicenseInfo = (sha = SHA) =>
  `\tbuild\t-tags=nolicense\n\tbuild\tvcs.revision=${sha}\n\tbuild\tvcs.modified=false\n`;
const enforceInfo = (sha = SHA) => `\tbuild\tvcs.revision=${sha}\n\tbuild\tvcs.modified=false\n`;

/** The clone stands in for `git clone`: a work dir holding the BPF source the build pins. */
function fakeClone(work: string): string {
  fs.mkdirSync(path.join(work, 'pkg', 'ebpf'), { recursive: true });
  fs.writeFileSync(path.join(work, 'pkg', 'ebpf', 'socket_isolation.c'), '');
  return '';
}

function fakeGitAnswer(args: string[], cwd: string, opts: FakeOptions): string {
  const answers: Record<string, () => string> = {
    'rev-parse HEAD': () => SHA,
    'rev-parse --show-superproject-working-tree': () => superproject,
    clone: () => fakeClone(args[args.length - 1]),
    '-c': () => '',
    status: () => (opts.cloneLeftDirty ? ' M pkg/ebpf/x.o' : ''),
  };
  const answer = answers[args.slice(0, 2).join(' ')] ?? answers[args[0]];
  if (!answer) throw new Error(`unexpected git ${args.join(' ')} in ${cwd}`);
  return answer();
}

function fakeDeps(opts: FakeOptions = {}) {
  const calls: string[][] = [];
  const builds: { cwd: string; env: NodeJS.ProcessEnv; sawAsset: boolean; flag: string }[] = [];
  const buildFlavor = (flag: string) => (flag === '--license' ? 'enforce' : 'nolicense');
  const deps: RenetCleanBuildDeps = {
    git: vi.fn((args: string[], cwd: string) => {
      calls.push(args);
      return fakeGitAnswer(args, cwd, opts);
    }),
    build: vi.fn((cwd: string, env: NodeJS.ProcessEnv, flag: string) => {
      builds.push({
        cwd,
        env,
        flag,
        sawAsset: fs.existsSync(path.join(cwd, 'pkg', 'embed', 'assets', 'amd64', 'x.zst')),
      });
      const outDir = path.join(cwd, buildFlavor(flag) === 'enforce' ? 'bin/enforce' : 'bin');
      fs.mkdirSync(outDir, { recursive: true });
      for (const name of ['renet', 'renet-linux-amd64', 'renet-linux-arm64']) {
        fs.writeFileSync(path.join(outDir, name), `built ${name}`);
      }
      return Promise.resolve();
    }),
    goVersionM: vi.fn((binary: string) => {
      if (opts.stamp) return opts.stamp;
      if (binary === workingBinary) {
        return opts.workingFlavor === 'enforce' ? enforceInfo() : nolicenseInfo();
      }
      return binary.includes(`${path.sep}enforce${path.sep}`) ? enforceInfo() : nolicenseInfo();
    }),
  };
  return { deps, calls, builds };
}

const cacheRoot = () => path.join(superproject, '.ci', 'cache', 'renet-head');

function load() {
  return import('../renet-execution.js');
}

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  delete process.env.REDIACC_ALLOW_DIRTY_RENET;
  delete process.env.REDIACC_SKIP_ROUTER_RESTART;
  delete process.env.ACCOUNT_ED25519_PUBLIC_KEY;
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'renet-clean-build-'));
  superproject = path.join(tmp, 'console');
  top = path.join(superproject, 'private', 'renet');
  workingBinary = path.join(top, 'bin', 'renet');
  fs.mkdirSync(path.join(top, 'bin'), { recursive: true });
  fs.writeFileSync(workingBinary, 'dirty build');
  fs.mkdirSync(path.join(top, 'pkg', 'embed', 'assets', 'amd64'), { recursive: true });
  fs.writeFileSync(path.join(top, 'pkg', 'embed', 'assets', 'amd64', 'x.zst'), 'asset');
  fs.mkdirSync(path.join(superproject, 'private', 'account', '.cache'), { recursive: true });
  fs.writeFileSync(
    path.join(superproject, 'private', 'account', '.cache', 'public-keys.env'),
    'ACCOUNT_ED25519_PUBLIC_KEY=fixture-public-key\n'
  );
});

afterEach(() => {
  fs.rmSync(tmp, { recursive: true, force: true });
});

describe('selectRenetUploadBinary', () => {
  it('a clean tree uploads the working-tree binary under the guard and builds nothing', async () => {
    porcelain('');
    const { selectRenetUploadBinary } = await load();
    const { deps } = fakeDeps();
    const selection = await selectRenetUploadBinary(workingBinary, deps);
    expect(selection).toEqual({
      localBinaryPath: workingBinary,
      cleanCommit: null,
      excludedPaths: 0,
      guarded: true,
    });
    expect(deps.build).not.toHaveBeenCalled();
  });

  it('REDIACC_ALLOW_DIRTY_RENET=1 uploads the dirty working-tree build as it is', async () => {
    porcelain(' M pkg/list.go\n');
    process.env.REDIACC_ALLOW_DIRTY_RENET = '1';
    const { selectRenetUploadBinary } = await load();
    const { deps } = fakeDeps();
    const selection = await selectRenetUploadBinary(workingBinary, deps);
    expect(selection.localBinaryPath).toBe(workingBinary);
    expect(selection.cleanCommit).toBeNull();
    expect(deps.build).not.toHaveBeenCalled();
    expect(mockExecFileSync).not.toHaveBeenCalled();
  });

  it('a binary outside any git tree is used as it is', async () => {
    mockExecFileSync.mockImplementation(() => {
      throw new Error('not a git repository');
    });
    const { selectRenetUploadBinary } = await load();
    const { deps } = fakeDeps();
    const selection = await selectRenetUploadBinary('/usr/local/bin/renet', deps);
    expect(selection.localBinaryPath).toBe('/usr/local/bin/renet');
    expect(deps.build).not.toHaveBeenCalled();
  });

  it('a dirty tree builds committed HEAD in a shared clone and selects that build', async () => {
    porcelain(' M pkg/list.go\n?? pkg/new.go\n');
    const { selectRenetUploadBinary } = await load();
    const { deps, calls, builds } = fakeDeps();
    const selection = await selectRenetUploadBinary(workingBinary, deps);

    const finalDir = path.join(cacheRoot(), `${SHA}-nolicense`);
    expect(selection).toEqual({
      localBinaryPath: path.join(finalDir, 'renet'),
      cleanCommit: SHA,
      excludedPaths: 2,
      guarded: false,
    });
    for (const name of ['renet', 'renet-linux-amd64', 'renet-linux-arm64']) {
      expect(fs.readFileSync(path.join(finalDir, name), 'utf-8')).toBe(`built ${name}`);
    }
    // A shared clone and a detached switch to HEAD; never a worktree.
    const clone = calls.find((c) => c[0] === 'clone');
    expect(clone).toEqual(expect.arrayContaining(['--shared', '--no-checkout', top]));
    expect(calls).toContainEqual(expect.arrayContaining(['switch', '--detach', SHA]));
    expect(calls.flat()).not.toContain('worktree');
    // The build ran in the clone, with the staged assets and the working tree's licence key.
    expect(builds).toHaveLength(1);
    expect(builds[0].cwd).not.toBe(top);
    expect(builds[0].sawAsset).toBe(true);
    expect(builds[0].flag).toBe('--nolicense');
    expect(builds[0].env.ACCOUNT_ED25519_PUBLIC_KEY).toBe('fixture-public-key');
    // The scratch clone is gone; only the per-commit build remains.
    expect(fs.readdirSync(cacheRoot())).toEqual([`${SHA}-nolicense`]);
    // The working tree's own binary is untouched.
    expect(fs.readFileSync(workingBinary, 'utf-8')).toBe('dirty build');
    expect(mockInfo.mock.calls.flat().join('\n')).toMatch(
      new RegExp(`committed HEAD ${SHA.slice(0, 12)}.*local edits not included`)
    );
  });

  it('a second call for the same commit reuses the cached build', async () => {
    porcelain(' M pkg/list.go\n');
    const { selectRenetUploadBinary } = await load();
    const first = fakeDeps();
    await selectRenetUploadBinary(workingBinary, first.deps);
    const second = fakeDeps();
    const selection = await selectRenetUploadBinary(workingBinary, second.deps);
    expect(selection.cleanCommit).toBe(SHA);
    expect(second.deps.build).not.toHaveBeenCalled();
  });

  it('rebuilds over an incomplete cached directory instead of failing the rename', async () => {
    porcelain(' M pkg/list.go\n');
    const finalDir = path.join(cacheRoot(), `${SHA}-nolicense`);
    fs.mkdirSync(finalDir, { recursive: true });
    // A finished marker with two binaries missing: not complete, and not empty.
    fs.writeFileSync(path.join(finalDir, 'renet'), 'partial');
    fs.writeFileSync(path.join(finalDir, '.complete'), `${SHA}\nkeyed\nnolicense\n`);
    const { selectRenetUploadBinary } = await load();
    const { deps } = fakeDeps();
    await selectRenetUploadBinary(workingBinary, deps);
    expect(deps.build).toHaveBeenCalledTimes(1);
    expect(fs.readFileSync(path.join(finalDir, 'renet-linux-arm64'), 'utf-8')).toBe(
      'built renet-linux-arm64'
    );
  });

  it('does not reuse a keyless build once the licence key is available', async () => {
    porcelain(' M pkg/list.go\n');
    const finalDir = path.join(cacheRoot(), `${SHA}-nolicense`);
    fs.mkdirSync(finalDir, { recursive: true });
    for (const name of ['renet', 'renet-linux-amd64', 'renet-linux-arm64']) {
      fs.writeFileSync(path.join(finalDir, name), 'keyless');
    }
    fs.writeFileSync(path.join(finalDir, '.complete'), `${SHA}\nkeyless\nnolicense\n`);
    const { selectRenetUploadBinary } = await load();
    const { deps } = fakeDeps();
    await selectRenetUploadBinary(workingBinary, deps);
    expect(deps.build).toHaveBeenCalledTimes(1);
    expect(fs.readFileSync(path.join(finalDir, 'renet'), 'utf-8')).toBe('built renet');
    expect(fs.readFileSync(path.join(finalDir, '.complete'), 'utf-8')).toBe(
      `${SHA}\nkeyed\nnolicense\n`
    );
  });

  it('a build of a new commit prunes the previous commit builds of both flavors', async () => {
    porcelain(' M pkg/list.go\n');
    for (const flavor of ['nolicense', 'enforce']) {
      fs.mkdirSync(path.join(cacheRoot(), `${OLD_SHA}-${flavor}`), { recursive: true });
    }
    const { selectRenetUploadBinary } = await load();
    await selectRenetUploadBinary(workingBinary, fakeDeps().deps);
    expect(fs.readdirSync(cacheRoot())).toEqual([`${SHA}-nolicense`]);
  });

  it('a dirty tree with an enforcing working-tree binary builds with --license', async () => {
    porcelain(' M pkg/list.go\n');
    const { selectRenetUploadBinary } = await load();
    const { deps, builds } = fakeDeps({ workingFlavor: 'enforce' });
    const selection = await selectRenetUploadBinary(workingBinary, deps);
    expect(builds.map((b) => b.flag)).toEqual(['--license']);
    expect(selection.localBinaryPath).toBe(path.join(cacheRoot(), `${SHA}-enforce`, 'renet'));
  });
});

describe('selectRenetUploadBinary when go cannot read the working-tree binary', () => {
  function unreadable(deps: RenetCleanBuildDeps): void {
    const real = deps.goVersionM;
    deps.goVersionM = vi.fn((binary: string) => {
      if (binary === workingBinary) throw new Error('spawn go ENOENT');
      return real(binary);
    });
  }

  it('reuses the one complete cached build of the commit instead of failing', async () => {
    porcelain(' M pkg/list.go\n');
    const { selectRenetUploadBinary } = await load();
    await selectRenetUploadBinary(workingBinary, fakeDeps({ workingFlavor: 'enforce' }).deps);
    const second = fakeDeps();
    unreadable(second.deps);
    const selection = await selectRenetUploadBinary(workingBinary, second.deps);
    expect(selection.localBinaryPath).toBe(path.join(cacheRoot(), `${SHA}-enforce`, 'renet'));
    expect(second.deps.build).not.toHaveBeenCalled();
  });

  it('with no cached build, names the binary and the go failure', async () => {
    porcelain(' M pkg/list.go\n');
    const { selectRenetUploadBinary } = await load();
    const { deps } = fakeDeps();
    unreadable(deps);
    await expect(selectRenetUploadBinary(workingBinary, deps)).rejects.toThrow(
      `Cannot read the build flavor of ${workingBinary} with \`go version -m\` (spawn go ENOENT)`
    );
    expect(deps.build).not.toHaveBeenCalled();
  });
});

describe('buildRenetAtCommit flavors', () => {
  it('does not reuse a complete nolicense cache for an enforcing request at the same commit', async () => {
    const { buildRenetAtCommit } = await load();
    const first = fakeDeps();
    await buildRenetAtCommit(top, SHA, first.deps, 'nolicense');
    const second = fakeDeps();
    const binary = await buildRenetAtCommit(top, SHA, second.deps, 'enforce');
    expect(second.builds.map((b) => b.flag)).toEqual(['--license']);
    expect(binary).toBe(path.join(cacheRoot(), `${SHA}-enforce`, 'renet'));
    expect(fs.readFileSync(binary, 'utf-8')).toBe('built renet');
  });

  it('keeps both flavors of the current commit when pruning and drops other commits', async () => {
    fs.mkdirSync(path.join(cacheRoot(), `${OLD_SHA}-enforce`), { recursive: true });
    fs.mkdirSync(path.join(cacheRoot(), OLD_SHA), { recursive: true });
    const { buildRenetAtCommit } = await load();
    await buildRenetAtCommit(top, SHA, fakeDeps().deps, 'nolicense');
    await buildRenetAtCommit(top, SHA, fakeDeps().deps, 'enforce');
    expect(fs.readdirSync(cacheRoot()).sort()).toEqual([`${SHA}-enforce`, `${SHA}-nolicense`]);
  });

  it('an enforcing request reads work/bin/enforce/renet', async () => {
    const { buildRenetAtCommit } = await load();
    const { deps } = fakeDeps();
    await buildRenetAtCommit(top, SHA, deps, 'enforce');
    const read = (deps.goVersionM as ReturnType<typeof vi.fn>).mock.calls.map(
      (c) => c[0] as string
    );
    expect(read).toHaveLength(3);
    for (const binary of read) expect(binary).toMatch(/work-[^/]+\/bin\/enforce\/renet/);
  });

  it('an enforcing request refuses a clone build whose buildinfo says tags=nolicense', async () => {
    const { buildRenetAtCommit } = await load();
    const { deps } = fakeDeps({ stamp: nolicenseInfo() });
    await expect(buildRenetAtCommit(top, SHA, deps, 'enforce')).rejects.toThrow(
      /not the enforce flavor/
    );
    expect(fs.readdirSync(cacheRoot())).toEqual([]);
  });

  it('the plain flavor passes --nolicense and reads work/bin/renet', async () => {
    const { buildRenetAtCommit } = await load();
    const { deps, builds } = fakeDeps();
    await buildRenetAtCommit(top, SHA, deps);
    expect(builds.map((b) => b.flag)).toEqual(['--nolicense']);
    const read = (deps.goVersionM as ReturnType<typeof vi.fn>).mock.calls.map(
      (c) => c[0] as string
    );
    expect(read[0]).toMatch(/work-[^/]+\/bin\/renet$/);
  });
});

describe('buildRenetAtCommit refusals', () => {
  it('refuses a build whose stamp is not the commit, and caches nothing', async () => {
    const { buildRenetAtCommit } = await load();
    const { deps } = fakeDeps({
      stamp: nolicenseInfo(OLD_SHA),
    });
    await expect(buildRenetAtCommit(top, SHA, deps)).rejects.toThrow(/vcs\.revision=a{40}/);
    expect(fs.readdirSync(cacheRoot())).toEqual([]);
  });

  it('refuses a build that left the clone modified', async () => {
    const { buildRenetAtCommit } = await load();
    const { deps } = fakeDeps({ cloneLeftDirty: true });
    await expect(buildRenetAtCommit(top, SHA, deps)).rejects.toThrow(/changed tracked files/);
    expect(fs.readdirSync(cacheRoot())).toEqual([]);
  });

  it('refuses vcs.modified=true', async () => {
    const { buildRenetAtCommit } = await load();
    const { deps } = fakeDeps({
      stamp: `\tbuild\t-tags=nolicense\n\tbuild\tvcs.revision=${SHA}\n\tbuild\tvcs.modified=true\n`,
    });
    await expect(buildRenetAtCommit(top, SHA, deps)).rejects.toThrow(/vcs\.modified=false/);
  });
});

describe('acquireRemoteRenet with a dirty renet tree', () => {
  it('provisions the clean build without the dirty guard and names the uploaded commit', async () => {
    porcelain(' M pkg/list.go\n');
    // Pre-seed the cache so acquireRemoteRenet's real build seam is never reached.
    const finalDir = path.join(cacheRoot(), `${SHA}-nolicense`);
    fs.mkdirSync(finalDir, { recursive: true });
    for (const name of ['renet', 'renet-linux-amd64', 'renet-linux-arm64']) {
      fs.writeFileSync(path.join(finalDir, name), 'built');
    }
    fs.writeFileSync(path.join(finalDir, '.complete'), `${SHA}\nkeyed\nnolicense\n`);
    const answers: [string, string][] = [
      ['--show-toplevel', `${top}\n`],
      ['--porcelain', ' M pkg/list.go\n'],
      ['--show-superproject-working-tree', `${superproject}\n`],
      ['HEAD', `${SHA}\n`],
      ['version', nolicenseInfo()],
    ];
    mockExecFileSync.mockImplementation((_cmd: string, args: string[]) => {
      const hit = answers.find(([flag]) => args.includes(flag));
      if (!hit) throw new Error(`unexpected git ${args.join(' ')}`);
      return hit[1];
    });
    mockProvision.mockResolvedValue({
      success: true,
      action: 'uploaded',
      arch: 'amd64',
      remotePath: '/usr/lib/rediacc/renet/1.2.4/renet',
    });
    const { acquireRemoteRenet } = await load();
    await acquireRemoteRenet('provision', { renetPath: workingBinary }, MACHINE, 'key', {});

    const options = mockProvision.mock.calls[0][1] as {
      localBinaryPath: string;
      uploadGuard?: unknown;
    };
    expect(options.localBinaryPath).toBe(path.join(finalDir, 'renet'));
    expect(options.uploadGuard).toBeUndefined();
    expect(mockInfo.mock.calls.flat().join('\n')).toMatch(
      new RegExp(`Uploaded renet built from committed HEAD ${SHA.slice(0, 12)}; 1 uncommitted`)
    );
  });

  it('control: a clean tree still provisions the working-tree binary under the guard', async () => {
    porcelain('');
    mockProvision.mockResolvedValue({
      success: true,
      action: 'verified',
      arch: 'amd64',
      remotePath: '/usr/lib/rediacc/renet/1.2.4/renet',
    });
    const { acquireRemoteRenet } = await load();
    await acquireRemoteRenet('provision', { renetPath: workingBinary }, MACHINE, 'key', {});
    const options = mockProvision.mock.calls[0][1] as {
      localBinaryPath: string;
      uploadGuard?: unknown;
    };
    expect(options.localBinaryPath).toBe(workingBinary);
    expect(typeof options.uploadGuard).toBe('function');
  });
});
