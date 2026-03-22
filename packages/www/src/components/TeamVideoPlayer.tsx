/**
 * TeamVideoPlayer — click-to-play video with dubbed audio sync and captions.
 * Generic component: accepts a member slug + video key from team-videos config.
 * Uses facade pattern: poster image + play button until user clicks.
 */

import type { FC } from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AUDIO_FALLBACK,
  AUDIO_LANGUAGES,
  getAudioPath,
  getCaptionPath,
  getMemberVideo,
} from '../config/team-videos';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';
import '../styles/team-video.css';

interface TeamVideoPlayerProps {
  member: string;
  videoKey: string;
  lang: string;
  size?: 'compact' | 'full';
  className?: string;
}

const VOLUME_KEY = 'team-video-volume';
const MUTED_KEY = 'team-video-muted';
const CC_KEY = 'team-video-cc-enabled';
const DEFAULT_VOLUME = 0.5;
const SYNC_INTERVAL_MS = 90;
const FALLBACK_AUDIO_LANG = 'en';

function readBoolean(key: string, fallback: boolean): boolean {
  if (typeof window === 'undefined') return fallback;
  const v = window.localStorage.getItem(key);
  if (v === '1' || v === 'true') return true;
  if (v === '0' || v === 'false') return false;
  return fallback;
}

function readVolume(): number {
  if (typeof window === 'undefined') return DEFAULT_VOLUME;
  const v = Number(window.localStorage.getItem(VOLUME_KEY));
  return Number.isFinite(v) && v >= 0 && v <= 1 ? v : DEFAULT_VOLUME;
}

function resolveAudioLang(lang: string): string {
  if ((AUDIO_LANGUAGES as readonly string[]).includes(lang)) return lang;
  return AUDIO_FALLBACK[lang] ?? FALLBACK_AUDIO_LANG;
}

function VolumeIcon({ muted }: { muted: boolean }) {
  if (muted) {
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true" className="tv-icon">
        <path d="M6 9H3v6h3l4 4V5L6 9zm12.7 3 2.3 2.3-1.4 1.4-2.3-2.3-2.3 2.3-1.4-1.4 2.3-2.3-2.3-2.3 1.4-1.4 2.3 2.3 2.3-2.3 1.4 1.4-2.3 2.3z" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="tv-icon">
      <path d="M6 9H3v6h3l4 4V5L6 9zm8.5 3c0-1.8-1-3.4-2.5-4.2v8.3c1.5-.8 2.5-2.3 2.5-4.1zm2.5 0c0 3-1.7 5.6-4.2 6.8l-.8-1.7c2-.9 3.3-2.9 3.3-5.1s-1.3-4.2-3.3-5.1l.8-1.7c2.5 1.2 4.2 3.9 4.2 6.8z" />
    </svg>
  );
}

function PlayIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="tv-icon">
      <path d="M8 5v14l11-7z" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="tv-icon">
      <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
    </svg>
  );
}

function FullscreenIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="tv-icon">
      <path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z" />
    </svg>
  );
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

const TeamVideoPlayer: FC<TeamVideoPlayerProps> = ({
  member,
  videoKey,
  lang,
  size = 'full',
  className,
}) => {
  const { t } = useTranslation(lang as Language);
  const video = getMemberVideo(member, videoKey);
  const videoRef = useRef<HTMLVideoElement>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const progressRef = useRef<HTMLDivElement>(null);
  const progressFillRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [facadeVisible, setFacadeVisible] = useState(true);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(video?.duration ?? 0);
  const [isMuted, setIsMuted] = useState(() => readBoolean(MUTED_KEY, false));
  const [volume, setVolume] = useState(readVolume);
  const [ccEnabled, setCcEnabled] = useState(() => readBoolean(CC_KEY, true));

  const audioLang = resolveAudioLang(lang);

  // Persist preferences
  useEffect(() => {
    window.localStorage.setItem(VOLUME_KEY, String(volume));
  }, [volume]);
  useEffect(() => {
    window.localStorage.setItem(MUTED_KEY, isMuted ? '1' : '0');
  }, [isMuted]);
  useEffect(() => {
    window.localStorage.setItem(CC_KEY, ccEnabled ? '1' : '0');
  }, [ccEnabled]);

  // Initialize audio element
  useEffect(() => {
    audioRef.current = new Audio();
    audioRef.current.preload = 'auto';
    return () => {
      audioRef.current?.pause();
      audioRef.current = null;
    };
  }, []);

  // Sync audio volume/muted
  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.muted = isMuted;
    audio.volume = volume;
  }, [isMuted, volume]);

  // 90ms sync polling: keep audio in sync with video
  useEffect(() => {
    const timer = window.setInterval(() => {
      const vid = videoRef.current;
      const audio = audioRef.current;
      if (!vid || !audio) return;

      setCurrentTime(vid.currentTime);

      const pct = vid.duration > 0 ? (vid.currentTime / vid.duration) * 100 : 0;
      if (progressFillRef.current) {
        progressFillRef.current.style.width = `${pct}%`;
      }

      if (Math.abs(vid.currentTime - audio.currentTime) > 0.3) {
        try {
          audio.currentTime = vid.currentTime;
        } catch {
          // ignore seek errors before metadata ready
        }
      }
    }, SYNC_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, []);

  const startPlayback = useCallback(() => {
    const vid = videoRef.current;
    const audio = audioRef.current;
    if (!vid || !video) return;

    setFacadeVisible(false);

    // Load audio dub
    if (audio) {
      const audioSrc = getAudioPath(member, videoKey, audioLang);
      audio.src = audioSrc;
      audio.load();
    }

    // Add captions track
    if (ccEnabled) {
      const existing = vid.querySelector('track');
      if (!existing) {
        const track = document.createElement('track');
        track.kind = 'captions';
        track.src = getCaptionPath(member, videoKey, lang);
        track.srclang = lang;
        track.default = true;
        vid.appendChild(track);
      }
    }

    vid
      .play()
      .then(() => {
        setIsPlaying(true);
        if (audio?.src) {
          const playAudio = () => {
            try {
              audio.currentTime = vid.currentTime;
            } catch {
              /* ignore */
            }
            void audio.play().catch(() => undefined);
          };
          if (audio.readyState >= 1) {
            playAudio();
          } else {
            audio.addEventListener('loadedmetadata', playAudio, { once: true });
          }
        }
      })
      .catch(() => undefined);
  }, [member, videoKey, lang, audioLang, ccEnabled, video]);

  const togglePlay = useCallback(() => {
    const vid = videoRef.current;
    const audio = audioRef.current;
    if (!vid) return;

    if (vid.paused) {
      vid
        .play()
        .then(() => {
          setIsPlaying(true);
          if (audio) void audio.play().catch(() => undefined);
        })
        .catch(() => undefined);
    } else {
      vid.pause();
      audio?.pause();
      setIsPlaying(false);
    }
  }, []);

  const handleVideoEnded = useCallback(() => {
    setIsPlaying(false);
    audioRef.current?.pause();
  }, []);

  const handleLoadedMetadata = useCallback(() => {
    const vid = videoRef.current;
    if (vid) setDuration(vid.duration);
  }, []);

  const handleProgressClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const vid = videoRef.current;
    const audio = audioRef.current;
    const bar = progressRef.current;
    if (!vid || !bar) return;

    const rect = bar.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const newTime = ratio * vid.duration;
    vid.currentTime = newTime;
    if (audio) {
      try {
        audio.currentTime = newTime;
      } catch {
        /* ignore */
      }
    }
    setCurrentTime(newTime);
    const pct = vid.duration > 0 ? (newTime / vid.duration) * 100 : 0;
    if (progressFillRef.current) {
      progressFillRef.current.style.width = `${pct}%`;
    }
  }, []);

  const toggleFullscreen = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => undefined);
    } else {
      el.requestFullscreen().catch(() => undefined);
    }
  }, []);

  // Toggle captions track mode
  useEffect(() => {
    const vid = videoRef.current;
    if (!vid) return;
    if (vid.textTracks.length > 0) {
      vid.textTracks[0].mode = ccEnabled ? 'showing' : 'hidden';
    }
  }, [ccEnabled]);

  if (!video) return null;

  return (
    <div
      ref={containerRef}
      className={`tv-player tv-player--${size}${className ? ` ${className}` : ''}`}
    >
      {facadeVisible && (
        <button
          type="button"
          className="tv-facade"
          onClick={startPlayback}
          aria-label={t('video.playVideo')}
          data-track="team-video-play-facade"
        >
          <img
            src={video.poster}
            alt=""
            className="tv-poster"
            loading={size === 'compact' ? 'eager' : 'lazy'}
            decoding="async"
          />
          <span className="tv-play-overlay">
            <svg viewBox="0 0 64 64" className="tv-play-btn-icon" aria-hidden="true">
              <circle cx="32" cy="32" r="30" fill="rgba(0,0,0,0.6)" />
              <path d="M26 20v24l18-12z" fill="#fff" />
            </svg>
            <span className="tv-duration-badge">{video.durationLabel}</span>
          </span>
        </button>
      )}

      <video
        ref={videoRef}
        src={video.src}
        poster={video.poster}
        preload="none"
        playsInline
        onEnded={handleVideoEnded}
        onLoadedMetadata={handleLoadedMetadata}
        className={`tv-video${facadeVisible ? ' tv-video--hidden' : ''}`}
      />

      {!facadeVisible && (
        <div className="tv-controls">
          <button
            type="button"
            className="tv-ctrl-btn"
            onClick={togglePlay}
            aria-label={isPlaying ? 'Pause' : 'Play'}
            data-track="team-video-toggle-play"
          >
            {isPlaying ? <PauseIcon /> : <PlayIcon />}
          </button>

          <div
            ref={progressRef}
            className="tv-progress"
            onClick={handleProgressClick}
            role="progressbar"
            aria-valuenow={Math.round(currentTime)}
            aria-valuemin={0}
            aria-valuemax={Math.round(duration)}
          >
            <div ref={progressFillRef} className="tv-progress-fill" />
          </div>

          <span className="tv-time">
            {formatTime(currentTime)} / {formatTime(duration)}
          </span>

          <span className="tv-audio-controls">
            <button
              type="button"
              className="tv-ctrl-btn"
              onClick={() => setIsMuted(!isMuted)}
              aria-label={isMuted ? 'Unmute' : 'Mute'}
              data-track="team-video-toggle-mute"
            >
              <VolumeIcon muted={isMuted} />
            </button>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={volume}
              onChange={(e) => setVolume(Number(e.currentTarget.value))}
              className="tv-volume-slider"
              aria-label={t('video.volume')}
            />
          </span>

          <button
            type="button"
            className={`tv-ctrl-btn tv-cc-btn${ccEnabled ? ' is-active' : ''}`}
            onClick={() => setCcEnabled(!ccEnabled)}
            aria-label={ccEnabled ? t('video.disableCaptions') : t('video.enableCaptions')}
            aria-pressed={ccEnabled}
            data-track="team-video-toggle-cc"
          >
            CC
          </button>

          <button
            type="button"
            className="tv-ctrl-btn"
            onClick={toggleFullscreen}
            aria-label={t('video.toggleFullscreen')}
            data-track="team-video-toggle-fullscreen"
          >
            <FullscreenIcon />
          </button>
        </div>
      )}
    </div>
  );
};

export default TeamVideoPlayer;
