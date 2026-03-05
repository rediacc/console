import type { FC } from 'react';
import { useEffect, useState } from 'react';

const AUDIO_VOLUME_STORAGE_KEY = 'tutorial-audio-volume';
const AUDIO_MUTED_STORAGE_KEY = 'tutorial-audio-muted';
const AUDIO_CC_ENABLED_STORAGE_KEY = 'tutorial-audio-cc-enabled';
const DEFAULT_AUDIO_VOLUME = 0.5;
const SYNC_DEDUPE_OFFSET_SECONDS = 0.15;
const SYNC_DEDUPE_WINDOW_MS = 700;

export interface AudioSyncSnapshot {
  audioSrc: string;
  eventIndex: number;
  shouldPlayAudio: boolean;
  offset: number;
  at: number;
}

export interface AudioVolumeControlsProps {
  isAudioMuted: boolean;
  audioVolume: number;
  onToggleMuted: () => void;
  onVolumeChange: (volume: number) => void;
}

export interface AudioCcToggleProps {
  isCcEnabled: boolean;
  onToggleCc: () => void;
}

export function resetAudioTransientHandlers(audioEl: HTMLAudioElement): void {
  audioEl.oncanplay = null;
  audioEl.onloadedmetadata = null;
}

export function pauseAudioElement(audioEl: HTMLAudioElement): void {
  audioEl.pause();
  resetAudioTransientHandlers(audioEl);
}

export function shouldSkipDuplicateSync(
  lastSync: AudioSyncSnapshot | null,
  nextSync: Omit<AudioSyncSnapshot, 'at'>,
  now: number
): boolean {
  if (!lastSync) return false;
  return (
    lastSync.audioSrc === nextSync.audioSrc &&
    lastSync.eventIndex === nextSync.eventIndex &&
    lastSync.shouldPlayAudio === nextSync.shouldPlayAudio &&
    Math.abs(lastSync.offset - nextSync.offset) < SYNC_DEDUPE_OFFSET_SECONDS &&
    now - lastSync.at < SYNC_DEDUPE_WINDOW_MS
  );
}

export function logAudioSync(payload: {
  castKey: string;
  eventIndex: number;
  shouldPlayAudio: boolean;
  audioSrc: string;
  currentTime: number;
  eventStart: number;
  boundedOffset: number;
}): void {
  if (!import.meta.env.DEV) return;
  console.warn('[TutorialAudio] sync', payload);
}

export function applyAudioTargetState(params: {
  audioEl: HTMLAudioElement;
  boundedOffset: number;
  shouldPlayAudio: boolean;
  requestId: number;
  getCurrentRequestId: () => number;
}): void {
  const { audioEl, boundedOffset, shouldPlayAudio, requestId, getCurrentRequestId } = params;
  const apply = () => {
    if (requestId !== getCurrentRequestId()) return;
    try {
      audioEl.currentTime = boundedOffset;
    } catch {
      // Ignore seek errors while metadata is not available yet.
    }

    if (!shouldPlayAudio) {
      pauseAudioElement(audioEl);
      return;
    }

    void audioEl.play().catch(() => {
      audioEl.oncanplay = () => {
        audioEl.oncanplay = null;
        if (requestId !== getCurrentRequestId()) return;
        void audioEl.play().catch(() => undefined);
      };
    });
  };

  if (audioEl.readyState < 1) {
    audioEl.onloadedmetadata = () => {
      audioEl.onloadedmetadata = null;
      apply();
    };
    return;
  }

  apply();
}

export function useAudioPreferences() {
  const parseStoredBoolean = (value: string | null, fallback: boolean): boolean => {
    if (value === null) return fallback;
    const normalized = value.trim().toLowerCase();
    if (normalized === '1' || normalized === 'true') return true;
    if (normalized === '0' || normalized === 'false') return false;
    return fallback;
  };

  const [isAudioMuted, setIsAudioMuted] = useState(() => {
    if (typeof window === 'undefined') return false;
    return parseStoredBoolean(window.localStorage.getItem(AUDIO_MUTED_STORAGE_KEY), false);
  });
  const [isCcEnabled, setIsCcEnabled] = useState(() => {
    if (typeof window === 'undefined') return true;
    return parseStoredBoolean(window.localStorage.getItem(AUDIO_CC_ENABLED_STORAGE_KEY), true);
  });

  const [audioVolume, setAudioVolume] = useState(() => {
    if (typeof window === 'undefined') return DEFAULT_AUDIO_VOLUME;
    const storedRaw = window.localStorage.getItem(AUDIO_VOLUME_STORAGE_KEY);
    if (storedRaw === null) return DEFAULT_AUDIO_VOLUME;
    const storedVolume = Number(storedRaw);
    if (Number.isFinite(storedVolume) && storedVolume >= 0 && storedVolume <= 1)
      return storedVolume;
    return DEFAULT_AUDIO_VOLUME;
  });

  useEffect(() => {
    window.localStorage.setItem(AUDIO_VOLUME_STORAGE_KEY, String(audioVolume));
  }, [audioVolume]);

  useEffect(() => {
    window.localStorage.setItem(AUDIO_MUTED_STORAGE_KEY, isAudioMuted ? '1' : '0');
  }, [isAudioMuted]);

  useEffect(() => {
    window.localStorage.setItem(AUDIO_CC_ENABLED_STORAGE_KEY, isCcEnabled ? '1' : '0');
  }, [isCcEnabled]);

  return {
    isAudioMuted,
    isCcEnabled,
    audioVolume,
    setIsAudioMuted,
    setIsCcEnabled,
    setAudioVolume,
  };
}

function VolumeIcon({ muted }: { muted: boolean }) {
  if (muted) {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6 9H3v6h3l4 4V5L6 9zm12.7 3 2.3 2.3-1.4 1.4-2.3-2.3-2.3 2.3-1.4-1.4 2.3-2.3-2.3-2.3 1.4-1.4 2.3 2.3 2.3-2.3 1.4 1.4-2.3 2.3z" />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M6 9H3v6h3l4 4V5L6 9zm8.5 3c0-1.8-1-3.4-2.5-4.2v8.3c1.5-.8 2.5-2.3 2.5-4.1zm2.5 0c0 3-1.7 5.6-4.2 6.8l-.8-1.7c2-.9 3.3-2.9 3.3-5.1s-1.3-4.2-3.3-5.1l.8-1.7c2.5 1.2 4.2 3.9 4.2 6.8z" />
    </svg>
  );
}

export const AudioVolumeControls: FC<AudioVolumeControlsProps> = ({
  isAudioMuted,
  audioVolume,
  onToggleMuted,
  onVolumeChange,
}) => {
  return (
    <span className="terminal-player-audio-controls" aria-label="Transcript audio controls">
      <span className="terminal-player-audio-volume-wrap">
        <button
          type="button"
          className="terminal-player-audio-icon-btn terminal-player-audio-toggle"
          onClick={onToggleMuted}
          aria-label={isAudioMuted ? 'Unmute transcript audio' : 'Mute transcript audio'}
          data-track="tutorial-audio-toggle"
        >
          <VolumeIcon muted={isAudioMuted} />
        </button>
        <label className="terminal-player-audio-slider-wrap">
          <span className="sr-only">Transcript voice volume</span>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={audioVolume}
            onChange={(event) => onVolumeChange(Number(event.currentTarget.value))}
            aria-label="Transcript voice volume"
          />
        </label>
      </span>
    </span>
  );
};

export const AudioCcToggle: FC<AudioCcToggleProps> = ({ isCcEnabled, onToggleCc }) => {
  return (
    <span className="terminal-player-audio-controls" aria-label="Transcript subtitles controls">
      <button
        type="button"
        className={`terminal-player-audio-icon-btn terminal-player-audio-cc-btn${
          isCcEnabled ? ' is-active' : ''
        }`}
        onClick={onToggleCc}
        aria-label={isCcEnabled ? 'Disable subtitles' : 'Enable subtitles'}
        aria-pressed={isCcEnabled}
        data-track="tutorial-audio-cc-toggle"
      >
        CC
      </button>
    </span>
  );
};
