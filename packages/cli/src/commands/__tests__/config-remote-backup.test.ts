import { promises as fs } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  nextPreEnableBackupName,
  preEnableBackupName,
  writePreEnableBackup,
} from '../config-remote-backup.js';

// Review 1121-1 41e31abd.1/.2: two enables inside one second take `-1`, `-2` names, the prompt names the file that will be written, and the 100-copy limit throws.
describe('pre-enable copy names', () => {
  const now = new Date('2026-11-25T10:00:00.000Z');
  let dir = '';
  let configPath = '';

  beforeEach(async () => {
    dir = await fs.mkdtemp(join(tmpdir(), 'rdc-preenable-'));
    configPath = join(dir, 'rediacc.json');
    await fs.writeFile(configPath, '{"a":1}');
  });

  afterEach(async () => {
    await fs.rm(dir, { recursive: true, force: true });
  });

  it('writes the plain name first, then a counter for every copy of the same second', async () => {
    const plain = preEnableBackupName(configPath, now);
    expect(plain).toMatch(/\.pre-enable\.20261125T100000Z\.bak$/);
    expect(await writePreEnableBackup(configPath, now)).toBe(plain);
    expect(await writePreEnableBackup(configPath, now)).toBe(plain.replace(/\.bak$/, '-1.bak'));
    expect(await writePreEnableBackup(configPath, now)).toBe(plain.replace(/\.bak$/, '-2.bak'));
  });

  it('names in the prompt the file the next write creates, counter included', async () => {
    const plain = preEnableBackupName(configPath, now);
    expect(await nextPreEnableBackupName(configPath, now)).toBe(plain);
    await writePreEnableBackup(configPath, now);
    const second = await nextPreEnableBackupName(configPath, now);
    expect(second).toBe(plain.replace(/\.bak$/, '-1.bak'));
    expect(await writePreEnableBackup(configPath, now)).toBe(second);
  });

  it('never overwrites a copy that exists', async () => {
    const plain = preEnableBackupName(configPath, now);
    await fs.writeFile(plain, 'older');
    const written = await writePreEnableBackup(configPath, now);
    expect(written).not.toBe(plain);
    expect(await fs.readFile(plain, 'utf8')).toBe('older');
  });

  it('throws after 100 copies in one second', async () => {
    for (let i = 0; i < 100; i++) await writePreEnableBackup(configPath, now);
    await expect(writePreEnableBackup(configPath, now)).rejects.toThrow(/Too many pre-enable/);
    await expect(nextPreEnableBackupName(configPath, now)).rejects.toThrow(/Too many pre-enable/);
  });

  it('returns null when the config file does not exist yet', async () => {
    await fs.rm(configPath);
    expect(await writePreEnableBackup(configPath, now)).toBeNull();
  });
});
