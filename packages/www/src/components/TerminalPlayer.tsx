/**
 * TerminalPlayer — Interactive asciinema-player for tutorial recordings.
 *
 * Renders a .cast file with asciinema-player. The playback bar and the
 * "What You'll See" section in the markdown provide command navigation,
 * so no sidebar is needed here.
 */

import type { FC } from 'react';
import { useEffect, useRef, useState } from 'react';

interface AsciinemaPlayerInstance {
  play(): void;
  pause(): void;
  dispose(): void;
  addEventListener(event: string, handler: () => void): void;
}

interface TerminalPlayerProps {
  src: string;
  title?: string;
}

const TerminalPlayer: FC<TerminalPlayerProps> = ({ src, title }) => {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<AsciinemaPlayerInstance | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const controller = new AbortController();

    const init = async () => {
      const container = containerRef.current;
      if (!container) return;

      const AsciinemaPlayer = await import('asciinema-player');
      await import('asciinema-player/dist/bundle/asciinema-player.css');

      if (controller.signal.aborted) return;

      const player = AsciinemaPlayer.create(src, container, {
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
      }) as AsciinemaPlayerInstance;

      playerRef.current = player;

      player.addEventListener('play', () => {
        if (!controller.signal.aborted) setIsPlaying(true);
      });
      player.addEventListener('pause', () => {
        if (!controller.signal.aborted) setIsPlaying(false);
      });

      setLoaded(true);
    };

    void init();

    return () => {
      controller.abort();
      if (playerRef.current) {
        playerRef.current.dispose();
        playerRef.current = null;
      }
    };
  }, [src]);

  // Fix: reset player sizing when exiting fullscreen.
  // asciinema-player uses the native Fullscreen API and may leave stale
  // inline dimensions on the wrapper after exiting.
  useEffect(() => {
    const onFullscreenChange = () => {
      if (!document.fullscreenElement && wrapperRef.current) {
        const apWrapper = wrapperRef.current.querySelector<HTMLElement>('.ap-wrapper');
        if (apWrapper) {
          apWrapper.style.width = '';
          apWrapper.style.height = '';
        }
        // Also reset any inline styles the player set on the terminal element
        const terminal = wrapperRef.current.querySelector<HTMLElement>('.ap-player');
        if (terminal) {
          terminal.style.width = '';
          terminal.style.height = '';
        }
      }
    };

    document.addEventListener('fullscreenchange', onFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange);
  }, []);

  const togglePlayback = () => {
    if (!playerRef.current) return;
    if (isPlaying) {
      playerRef.current.pause();
    } else {
      playerRef.current.play();
    }
  };

  return (
    <div className="terminal-tutorial" ref={wrapperRef}>
      {title && <div className="terminal-tutorial-header">{title}</div>}

      <div className="terminal-tutorial-layout">
        <div className="terminal-tutorial-player">
          <div ref={containerRef} className="terminal-tutorial-player-inner" />
          {loaded && (
            <div className="terminal-tutorial-controls">
              <button type="button" className="terminal-tutorial-play-btn" onClick={togglePlayback}>
                {isPlaying ? 'Pause' : 'Play Tutorial'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default TerminalPlayer;
