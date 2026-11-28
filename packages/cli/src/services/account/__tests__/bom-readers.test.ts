/**
 * Every synchronous reader of a config-dir JSON file tolerates a UTF-8 byte
 * order mark (Windows PowerShell 5.1, older Notepad). Each case writes a
 * BOM-prefixed CRLF file and reads it through the real reader, so a reader
 * that goes back to a bare `JSON.parse` fails here.
 */
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { completeNames } from '../../../commands/completion.js';
import {
  readPreviewOverlay,
  readRealAccountServer,
  readRealReleasesBase,
} from '../../preview/state.js';
import { readAccountPointer } from '../account-pointer.js';
import { getSubscriptionTokenState } from '../subscription-auth.js';

const BOM = '﻿';

function writeBomJson(file: string, value: unknown): void {
  writeFileSync(file, `${BOM}${JSON.stringify(value, null, 2).replaceAll('\n', '\r\n')}`);
}

describe('config-dir readers with a byte order mark', () => {
  let configDir: string;

  beforeEach(() => {
    const home = mkdtempSync(path.join(tmpdir(), 'rdc-bom-readers-'));
    vi.stubEnv('XDG_CONFIG_HOME', home);
    vi.stubEnv('REDIACC_CONFIG', 'bom');
    vi.stubEnv('REDIACC_TOKEN', '');
    configDir = path.join(home, 'rediacc');
    mkdirSync(configDir, { recursive: true });
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('readAccountPointer reads the account section', () => {
    writeBomJson(path.join(configDir, 'bom.json'), {
      account: { accountServer: 'https://acct.example.test' },
    });
    expect(readAccountPointer('bom', configDir).accountServer).toBe('https://acct.example.test');
  });

  it('the subscription token reader reads the stored token', () => {
    writeBomJson(path.join(configDir, 'api-token-bom.json'), {
      token: 'tok',
      serverUrl: 'https://acct.example.test',
    });
    const state = getSubscriptionTokenState();
    expect(state.kind).toBe('ready');
    if (state.kind === 'ready') expect(state.token.token).toBe('tok');
  });

  it('the preview readers read the overlay and the real account section', () => {
    writeBomJson(path.join(configDir, 'bom.json'), {
      account: {
        accountServer: 'https://real.example.test',
        releasesUrl: 'https://rel.example.test/',
      },
      preview: {
        name: 'pv-aa-bb-cc',
        host: 'https://preview.example.test',
        enteredAt: '2026-01-01T00:00:00Z',
        channel: 'edge',
        previous: { cliVersion: '1.0.0', cliSha256: 'abc' },
      },
    });
    expect(readPreviewOverlay('bom', configDir)?.name).toBe('pv-aa-bb-cc');
    expect(readRealAccountServer('bom', configDir)).toBe('https://real.example.test');
    expect(readRealReleasesBase('bom', configDir)).toBe('https://rel.example.test/cli');
  });

  it('completion reads resource names', () => {
    writeBomJson(path.join(configDir, 'bom.json'), {
      resources: { machines: { alpha: {}, beta: {} } },
    });
    expect(completeNames({ kind: 'machine' })).toEqual(['alpha', 'beta']);
  });
});
