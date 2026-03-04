import type { Language } from '../i18n/types';

export interface TutorialTranscriptEvent {
  id: string;
  markerIndex: number;
  at: number;
  text: string;
}

export interface TutorialTranscriptDocument {
  cast: string;
  language: Language;
  version: 1;
  events: TutorialTranscriptEvent[];
}
