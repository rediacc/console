import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import { chmod, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { homedir, tmpdir } from 'node:os';
import { join } from 'node:path';
import { promisify } from 'node:util';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { OPENTOFU_PIN } from '../../tools/opentofu-pin.generated.js';
import { TofuExecutor } from '../executor.js';
import { PROVIDER_LOCK_HOST, PROVIDER_PINS, type ProviderPin } from '../provider-pins.generated.js';
import providerRegistry from '../provider-registry.json' with { type: 'json' };
import { generateProviderLock, generateTfJson } from '../tf-generator.js';

const run = promisify(execFile);
const registry = providerRegistry as Record<string, { version?: string }>;
const pinned = Object.entries(registry).filter(([source]) => source.includes('/'));

describe('provider pins', () => {
  it('pins every registry provider at an exact version equal to its lock block', () => {
    expect(pinned.length).toBeGreaterThan(0);
    for (const [source, entry] of pinned) {
      const pin = PROVIDER_PINS[source];
      expect(pin, source).toBeDefined();
      expect(entry.version, source).toMatch(/^\d+\.\d+\.\d+$/);
      expect(pin.version, source).toBe(entry.version);
      expect(pin.lock, source).toContain(
        `provider "${PROVIDER_LOCK_HOST}/${source.toLowerCase()}" {\n  version     = "${pin.version}"\n`
      );
      expect(pin.lock, source).toMatch(/"h1:[A-Za-z0-9+/=]{44}"/);
      expect(pin.lock, source).toMatch(/"zh:[0-9a-f]{64}"/);
    }
    expect(new Set(Object.keys(PROVIDER_PINS))).toEqual(new Set(pinned.map(([s]) => s)));
  });

  it('generates main.tf.json with the exact pinned version, so init cannot pick another build', () => {
    const tf = generateTfJson({
      machineName: 'm1',
      mapping: { ...(registry['linode/linode'] as never), source: 'linode/linode' },
      apiToken: 't',
      sshPublicKey: 'ssh-ed25519 AAAA',
    }) as { terraform: { required_providers: Record<string, { version: string }> } };
    expect(tf.terraform.required_providers.linode.version).toBe(
      PROVIDER_PINS['linode/linode'].version
    );
  });

  it('writes the lock blocks of the pinned providers a config requires, from the generated constants', () => {
    const lock = generateProviderLock({
      linode: { source: 'linode/linode', version: PROVIDER_PINS['linode/linode'].version },
      hcloud: {
        source: 'hetznercloud/hcloud',
        version: PROVIDER_PINS['hetznercloud/hcloud'].version,
      },
    });
    expect(lock).toBe(
      '# This file is maintained automatically by "tofu init".\n' +
        '# Manual edits may be lost in future updates.\n\n' +
        `${PROVIDER_PINS['hetznercloud/hcloud'].lock}\n\n${PROVIDER_PINS['linode/linode'].lock}\n`
    );
  });

  it('leaves an unpinned provider, or a pinned one asked at another version, to tofu', () => {
    expect(generateProviderLock({ x: { source: 'example/custom', version: '1.0.0' } })).toBeNull();
    expect(
      generateProviderLock({ linode: { source: 'linode/linode', version: '~> 3.0' } })
    ).toBeNull();
    expect(
      generateProviderLock({ linode: { source: `${PROVIDER_LOCK_HOST}/linode/linode` } })
    ).toContain(PROVIDER_PINS['linode/linode'].lock);
  });
});

// ---- the real engine: tofu init against a local filesystem mirror, offline ----------------

/** The pinned OpenTofu `rdc tools install tofu` placed for the developer, or REDIACC_TOFU. */
function realTofu(): string | null {
  if (process.env.REDIACC_TOFU) return process.env.REDIACC_TOFU;
  const p = join(homedir(), '.local/state/rediacc/tools/opentofu', OPENTOFU_PIN.version, 'tofu');
  return existsSync(p) ? p : null;
}

const TOFU = process.platform === 'win32' ? null : realTofu();
const PLATFORM = `${process.platform === 'darwin' ? 'darwin' : 'linux'}_${process.arch === 'arm64' ? 'arm64' : 'amd64'}`;
const FAKE = 'rediacc/fake';
const FAKE_VERSION = '1.0.0';

/** Flip one character of the first h1: hash in a lock block. */
const tamper = (lock: string): string =>
  lock.replace(/"h1:(.)/, (_m, c: string) => `"h1:${c === 'A' ? 'B' : 'A'}`);

// CI must not skip the core guarantee: without a tofu binary the suite fails there.
describe.skipIf(TOFU === null && process.env.CI !== 'true')(
  'tofu init refuses a provider whose hash the pin does not list',
  () => {
    let root: string;
    let pin: ProviderPin;
    const saved: Record<string, string | undefined> = {};

    it('has a tofu binary to run against (required when CI=true)', () => {
      expect(
        TOFU,
        'no pinned tofu: run `rdc tools install tofu` or set REDIACC_TOFU'
      ).not.toBeNull();
    });

    beforeEach(async () => {
      root = await mkdtemp(join(tmpdir(), 'tofu-lock-'));
      // An unpacked provider in a filesystem mirror: init installs from it with no network.
      const mirror = join(root, 'mirror');
      const pkg = join(mirror, PROVIDER_LOCK_HOST, FAKE, FAKE_VERSION, PLATFORM);
      await mkdir(pkg, { recursive: true });
      await writeFile(join(pkg, `terraform-provider-fake_v${FAKE_VERSION}`), '#!/bin/sh\nexit 1\n');
      await chmod(join(pkg, `terraform-provider-fake_v${FAKE_VERSION}`), 0o755);
      const cliConfig = join(root, 'tofurc');
      await writeFile(
        cliConfig,
        `provider_installation {\n  filesystem_mirror {\n    path = "${mirror}"\n  }\n}\n`
      );
      for (const k of ['REDIACC_TOFU', 'TF_CLI_CONFIG_FILE', 'TF_PLUGIN_CACHE_DIR'])
        saved[k] = process.env[k];
      process.env.REDIACC_TOFU = TOFU as string;
      process.env.TF_CLI_CONFIG_FILE = cliConfig;
      process.env.TF_PLUGIN_CACHE_DIR = join(root, 'plugin-cache');
      await mkdir(process.env.TF_PLUGIN_CACHE_DIR);

      // The pin's lock block, as `tofu providers lock` computes it from the mirror.
      const lockDir = join(root, 'lock');
      await mkdir(lockDir);
      await writeFile(
        join(lockDir, 'main.tf.json'),
        JSON.stringify({
          terraform: { required_providers: { fake: { source: FAKE, version: FAKE_VERSION } } },
        })
      );
      await run(
        TOFU as string,
        ['providers', 'lock', `-fs-mirror=${mirror}`, `-platform=${PLATFORM}`],
        { cwd: lockDir, env: process.env }
      );
      const block = /^provider "[^"]+" \{\n[^}]*\n\}$/m.exec(
        await readFile(join(lockDir, '.terraform.lock.hcl'), 'utf8')
      )?.[0];
      expect(block).toContain('"h1:');
      pin = { version: FAKE_VERSION, lock: block as string };
    });

    afterEach(async () => {
      for (const [k, v] of Object.entries(saved)) {
        if (v === undefined) delete process.env[k];
        else process.env[k] = v;
      }
      await rm(root, { recursive: true, force: true });
    });

    const config = {
      terraform: { required_providers: { fake: { source: FAKE, version: FAKE_VERSION } } },
    };

    async function initWith(pins: Record<string, ProviderPin>, work: string) {
      const exec = new TofuExecutor(work, pins);
      await exec.writeConfig(config);
      let stderr = '';
      const result = await exec
        .init({ onStderr: (d) => (stderr += d) })
        .then(() => 'ok' as const)
        .catch((e: Error) => e.message);
      return { result, stderr };
    }

    it('installs the provider when the lock written before init carries its hash', async () => {
      const work = join(root, 'ok');
      // A tampered lock left in the work dir is replaced by the pinned one before init.
      await mkdir(work, { recursive: true });
      await writeFile(join(work, '.terraform.lock.hcl'), tamper(pin.lock));
      const { result, stderr } = await initWith({ [FAKE]: pin }, work);
      expect(stderr).toBe('');
      expect(result).toBe('ok');
      expect(await readFile(join(work, '.terraform.lock.hcl'), 'utf8')).toBe(
        generateProviderLock(config.terraform.required_providers, { [FAKE]: pin })
      );
    });

    it('leaves an existing lock to tofu when no pinned provider applies, and refuses a missing main.tf.json', async () => {
      const work = join(root, 'nopin');
      await mkdir(work, { recursive: true });
      await writeFile(join(work, '.terraform.lock.hcl'), '# kept\n');
      const exec = new TofuExecutor(work, {});
      await exec.writeConfig({ terraform: { required_providers: {} } });
      await exec.init().catch(() => undefined);
      expect(await readFile(join(work, '.terraform.lock.hcl'), 'utf8')).toBe('# kept\n');
      // No main.tf.json: init refuses by name, since tofu init would pass on an empty directory.
      const empty = join(root, 'empty');
      await mkdir(empty, { recursive: true });
      await expect(new TofuExecutor(empty, {}).init()).rejects.toThrow(
        'No tofu configuration (main.tf.json)'
      );
    });

    it('fails init when the pinned lock carries a changed hash', async () => {
      const { result, stderr } = await initWith(
        { [FAKE]: { ...pin, lock: tamper(pin.lock) } },
        join(root, 'bad')
      );
      expect(result).not.toBe('ok');
      // tofu wraps and colours its diagnostics; compare the words.
      const ansi = new RegExp(`${String.fromCharCode(27)}\\[[0-9;]*m`, 'g');
      const words = stderr.replace(ansi, '').replace(/[│\s]+/g, ' ');
      expect(words).toContain(
        "doesn't match any of the checksums previously recorded in the dependency lock file"
      );
    });
  }
);
