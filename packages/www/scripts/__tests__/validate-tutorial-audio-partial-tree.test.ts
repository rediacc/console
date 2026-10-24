import { spawnSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterAll, describe, expect, it } from 'vitest';

/**
 * The gate resolves every path from its own location, so each case copies it into a scratch tree with two tutorials (A and B) in one locale and symlinks the monorepo's node_modules for `@rediacc/locales`. The scenario is the one measured on 2026-10-24: a single tutorial's audio on disk, which used to make the gate demand every other tutorial's mp3s.
 */
const wwwRoot = fileURLToPath(new URL('../..', import.meta.url));
const source = path.join(wwwRoot, 'scripts', 'validate-tutorial-audio.js');
const scratch = fs.mkdtempSync(path.join(os.tmpdir(), 'audio-gate-'));
afterAll(() => fs.rmSync(scratch, { recursive: true, force: true }));

const EVENTS = [{ id: 'e1', markerIndex: 0, at: 0, text: 'Hello there' }];
const hash = (events: typeof EVENTS) =>
  crypto
    .createHash('sha256')
    .update(
      JSON.stringify(
        events.map((e) => ({ id: e.id, markerIndex: e.markerIndex, at: e.at, text: e.text }))
      )
    )
    .digest('hex');

function mkTree(): string {
  const root = fs.mkdtempSync(path.join(scratch, 'tree-'));
  fs.mkdirSync(path.join(root, 'scripts'), { recursive: true });
  fs.copyFileSync(source, path.join(root, 'scripts', 'validate-tutorial-audio.js'));
  fs.symlinkSync(path.join(wwwRoot, '..', '..', 'node_modules'), path.join(root, 'node_modules'));
  fs.writeFileSync(path.join(root, 'package.json'), '{"type":"module"}');
  for (const cast of ['A', 'B']) {
    const tdir = path.join(root, 'src', 'data', 'tutorial-transcripts', 'en');
    const ldir = path.join(root, 'src', 'data', 'tutorial-timeline', 'en');
    fs.mkdirSync(tdir, { recursive: true });
    fs.mkdirSync(ldir, { recursive: true });
    fs.writeFileSync(path.join(tdir, `${cast}.json`), JSON.stringify({ cast, events: EVENTS }));
    fs.writeFileSync(
      path.join(ldir, `${cast}.json`),
      JSON.stringify({
        version: 1,
        provider: 'voxcpm2',
        cast,
        language: 'en',
        transcriptHash: hash(EVENTS),
        steps: [
          {
            id: 'e1',
            markerIndex: 0,
            narrationText: 'Hello there',
            replayStartSec: 0,
            replayEndSec: 1,
            audioSrc: `/assets/tutorials/audio/en/${cast}/${cast}-01.mp3`,
          },
        ],
      })
    );
  }
  return root;
}

function putAudio(root: string, cast: string): string {
  const file = path.join(
    root,
    'public',
    'assets',
    'tutorials',
    'audio',
    'en',
    cast,
    `${cast}-01.mp3`
  );
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, 'x');
  return file;
}

const run = (root: string, ...args: string[]) =>
  spawnSync(process.execPath, [path.join(root, 'scripts', 'validate-tutorial-audio.js'), ...args], {
    cwd: root,
    encoding: 'utf8',
  });

describe('validate-tutorial-audio with a partial audio tree', () => {
  it('passes the default run when only tutorial A has audio, and says B was not checked', () => {
    const root = mkTree();
    putAudio(root, 'A');
    const res = run(root);
    expect(res.status, res.stdout + res.stderr).toBe(0);
    expect(res.stdout).toContain('Audio files not checked for 1 of 2 pair(s)');
  });

  it('CONTROL: a pair with SOME audio but a missing file still fails', () => {
    const root = mkTree();
    const keep = putAudio(root, 'A');
    // A second step whose mp3 does not exist: A has audio locally, so it is held to all of it.
    const timelinePath = path.join(root, 'src', 'data', 'tutorial-timeline', 'en', 'A.json');
    const timeline = JSON.parse(fs.readFileSync(timelinePath, 'utf8'));
    expect(fs.existsSync(keep)).toBe(true);
    timeline.steps.push({
      ...timeline.steps[0],
      id: 'e2',
      markerIndex: 1,
      audioSrc: '/assets/tutorials/audio/en/A/A-02.mp3',
    });
    const events = [...EVENTS, { id: 'e2', markerIndex: 1, at: 1, text: 'Hello there' }];
    timeline.transcriptHash = hash(events);
    timeline.steps[1].narrationText = 'Hello there';
    fs.writeFileSync(timelinePath, JSON.stringify(timeline));
    fs.writeFileSync(
      path.join(root, 'src', 'data', 'tutorial-transcripts', 'en', 'A.json'),
      JSON.stringify({ cast: 'A', events })
    );
    const res = run(root);
    expect(res.status).toBe(1);
    expect(res.stderr).toContain('A-02.mp3');
  });

  it('CONTROL: a selective run still demands every file of every pair it matched', () => {
    const root = mkTree();
    putAudio(root, 'A');
    const res = run(root, '--lang', 'en');
    expect(res.status).toBe(1);
    expect(res.stderr).toContain('B-01.mp3');
  });

  it('CONTROL: structure is still validated for a pair with no audio', () => {
    const root = mkTree();
    putAudio(root, 'A');
    const timelinePath = path.join(root, 'src', 'data', 'tutorial-timeline', 'en', 'B.json');
    const timeline = JSON.parse(fs.readFileSync(timelinePath, 'utf8'));
    timeline.transcriptHash = 'stale';
    fs.writeFileSync(timelinePath, JSON.stringify(timeline));
    const res = run(root);
    expect(res.status).toBe(1);
    expect(res.stderr).toContain('transcriptHash is stale');
  });
});
