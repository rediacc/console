import { chmod, mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import {
  describeTofuFailure,
  getPluginCacheDir,
  parseEngineVersion,
  resolveTofu,
  TofuExecutor,
  type TofuResolution,
} from '../executor.js';

const MANAGED = '/state/tools/opentofu/1.10.6/tofu';

/** Probe answers by path: the stdout of `<path> version`, or absent when it does not run. */
function probes(answers: Record<string, string>) {
  return (path: string) => Promise.resolve(answers[path] ?? null);
}

function onPath(found: Record<string, string>) {
  return (cmd: string) => found[cmd] ?? null;
}

function failure(r: TofuResolution) {
  if (r.ok) throw new Error('expected a failed resolution');
  return r;
}

describe('parseEngineVersion', () => {
  it('reads both engines', () => {
    expect(parseEngineVersion('OpenTofu v1.10.6\non linux_amd64\n')).toEqual({
      engine: 'tofu',
      version: '1.10.6',
    });
    expect(parseEngineVersion('Terraform v1.5.7\non darwin_arm64')).toEqual({
      engine: 'terraform',
      version: '1.5.7',
    });
    expect(parseEngineVersion('something else')).toBeNull();
  });
});

describe('resolveTofu lookup order', () => {
  const everything = {
    '/override/tofu': 'OpenTofu v1.9.0',
    [MANAGED]: 'OpenTofu v1.10.6',
    '/usr/bin/tofu': 'OpenTofu v1.8.0',
    '/usr/bin/terraform': 'Terraform v1.9.0',
  };
  const path = onPath({ tofu: '/usr/bin/tofu', terraform: '/usr/bin/terraform' });

  it('REDIACC_TOFU wins over everything', async () => {
    const r = await resolveTofu({
      env: { REDIACC_TOFU: '/override/tofu' },
      managedPath: MANAGED,
      findOnPath: path,
      probe: probes(everything),
    });
    expect(r).toEqual({
      ok: true,
      engine: { engine: 'tofu', version: '1.9.0', path: '/override/tofu', source: 'env' },
    });
  });

  it("then rdc's tools dir at the pinned version", async () => {
    const r = await resolveTofu({
      env: {},
      managedPath: MANAGED,
      findOnPath: path,
      probe: probes(everything),
    });
    expect(r.ok && r.engine).toMatchObject({ path: MANAGED, source: 'rdc', version: '1.10.6' });
  });

  it('then tofu on PATH', async () => {
    const rest = Object.fromEntries(Object.entries(everything).filter(([k]) => k !== MANAGED));
    const r = await resolveTofu({
      env: {},
      managedPath: MANAGED,
      findOnPath: path,
      probe: probes(rest),
    });
    expect(r.ok && r.engine).toMatchObject({
      path: '/usr/bin/tofu',
      source: 'path',
      engine: 'tofu',
    });
  });

  it('then terraform on PATH', async () => {
    const r = await resolveTofu({
      env: {},
      managedPath: MANAGED,
      findOnPath: onPath({ terraform: '/usr/bin/terraform' }),
      probe: probes({ '/usr/bin/terraform': 'Terraform v1.9.0' }),
    });
    expect(r.ok && r.engine).toMatchObject({ engine: 'terraform', path: '/usr/bin/terraform' });
  });

  it('reports missing when nothing runs', async () => {
    const r = await resolveTofu({
      env: {},
      managedPath: MANAGED,
      findOnPath: onPath({}),
      probe: probes({}),
    });
    expect(r).toEqual({ ok: false, reason: 'missing' });
    expect(describeTofuFailure(failure(r))).toContain('rdc tools install tofu');
  });
});

describe('resolveTofu version floors', () => {
  it('refuses a terraform below 1.5', async () => {
    const r = await resolveTofu({
      env: {},
      managedPath: MANAGED,
      findOnPath: onPath({ terraform: '/usr/bin/terraform' }),
      probe: probes({ '/usr/bin/terraform': 'Terraform v1.4.6' }),
    });
    const f = failure(r);
    expect(f.reason).toBe('belowFloor');
    const msg = describeTofuFailure(f);
    expect(msg).toContain('terraform 1.4.6');
    expect(msg).toContain('1.5.0');
    expect(msg).toContain('rdc tools install tofu');
  });

  it('accepts terraform at exactly 1.5.0', async () => {
    const r = await resolveTofu({
      env: {},
      managedPath: MANAGED,
      findOnPath: onPath({ terraform: '/usr/bin/terraform' }),
      probe: probes({ '/usr/bin/terraform': 'Terraform v1.5.0' }),
    });
    expect(r.ok).toBe(true);
  });

  it('skips a tofu below 1.6 for a newer terraform further down', async () => {
    const r = await resolveTofu({
      env: {},
      managedPath: MANAGED,
      findOnPath: onPath({ tofu: '/usr/bin/tofu', terraform: '/usr/bin/terraform' }),
      probe: probes({
        '/usr/bin/tofu': 'OpenTofu v1.5.9',
        '/usr/bin/terraform': 'Terraform v1.6.0',
      }),
    });
    expect(r.ok && r.engine.engine).toBe('terraform');
  });

  it('refuses an explicit REDIACC_TOFU below the floor instead of falling through', async () => {
    const r = await resolveTofu({
      env: { REDIACC_TOFU: '/old/tofu' },
      managedPath: MANAGED,
      findOnPath: onPath({}),
      probe: probes({ '/old/tofu': 'OpenTofu v1.5.0', [MANAGED]: 'OpenTofu v1.10.6' }),
    });
    expect(failure(r).reason).toBe('belowFloor');
  });

  it('refuses a REDIACC_TOFU that does not run, naming it', async () => {
    const r = await resolveTofu({
      env: { REDIACC_TOFU: '/nope' },
      managedPath: MANAGED,
      findOnPath: onPath({}),
      probe: probes({ [MANAGED]: 'OpenTofu v1.10.6' }),
    });
    const f = failure(r);
    expect(f).toEqual({ ok: false, reason: 'overrideUnusable', path: '/nope' });
    expect(describeTofuFailure(f)).toMatch(/REDIACC_TOFU.*\/nope.*rdc tools install tofu/);
  });
});

describe('resolveTofu on Windows', () => {
  it('looks up the managed tofu.exe and PATH entries through PATHEXT', async () => {
    const seen: string[] = [];
    const r = await resolveTofu({
      env: { Path: 'C:\\bin', PATHEXT: '.EXE' },
      platform: 'win32',
      findOnPath: undefined,
      probe: (p) => {
        seen.push(p);
        return Promise.resolve(null);
      },
    });
    expect(r.ok).toBe(false);
    // The managed candidate is the .exe; PATH lookup found nothing in a C:\bin that does not exist.
    expect(seen[0]).toMatch(/opentofu[\\/][^\\/]+[\\/]tofu\.exe$/);
  });
});

describe.skipIf(process.platform === 'win32')('TofuExecutor against a fake engine', () => {
  const dirs: string[] = [];
  const saved = { ...process.env };
  afterEach(async () => {
    process.env = { ...saved };
    await Promise.all(dirs.splice(0).map((d) => rm(d, { recursive: true, force: true })));
  });

  it('runs the REDIACC_TOFU engine with TF_PLUGIN_CACHE_DIR set to a created shared cache', async () => {
    const root = await mkdtemp(join(tmpdir(), 'rdc-tofu-exec-'));
    dirs.push(root);
    const engine = join(root, 'tofu');
    const record = join(root, 'record.txt');
    await writeFile(
      engine,
      `#!/bin/sh\nif [ "$1" = version ]; then echo "OpenTofu v1.10.6"; exit 0; fi\necho "$1 $TF_PLUGIN_CACHE_DIR" > "${record}"\n`
    );
    await chmod(engine, 0o755);
    process.env.REDIACC_TOFU = engine;
    delete process.env.TF_PLUGIN_CACHE_DIR;

    const work = join(root, 'work');
    const exec = new TofuExecutor(work);
    await exec.writeConfig({});
    await exec.init();

    const cache = getPluginCacheDir();
    expect(await readFile(record, 'utf8')).toBe(`init ${cache}\n`);
    expect((await stat(cache)).isDirectory()).toBe(true);
    // The work dir and config keep their modes.
    expect((await stat(work)).mode & 0o777).toBe(0o700);
    expect((await stat(join(work, 'main.tf.json'))).mode & 0o777).toBe(0o600);
  });

  it('throws the i18n not-installed error when nothing is found', async () => {
    process.env.REDIACC_TOFU = '';
    process.env.PATH = '/nonexistent-rdc-test-path';
    await expect(TofuExecutor.resolveBinary()).rejects.toThrow(/rdc tools install tofu/);
    expect(await TofuExecutor.checkInstalled()).toBe(false);
  });
});
