/**
 * The three defects the live CL1 install run found: `--image-file` shipped no manifest, a failing
 * inner step hid its stderr, and the install help never named `--accept-terms`.
 */

import { readFileSync } from 'node:fs';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn(), print: vi.fn() },
}));

import { WK_IMAGE_REGISTRY } from '@rediacc/shared/config/well-known.generated';
import { rdcMust, stderrTail } from '../box.js';
import { imageListText } from '../bundle/manifest.js';
import { placeImage } from '../common.js';
import { makeFake } from './fakes.js';

const REF = `${WK_IMAGE_REGISTRY}/server:1.2`;
const WHERE = { repo: 'elite', machine: 'box1', dockerSocket: '/var/run/x.sock' } as never;

describe('--image-file manifest', () => {
  it('ships images/manifest.txt with the same text a bundle writes', async () => {
    const fake = makeFake({});
    await placeImage(fake.deps, WHERE, REF, '/srv/server.tar');
    const uploads = fake.calls.filter((c) => c.startsWith('rdc repo sync upload'));
    expect(uploads).toHaveLength(2);
    expect(uploads[1]).toContain('--remote-file images/manifest.txt');
    const local = /--local (\S+)/.exec(uploads[1])?.[1] ?? '';
    expect(fake.files[local]).toBe(
      imageListText([{ file: 'images/server.tar', ref: REF, digest: '', sha256: '' }])
    );
    expect(fake.files[local]).toBe(`server.tar ${REF}\n`);
  });
});

describe('a failing inner step', () => {
  it('names the tail of its stderr and masks secrets', async () => {
    const fake = makeFake({
      rdcFail: 'repo create',
      rdcStderr:
        'noise\nTerms of Service not accepted\nwrite failed: No space left on device\npassword=hunter2',
    });
    const error = await rdcMust(fake.deps, ['repo', 'create', 'elite']).catch((e: Error) => e);
    expect((error as Error).message).toContain('No space left on device');
    expect((error as Error).message).toContain('Terms of Service not accepted');
    expect((error as Error).message).not.toContain('hunter2');
  });

  it('keeps the bare message when stderr is empty, and bounds a long one', () => {
    expect(stderrTail('')).toBe('');
    expect(stderrTail('x'.repeat(5000)).length).toBeLessThan(700);
  });
});

describe('install help', () => {
  const en = JSON.parse(
    readFileSync(new URL('../../../i18n/locales/en/cli.json', import.meta.url), 'utf-8')
  );
  it('names --accept-terms', () => {
    expect(en.commands.server.install.help).toContain('--accept-terms');
    expect(en.commands.server.install.termsHint).toContain('--accept-terms');
  });
});
