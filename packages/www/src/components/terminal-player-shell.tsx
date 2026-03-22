import type * as React from 'react';
import { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { AudioCcToggle, AudioVolumeControls } from './terminal-player-audio';
import {
  type CaptionSegment,
  ensureInlineCcHost,
  ensureInlinePlaybackHost,
  ensureInlineVolumeHost,
} from './terminal-player-utils';

export interface AsciinemaPlayerInstance {
  play(): Promise<void>;
  pause(): Promise<void>;
  seek(position: number | string | { marker: number | 'prev' | 'next' }): Promise<void>;
  dispose(): void;
  addEventListener(event: string, handler: (payload?: unknown) => void): void;
  getCurrentTime?(): Promise<number>;
}

export interface AsciinemaPlayerModule {
  create(src: string, el: Element, opts: Record<string, unknown>): AsciinemaPlayerInstance;
}

export type GuidedPhase = 'idle' | 'narrating' | 'replaying' | 'pausedByUser' | 'ended';

export function isPlayingPhase(phase: GuidedPhase): boolean {
  return phase === 'narrating' || phase === 'replaying';
}

function PlayGlyph() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M8 5v14l11-7z" />
    </svg>
  );
}

function PauseGlyph() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M6 5h4v14H6zM14 5h4v14h-4z" />
    </svg>
  );
}

function GuidedPlaybackToggle({ phase, onToggle }: { phase: GuidedPhase; onToggle: () => void }) {
  const isRunning = isPlayingPhase(phase);
  const label = isRunning ? 'Pause' : 'Play';

  return (
    <button
      type="button"
      className="terminal-player-guided-toggle"
      onClick={onToggle}
      aria-label={label}
      data-track="tutorial-guided-playback-toggle"
    >
      {isRunning ? <PauseGlyph /> : <PlayGlyph />}
      <span className="sr-only">{label}</span>
    </button>
  );
}

export function CaptionLayer({
  captionNodeClassName,
  transcriptLabel,
  segments,
  highlightedWord,
}: {
  captionNodeClassName: string;
  transcriptLabel: string;
  segments: CaptionSegment[];
  highlightedWord: number;
}) {
  return (
    <div className={captionNodeClassName} aria-label={transcriptLabel} aria-live="polite">
      <span className="terminal-player-caption-text">
        {segments.map((segment, index) =>
          segment.isWord ? (
            <span
              key={`w-${index}`}
              className={
                segment.index === highlightedWord
                  ? 'terminal-player-caption-word is-active'
                  : 'terminal-player-caption-word'
              }
            >
              {segment.text}
            </span>
          ) : (
            <span key={`g-${index}`}>{segment.text}</span>
          )
        )}
      </span>
    </div>
  );
}

export function TerminalPlayerView({
  rootClassName,
  wrapperRef,
  title,
  containerRef,
  captionNode,
  fullscreenCaptionHostEl,
  showControls,
  playbackHostEl,
  volumeHostEl,
  ccHostEl,
  guidedPhase,
  onToggleGuidedPlayback,
  isAudioMuted,
  audioVolume,
  isCcEnabled,
  setIsAudioMuted,
  setIsCcEnabled,
  setAudioVolume,
  guidedStep,
}: {
  rootClassName: string;
  wrapperRef: React.RefObject<HTMLDivElement | null>;
  title?: string;
  containerRef: React.RefObject<HTMLDivElement | null>;
  captionNode: React.ReactNode;
  fullscreenCaptionHostEl: HTMLElement | null;
  showControls: boolean;
  playbackHostEl: HTMLElement | null;
  volumeHostEl: HTMLElement | null;
  ccHostEl: HTMLElement | null;
  guidedPhase: GuidedPhase;
  onToggleGuidedPlayback: () => void;
  isAudioMuted: boolean;
  audioVolume: number;
  isCcEnabled: boolean;
  setIsAudioMuted: React.Dispatch<React.SetStateAction<boolean>>;
  setIsCcEnabled: React.Dispatch<React.SetStateAction<boolean>>;
  setAudioVolume: React.Dispatch<React.SetStateAction<number>>;
  guidedStep: number;
}) {
  const inlineCaptionNode = fullscreenCaptionHostEl ? null : captionNode;
  const fullscreenCaptionPortal =
    fullscreenCaptionHostEl && captionNode
      ? createPortal(captionNode, fullscreenCaptionHostEl)
      : null;

  const playbackPortal =
    showControls && playbackHostEl
      ? createPortal(
          <GuidedPlaybackToggle phase={guidedPhase} onToggle={onToggleGuidedPlayback} />,
          playbackHostEl
        )
      : null;

  const volumePortal =
    showControls && volumeHostEl
      ? createPortal(
          <AudioVolumeControls
            isAudioMuted={isAudioMuted}
            audioVolume={audioVolume}
            onToggleMuted={() => setIsAudioMuted((prev) => !prev)}
            onVolumeChange={setAudioVolume}
          />,
          volumeHostEl
        )
      : null;

  const ccPortal =
    showControls && ccHostEl
      ? createPortal(
          <AudioCcToggle
            isCcEnabled={isCcEnabled}
            onToggleCc={() => setIsCcEnabled((prev) => !prev)}
          />,
          ccHostEl
        )
      : null;

  return (
    <div
      className={rootClassName}
      ref={wrapperRef}
      data-guided-phase={guidedPhase}
      data-guided-step={String(guidedStep)}
    >
      {title && <div className="terminal-tutorial-header">{title}</div>}
      <div className="terminal-tutorial-layout">
        <div className="terminal-tutorial-player">
          <div ref={containerRef} className="terminal-tutorial-player-inner" />
          {inlineCaptionNode}
        </div>
      </div>
      {fullscreenCaptionPortal}
      {playbackPortal}
      {volumePortal}
      {ccPortal}
    </div>
  );
}

export function usePlayerSetup(params: {
  src: string;
  containerRef: React.RefObject<HTMLDivElement | null>;
  playerRef: React.RefObject<AsciinemaPlayerInstance | null>;
  asciinemaModuleRef: React.RefObject<AsciinemaPlayerModule | null>;
  setPlaybackHostEl: React.Dispatch<React.SetStateAction<HTMLElement | null>>;
  setVolumeHostEl: React.Dispatch<React.SetStateAction<HTMLElement | null>>;
  setCcHostEl: React.Dispatch<React.SetStateAction<HTMLElement | null>>;
  onPlayerSeeked: () => void;
  onPlayerPlay: () => void;
}): void {
  const {
    src,
    containerRef,
    playerRef,
    asciinemaModuleRef,
    setPlaybackHostEl,
    setVolumeHostEl,
    setCcHostEl,
    onPlayerSeeked,
    onPlayerPlay,
  } = params;

  useEffect(() => {
    const controller = new AbortController();
    let retryTimer: number | null = null;

    const attachHosts = () => {
      const container = containerRef.current;
      if (!container || controller.signal.aborted) return;
      const playHost = ensureInlinePlaybackHost(container);
      const volumeHost = ensureInlineVolumeHost(container);
      const ccHost = ensureInlineCcHost(container);
      if (playHost) setPlaybackHostEl(playHost);
      if (volumeHost) setVolumeHostEl(volumeHost);
      if (ccHost) setCcHostEl(ccHost);
      if (!playHost || !volumeHost || !ccHost) retryTimer = window.setTimeout(attachHosts, 120);
    };

    const createPlayer = async () => {
      const container = containerRef.current;
      if (!container) return;

      if (!asciinemaModuleRef.current) {
        const AsciinemaPlayer = (await import(
          'asciinema-player'
        )) as unknown as AsciinemaPlayerModule;
        await import('asciinema-player/dist/bundle/asciinema-player.css');
        asciinemaModuleRef.current = AsciinemaPlayer;
      }

      playerRef.current?.dispose();
      playerRef.current = asciinemaModuleRef.current.create(src, container, {
        cols: 100,
        rows: 30,
        autoPlay: false,
        loop: false,
        preload: true,
        fit: 'width',
        pauseOnMarkers: false,
        theme: 'asciinema',
        terminalFontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
        terminalFontSize: '13px',
      });

      const player = playerRef.current;
      player.addEventListener('seeked', () => {
        if (!controller.signal.aborted) onPlayerSeeked();
      });
      player.addEventListener('play', () => {
        if (!controller.signal.aborted) onPlayerPlay();
      });

      attachHosts();
    };

    void createPlayer();

    return () => {
      controller.abort();
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      setPlaybackHostEl(null);
      setVolumeHostEl(null);
      setCcHostEl(null);
      playerRef.current?.dispose();
      playerRef.current = null;
    };
  }, [
    asciinemaModuleRef,
    containerRef,
    onPlayerPlay,
    onPlayerSeeked,
    playerRef,
    setCcHostEl,
    setPlaybackHostEl,
    setVolumeHostEl,
    src,
  ]);
}
