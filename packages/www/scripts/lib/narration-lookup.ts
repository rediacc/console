import { readFileSync } from 'node:fs';
import path from 'node:path';

export interface NarrationEntry {
  id: string;
  audioSrc: string;
  audioDurationSec?: number;
  narrationText?: string;
}

interface Timeline {
  steps?: Array<{
    id: string;
    audioSrc: string;
    audioDurationSec?: number;
    narrationText?: string;
    afterAudioSrc?: string;
    afterAudioDurationSec?: number;
  }>;
  narrationAudio?: NarrationEntry[];
}

export interface AfterAudioEntry {
  audioSrc: string;
  audioDurationSec: number;
}

export interface NarrationLookup {
  get(key: string): NarrationEntry;
  getAfter(stepId: string): AfterAudioEntry | null;
  resolvePath(audioSrc: string): string;
}

export function loadNarrationLookup(timelinePath: string, wwwPublicRoot: string): NarrationLookup {
  const t = JSON.parse(readFileSync(timelinePath, 'utf8')) as Timeline;
  const byId = new Map<string, NarrationEntry>();
  const afterById = new Map<string, AfterAudioEntry>();
  for (const s of t.steps ?? []) {
    byId.set(s.id, {
      id: s.id,
      audioSrc: s.audioSrc,
      audioDurationSec: s.audioDurationSec,
      narrationText: s.narrationText,
    });
    if (typeof s.afterAudioSrc === 'string' && typeof s.afterAudioDurationSec === 'number') {
      afterById.set(s.id, { audioSrc: s.afterAudioSrc, audioDurationSec: s.afterAudioDurationSec });
    }
  }
  for (const n of t.narrationAudio ?? []) {
    byId.set(n.id, n);
  }
  return {
    get(key: string): NarrationEntry {
      const entry = byId.get(key);
      if (!entry)
        throw new Error(`Narration lookup miss for key "${key}". Run TTS generate first.`);
      if (!entry.audioDurationSec)
        throw new Error(`Narration "${key}" has no audioDurationSec (re-run TTS).`);
      return entry;
    },
    getAfter(stepId: string): AfterAudioEntry | null {
      return afterById.get(stepId) ?? null;
    },
    resolvePath(audioSrc: string): string {
      return path.join(wwwPublicRoot, audioSrc.replace(/^\//, ''));
    },
  };
}

export function castMarkerKey(markerIndex: number, timelinePath: string): string {
  const t = JSON.parse(readFileSync(timelinePath, 'utf8')) as Timeline;
  const step = (t.steps ?? []).find(
    (s) => Number((s as { markerIndex?: number }).markerIndex) === markerIndex
  );
  if (!step) throw new Error(`No timeline step for markerIndex=${markerIndex} in ${timelinePath}`);
  return step.id;
}
