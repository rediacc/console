/**
 * A config or token file saved by Windows PowerShell 5.1 or an older Notepad
 * starts with a UTF-8 byte order mark (EF BB BF) and uses CRLF line endings.
 * The CLI reads it; its own writes stay BOM-free.
 */
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { parseJsonText, stripBom } from '../../utils/json-text.js';
import { ConfigFileStorage } from '../config-file-storage.js';
import { RemoteTokenStorage } from '../remote-token-storage.js';

const BOM = '﻿';

describe('json-text', () => {
  it('strips exactly one leading BOM', () => {
    expect(stripBom(`${BOM}{}`)).toBe('{}');
    expect(stripBom(`${BOM}${BOM}{}`)).toBe(`${BOM}{}`);
    expect(stripBom('{}')).toBe('{}');
    expect(parseJsonText(`${BOM}{\r\n  "a": 1\r\n}`)).toEqual({ a: 1 });
  });
});

describe('config file with a byte order mark and CRLF line endings', () => {
  it('loads, and the next write carries no BOM', async () => {
    const dir = mkdtempSync(path.join(tmpdir(), 'rdc-bom-'));
    const storage = new ConfigFileStorage(dir);
    await storage.save(await storage.load('bom'), 'bom');
    const file = path.join(dir, 'bom.json');
    const original = readFileSync(file, 'utf8');
    expect(original.startsWith(BOM)).toBe(false);

    const crlf = original.replaceAll('\n', '\r\n');
    writeFileSync(file, Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), Buffer.from(crlf)]));
    const reloaded = await new ConfigFileStorage(dir).load('bom');
    expect(reloaded.id).toBe(JSON.parse(original).id);

    await new ConfigFileStorage(dir).save(reloaded, 'bom');
    expect(readFileSync(file, 'utf8').startsWith(BOM)).toBe(false);
  });
});

describe('token file with a byte order mark', () => {
  it('reads', async () => {
    const dir = mkdtempSync(path.join(tmpdir(), 'rdc-bom-token-'));
    const storage = new RemoteTokenStorage(dir);
    await storage.set('eu', { token: 'tok', wrappedCek: 'cek' });
    const file = readdirTokenFile(dir);
    writeFileSync(file, `${BOM}${readFileSync(file, 'utf8').replaceAll('\n', '\r\n')}`);
    expect((await storage.get('eu'))?.token).toBe('tok');
  });
});

function readdirTokenFile(dir: string): string {
  return path.join(dir, 'eu.json');
}
