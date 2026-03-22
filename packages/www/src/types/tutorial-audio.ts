import type { Language } from '../i18n/types';

export interface TutorialAudioEvent {
  id: string;
  markerIndex: number;
  at: number;
  textHash: string;
  audioSrc: string;
  duration?: number;
  wordTimings?: TutorialWordTiming[];
}

export interface TutorialWordTiming {
  startSec: number;
  endSec: number;
  startChar: number;
  endChar: number;
}

export interface TutorialAudioManifestDocument {
  cast: string;
  language: Language;
  version: 1;
  provider: 'qwen3-tts';
  modelId: string;
  audioFormat: 'mp3' | 'wav';
  sampleRateHz: number;
  voiceDesignPreset: string;
  transcriptHash: string;
  events: TutorialAudioEvent[];
}
