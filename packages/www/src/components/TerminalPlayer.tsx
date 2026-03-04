/**
 * TerminalPlayer — Interactive asciinema-player for tutorial recordings.
 *
 * Renders a .cast file with asciinema-player and synchronized transcripts.
 */

import type { FC } from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { loadTranscript } from '../utils/tutorial-transcripts';

interface AsciinemaPlayerInstance {
  play(): Promise<void>;
  pause(): Promise<void>;
  dispose(): void;
  addEventListener(event: string, handler: (payload?: unknown) => void): void;
  seek?(time: number): Promise<void>;
  getCurrentTime?(): Promise<number>;
}

interface AsciinemaPlayerModule {
  create(src: string, el: Element, opts: Record<string, unknown>): AsciinemaPlayerInstance;
}

interface TerminalPlayerProps {
  src: string;
  title?: string;
  lang?: string;
  castKey?: string;
}

const transcriptLabels: Record<string, { transcript: string; step: string }> = {
  en: { transcript: 'Transcript', step: 'Step' },
  de: { transcript: 'Transkript', step: 'Schritt' },
  es: { transcript: 'Transcripción', step: 'Paso' },
  fr: { transcript: 'Transcription', step: 'Étape' },
  ja: { transcript: '文字起こし', step: 'ステップ' },
  ar: { transcript: 'النص', step: 'الخطوة' },
  ru: { transcript: 'Транскрипт', step: 'Шаг' },
  tr: { transcript: 'Transkript', step: 'Adım' },
  zh: { transcript: '文字稿', step: '步骤' },
};

const TerminalPlayer: FC<TerminalPlayerProps> = ({ src, title, lang = 'en', castKey }) => {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<AsciinemaPlayerInstance | null>(null);
  const asciinemaModuleRef = useRef<AsciinemaPlayerModule | null>(null);
  const [activeEventIndex, setActiveEventIndex] = useState(0);
  const [hasStarted, setHasStarted] = useState(false);

  const resolvedCastKey = useMemo(() => {
    if (castKey) return castKey;
    try {
      const pathname = new URL(src, 'https://www.rediacc.com').pathname;
      const filename = pathname.split('/').pop() ?? '';
      return filename.replace(/\.cast$/i, '');
    } catch {
      return (
        src
          .split('/')
          .pop()
          ?.replace(/\.cast$/i, '') ?? ''
      );
    }
  }, [castKey, src]);

  const transcript = useMemo(() => loadTranscript(resolvedCastKey, lang), [resolvedCastKey, lang]);
  const labels = transcriptLabels[String(lang).split('-')[0].toLowerCase()] ?? transcriptLabels.en;

  useEffect(() => {
    const controller = new AbortController();
    setActiveEventIndex(0);
    setHasStarted(false);

    const createPlayer = async (startAt?: number, autoPlay?: boolean) => {
      const container = containerRef.current;
      if (!container) return;

      if (!asciinemaModuleRef.current) {
        const AsciinemaPlayer = (await import(
          'asciinema-player'
        )) as unknown as AsciinemaPlayerModule;
        await import('asciinema-player/dist/bundle/asciinema-player.css');
        asciinemaModuleRef.current = AsciinemaPlayer;
      }

      if (playerRef.current) {
        playerRef.current.dispose();
        playerRef.current = null;
      }

      const player = asciinemaModuleRef.current.create(src, container, {
        cols: 100,
        rows: 30,
        autoPlay: Boolean(autoPlay),
        loop: false,
        preload: true,
        fit: 'width',
        pauseOnMarkers: false,
        theme: 'asciinema',
        terminalFontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
        terminalFontSize: '13px',
        ...(typeof startAt === 'number' ? { startAt } : {}),
      });

      playerRef.current = player;
      player.addEventListener('marker', (payload) => {
        if (controller.signal.aborted || !transcript || transcript.events.length === 0) return;
        const marker = payload as { index?: number };
        if (typeof marker.index !== 'number') return;
        const clamped = Math.max(0, Math.min(marker.index, transcript.events.length - 1));
        setActiveEventIndex(clamped);
      });
      player.addEventListener('seeked', async () => {
        if (controller.signal.aborted || !transcript || transcript.events.length === 0) return;
        if (typeof player.getCurrentTime !== 'function') return;
        setHasStarted(true);

        const currentTime = await player.getCurrentTime();

        let nextIndex = 0;
        for (let i = 0; i < transcript.events.length; i++) {
          if (currentTime >= transcript.events[i].at) {
            nextIndex = i;
          } else {
            break;
          }
        }
        setActiveEventIndex(nextIndex);
      });
      player.addEventListener('play', () => {
        if (controller.signal.aborted) return;
        setHasStarted(true);
      });
    };

    void createPlayer();

    return () => {
      controller.abort();
      if (playerRef.current) {
        playerRef.current.dispose();
        playerRef.current = null;
      }
    };
  }, [src, transcript]);

  useEffect(() => {
    if (!transcript?.events.length) return;

    const interval = window.setInterval(async () => {
      const player = playerRef.current;
      if (!player || typeof player.getCurrentTime !== 'function') return;

      const currentTime = await player.getCurrentTime();
      let nextIndex = 0;
      for (let i = 0; i < transcript.events.length; i++) {
        if (currentTime >= transcript.events[i].at) {
          nextIndex = i;
        } else {
          break;
        }
      }
      setActiveEventIndex((prev) => (prev === nextIndex ? prev : nextIndex));
    }, 400);

    return () => window.clearInterval(interval);
  }, [transcript]);

  // Fix: reset player sizing when exiting fullscreen.
  useEffect(() => {
    const resetInlineSizing = () => {
      if (!wrapperRef.current) return;
      const apWrapper = wrapperRef.current.querySelector<HTMLElement>('.ap-wrapper');
      if (apWrapper) {
        apWrapper.style.width = '100%';
        apWrapper.style.height = '';
        apWrapper.style.maxWidth = '100%';
        apWrapper.style.maxHeight = '';
      }
      const terminal = wrapperRef.current.querySelector<HTMLElement>('.ap-player');
      if (terminal) {
        terminal.style.width = '100%';
        terminal.style.height = '';
        terminal.style.maxWidth = '100%';
        terminal.style.maxHeight = '';
      }
      window.dispatchEvent(new Event('resize'));
    };

    const onFullscreenChange = () => {
      const fullscreenElement =
        document.fullscreenElement ??
        (document as Document & { webkitFullscreenElement?: Element }).webkitFullscreenElement;

      if (!fullscreenElement) {
        // Apply immediately and once again after player internals settle.
        resetInlineSizing();
        window.setTimeout(resetInlineSizing, 80);
      }
    };

    document.addEventListener('fullscreenchange', onFullscreenChange);
    document.addEventListener('webkitfullscreenchange', onFullscreenChange as EventListener);
    return () => {
      document.removeEventListener('fullscreenchange', onFullscreenChange);
      document.removeEventListener('webkitfullscreenchange', onFullscreenChange as EventListener);
    };
  }, []);

  return (
    <div className="terminal-tutorial" ref={wrapperRef}>
      {title && <div className="terminal-tutorial-header">{title}</div>}

      <div className="terminal-tutorial-layout">
        <div className="terminal-tutorial-player">
          <div ref={containerRef} className="terminal-tutorial-player-inner" />
        </div>
      </div>

      {transcript && transcript.events.length > 0 ? (
        <div className="terminal-transcript" aria-label="Tutorial transcript">
          <h4 className="terminal-transcript-title">{labels.transcript}</h4>
          <div className="terminal-transcript-current" aria-current="true">
            <span className="terminal-transcript-step">
              {hasStarted
                ? `${labels.step} ${activeEventIndex + 1} / ${transcript.events.length}`
                : ''}
            </span>
            <span className="terminal-transcript-text">
              {hasStarted ? transcript.events[activeEventIndex].text : ''}
            </span>
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default TerminalPlayer;
