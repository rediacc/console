import type { Language } from '../i18n/types';

export interface TutorialWordTiming {
  startSec: number;
  endSec: number;
  startChar: number;
  endChar: number;
}

export interface TutorialTimelineStep {
  id: string;
  markerIndex: number;
  replayStartSec: number;
  replayEndSec: number;
  narrationText: string;
  audioSrc: string;
  audioDurationSec?: number;
  wordTimings?: TutorialWordTiming[];
  dwellMs?: number;
}

export interface TutorialTimelineDocument {
  cast: string;
  language: Language;
  version: 1;
  provider: 'qwen3-tts';
  modelId: string;
  audioFormat: 'mp3' | 'wav';
  sampleRateHz: number;
  voiceDesignPreset: string;
  transcriptHash: string;
  steps: TutorialTimelineStep[];
}
