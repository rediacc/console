/**
 * editor-launcher tests — git-compatible resolution order, --wait injection,
 * headless refusal.
 */

import { execFileSync as _execFileSync } from 'node:child_process';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Mock `execFileSync` so tests don't depend on the host's git config.
vi.mock('node:child_process', async () => {
  const actual = await vi.importActual<typeof import('node:child_process')>('node:child_process');
  return {
    ...actual,
    execFileSync: vi.fn(),
  };
});

const mockedExecFileSync = vi.mocked(_execFileSync);

import { EditorError, resolveEditor } from '../editor-launcher.js';

describe('resolveEditor', () => {
  let prev: Record<string, string | undefined>;

  beforeEach(() => {
    prev = {
      VISUAL: process.env.VISUAL,
      EDITOR: process.env.EDITOR,
      GIT_EDITOR: process.env.GIT_EDITOR,
    };
    delete process.env.VISUAL;
    delete process.env.EDITOR;
    delete process.env.GIT_EDITOR;
    // Default: git config returns nothing (simulates "no core.editor set").
    mockedExecFileSync.mockReturnValue('' as unknown as Buffer);
  });

  afterEach(() => {
    for (const [k, v] of Object.entries(prev)) {
      if (v === undefined) delete process.env[k];
      else process.env[k] = v;
    }
    vi.clearAllMocks();
  });

  it('respects explicit --editor arg (highest priority)', () => {
    process.env.GIT_EDITOR = 'git-ed';
    process.env.VISUAL = 'vim';
    process.env.EDITOR = 'nano';
    mockedExecFileSync.mockReturnValue('core-ed' as unknown as Buffer);
    const r = resolveEditor('/usr/bin/nano');
    expect(r.command).toBe('/usr/bin/nano');
    expect(r.args).toEqual([]);
  });

  it('prefers $GIT_EDITOR over git config and over $VISUAL / $EDITOR', () => {
    process.env.GIT_EDITOR = 'git-ed';
    process.env.VISUAL = 'vim';
    process.env.EDITOR = 'nano';
    mockedExecFileSync.mockReturnValue('core-ed' as unknown as Buffer);
    expect(resolveEditor().command).toBe('git-ed');
  });

  it('prefers git config core.editor over $VISUAL / $EDITOR when $GIT_EDITOR unset', () => {
    process.env.VISUAL = 'vim';
    process.env.EDITOR = 'nano';
    mockedExecFileSync.mockReturnValue('core-ed\n' as unknown as Buffer);
    expect(resolveEditor().command).toBe('core-ed');
  });

  it('falls through to $VISUAL when git config returns empty string', () => {
    process.env.VISUAL = 'vim';
    process.env.EDITOR = 'nano';
    mockedExecFileSync.mockReturnValue('' as unknown as Buffer);
    expect(resolveEditor().command).toBe('vim');
  });

  it('falls through to $EDITOR when git config missing and $VISUAL unset', () => {
    process.env.EDITOR = 'nano';
    mockedExecFileSync.mockImplementation(() => {
      throw new Error('git not installed');
    });
    expect(resolveEditor().command).toBe('nano');
  });

  it('ignores git errors silently (git missing, not a repo, slow helper)', () => {
    mockedExecFileSync.mockImplementation(() => {
      throw new Error('command not found: git');
    });
    process.env.EDITOR = 'fallback';
    expect(resolveEditor().command).toBe('fallback');
  });

  it('injects --wait for known GUI editors', () => {
    expect(resolveEditor('code').args).toEqual(['--wait']);
    expect(resolveEditor('cursor').args).toEqual(['--wait']);
    expect(resolveEditor('subl').args).toEqual(['--wait']);
  });

  it('does not inject --wait if already present', () => {
    expect(resolveEditor('code --wait').args).toEqual(['--wait']);
  });

  it('falls back to platform default when nothing set', () => {
    mockedExecFileSync.mockReturnValue('' as unknown as Buffer);
    const r = resolveEditor();
    if (process.platform === 'win32') {
      expect(r.command).toBe('notepad.exe');
      expect(r.args).toContain('/W');
    } else {
      expect(r.command).toBe('nano');
    }
  });

  it('refuses headless invocations', () => {
    expect(() => resolveEditor('nvim --headless')).toThrow(EditorError);
    expect(() => resolveEditor('vim --batch')).toThrow(EditorError);
  });

  it('preserves caller args', () => {
    const r = resolveEditor('code --disable-extensions --new-window');
    expect(r.args).toContain('--disable-extensions');
    expect(r.args).toContain('--new-window');
    expect(r.args).toContain('--wait');
  });

  it('honors git config even when the value has trailing whitespace/newlines', () => {
    mockedExecFileSync.mockReturnValue('emacs -nw\n\n' as unknown as Buffer);
    expect(resolveEditor().command).toBe('emacs');
  });
});
