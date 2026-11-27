/**
 * The temp known_hosts file the system ssh reads holds the pinned keys under
 * the host field of the endpoint it dials.
 *
 * A machine whose address changed (eu-bench's hostinger moved from its IPv4 to
 * its IPv6, 2026-11-27) kept its pinned keys under the old address, and OpenSSH
 * refused every connection with "No ED25519 host key is known for <new
 * address>" until `machine scan-keys`, while the ssh2 path (trust by key)
 * worked. `ssh-keygen -F` is OpenSSH's own known_hosts lookup, so it is the
 * oracle here: the old code wrote the lines verbatim and the lookup for the
 * dialed address found nothing.
 */

import { execFileSync } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { afterEach, describe, expect, it } from 'vitest';
import { createTempKnownHostsFile, removeTempKnownHostsFile } from '../knownHosts.js';

const ED25519 = 'AAAAC3NzaC1lZDI1NTE5AAAAIOc6d1X0xGOoKduhuDqMgbBDT+AvKI/mf7cfltmqwB06';
const RSA =
  'AAAAB3NzaC1yc2EAAAADAQABAAAAgQDMlPPsrWMIIZ7Xeoz3vRVnqzMCXUJFgclgSEyqSPV3WgEoIF+6ww8Ah+DVs2XR/pIQqNWAaSK+4f5oBByvL98VpUw3iWr/jBG0e0yWotO67K1YvTzOTM4HJxq5o6t4jz4IulJOyqqepBZX78uFGbgBFdsgSjMzDe7uZw2zMZ/PmQ==';
const OLD_V4 = '203.0.113.7';
const NEW_V6 = '2a02:4780:c:e9b5::1';
const PINNED = `${OLD_V4} ssh-ed25519 ${ED25519}\n${OLD_V4} ssh-rsa ${RSA} root@host`;

const files: string[] = [];
afterEach(async () => {
  for (const f of files.splice(0)) await removeTempKnownHostsFile(f);
});

async function write(knownHosts: string | undefined, host: string, port: number) {
  const path = await createTempKnownHostsFile(knownHosts, { host, port });
  files.push(path);
  return path;
}

/** OpenSSH's own lookup: the keys `ssh` would accept for this host field. */
function opensshKeysFor(path: string, hostField: string): string[] {
  let out: string;
  try {
    out = execFileSync('ssh-keygen', ['-F', hostField, '-f', path], { encoding: 'utf8' });
  } catch {
    return []; // ssh-keygen -F exits 1 when nothing matches
  }
  return out
    .split('\n')
    .filter((l) => l && !l.startsWith('#'))
    .map((l) => l.split(/\s+/).slice(1, 3).join(' '));
}

const hasSshKeygen = (() => {
  try {
    execFileSync('ssh-keygen', ['-?'], { stdio: 'ignore' });
    return true;
  } catch (e) {
    return (e as { status?: number }).status !== undefined;
  }
})();

describe('createTempKnownHostsFile writes the pins under the dialed host', () => {
  it('rewrites every pinned line to the bare host on port 22, keeping type and key', async () => {
    const path = await write(PINNED, NEW_V6, 22);
    expect(await readFile(path, 'utf8')).toBe(
      `${NEW_V6} ssh-ed25519 ${ED25519}\n${NEW_V6} ssh-rsa ${RSA}\n`
    );
  });

  it('uses [host]:port off port 22, and never double-brackets a bracketed IPv6', async () => {
    const path = await write(PINNED, `[${NEW_V6}]`, 2222);
    const text = await readFile(path, 'utf8');
    expect(text.split('\n')[0]).toBe(`[${NEW_V6}]:2222 ssh-ed25519 ${ED25519}`);
  });

  it('keeps a marker, drops comments and keyless lines, and adds no key', async () => {
    const path = await write(
      `# pinned 2026-11-01\n@revoked ${OLD_V4} ssh-rsa ${RSA}\nbroken-line\n${OLD_V4} ssh-ed25519 ${ED25519}`,
      'h.example',
      22
    );
    expect(await readFile(path, 'utf8')).toBe(
      `@revoked h.example ssh-rsa ${RSA}\nh.example ssh-ed25519 ${ED25519}\n`
    );
  });

  it('keeps @cert-authority as a marker on the dialed host, which is the only host the file serves', async () => {
    const path = await write(`@cert-authority *.example ssh-ed25519 ${ED25519}`, 'h.example', 22);
    expect(await readFile(path, 'utf8')).toBe(`@cert-authority h.example ssh-ed25519 ${ED25519}\n`);
  });

  it('has the OpenSSH oracle wherever CI runs, so its tests never skip there', () => {
    if (process.env.CI) expect(hasSshKeygen).toBe(true);
  });

  it('writes an empty file when nothing is pinned', async () => {
    expect(await readFile(await write(undefined, NEW_V6, 22), 'utf8')).toBe('');
    expect(await readFile(await write('  \n', NEW_V6, 22), 'utf8')).toBe('');
  });

  it.skipIf(!hasSshKeygen && !process.env.CI)(
    'OpenSSH finds exactly the pinned keys for the new address, and none for the old',
    async () => {
      const path = await write(PINNED, NEW_V6, 22);
      expect(new Set(opensshKeysFor(path, NEW_V6))).toEqual(
        new Set([`ssh-ed25519 ${ED25519}`, `ssh-rsa ${RSA}`])
      );
      // Strictness is unchanged: only the pinned keys are trusted, and only for the dialed host.
      expect(opensshKeysFor(path, OLD_V4)).toEqual([]);
      expect(opensshKeysFor(path, '198.51.100.1')).toEqual([]);
    }
  );

  it.skipIf(!hasSshKeygen && !process.env.CI)('OpenSSH finds the pins under [host]:port off port 22', async () => {
    const path = await write(PINNED, NEW_V6, 2222);
    expect(opensshKeysFor(path, `[${NEW_V6}]:2222`)).toHaveLength(2);
    expect(opensshKeysFor(path, NEW_V6)).toEqual([]);
  });
});
