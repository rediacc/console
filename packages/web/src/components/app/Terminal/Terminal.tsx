/* eslint-disable no-restricted-syntax, react/forbid-elements, react/display-name, react/hook-use-state, react-hooks/set-state-in-effect, react-hooks/exhaustive-deps, @typescript-eslint/no-unnecessary-condition */
import { useEffect, useRef, useState, forwardRef, useImperativeHandle } from 'react';
import { FitAddon } from '@xterm/addon-fit';
import { WebLinksAddon } from '@xterm/addon-web-links';
import { WebglAddon } from '@xterm/addon-webgl';
import { Terminal as XTerm } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';

/**
 * Theme configuration for the terminal
 */
export interface TerminalTheme {
  background: string;
  foreground: string;
  cursor: string;
  cursorAccent: string;
  selectionBackground: string;
  selectionForeground?: string;
  black: string;
  red: string;
  green: string;
  yellow: string;
  blue: string;
  magenta: string;
  cyan: string;
  white: string;
  brightBlack: string;
  brightRed: string;
  brightGreen: string;
  brightYellow: string;
  brightBlue: string;
  brightMagenta: string;
  brightCyan: string;
  brightWhite: string;
}

/**
 * Default dark theme for the terminal
 */
export const defaultTheme: TerminalTheme = {
  background: '#1e1e2e',
  foreground: '#cdd6f4',
  cursor: '#f5e0dc',
  cursorAccent: '#1e1e2e',
  selectionBackground: '#585b70',
  selectionForeground: '#cdd6f4',
  black: '#45475a',
  red: '#f38ba8',
  green: '#a6e3a1',
  yellow: '#f9e2af',
  blue: '#89b4fa',
  magenta: '#f5c2e7',
  cyan: '#94e2d5',
  white: '#bac2de',
  brightBlack: '#585b70',
  brightRed: '#f38ba8',
  brightGreen: '#a6e3a1',
  brightYellow: '#f9e2af',
  brightBlue: '#89b4fa',
  brightMagenta: '#f5c2e7',
  brightCyan: '#94e2d5',
  brightWhite: '#a6adc8',
};

/**
 * Props for the Terminal component
 */
export interface TerminalProps {
  /** Session ID for the terminal connection */
  sessionId: string | null;
  /** Write function for sending data to the terminal */
  write: (data: string) => void;
  /** Resize function for updating terminal dimensions */
  resize: (cols: number, rows: number) => void;
  /** Subscribe to terminal data */
  onData: (callback: (data: string) => void) => () => void;
  /** Subscribe to terminal exit */
  onExit: (callback: (code: number) => void) => () => void;
  /** Callback when terminal is ready */
  onReady?: () => void;
  /** Custom terminal theme */
  theme?: Partial<TerminalTheme>;
  /** Font size in pixels */
  fontSize?: number;
  /** Font family */
  fontFamily?: string;
  /** Whether cursor should blink */
  cursorBlink?: boolean;
  /** Cursor style */
  cursorStyle?: 'block' | 'underline' | 'bar';
  /** Additional CSS class name */
  className?: string;
  /** Additional inline styles */
  style?: React.CSSProperties;
}

/**
 * Methods exposed by the Terminal component via ref
 */
export interface TerminalRef {
  /** Focus the terminal */
  focus: () => void;
  /** Write data to the terminal display */
  writeToDisplay: (data: string) => void;
  /** Clear the terminal */
  clear: () => void;
  /** Get current dimensions */
  getDimensions: () => { cols: number; rows: number } | null;
  /** Fit terminal to container */
  fit: () => void;
}

/**
 * Terminal component using xterm.js 6.0.0
 *
 * Renders an interactive terminal that connects to an SSH session
 * via Electron IPC. Uses WebGL rendering for optimal performance.
 *
 * @example
 * ```tsx
 * const terminal = useTerminal({ host, user, privateKey });
 * const terminalRef = useRef<TerminalRef>(null);
 *
 * return (
 *   <Terminal
 *     ref={terminalRef}
 *     sessionId={terminal.sessionId}
 *     write={terminal.write}
 *     resize={terminal.resize}
 *     onData={terminal.onData}
 *     onExit={terminal.onExit}
 *     onReady={() => console.log('Terminal ready')}
 *   />
 * );
 * ```
 */
export const Terminal = forwardRef<TerminalRef, TerminalProps>(
  (
    {
      sessionId,
      write,
      resize,
      onData,
      onExit,
      onReady,
      theme,
      fontSize = 14,
      fontFamily = 'Menlo, Monaco, "Cascadia Mono", "Segoe UI Mono", "Roboto Mono", "Oxygen Mono", "Ubuntu Monospace", "Source Code Pro", "Fira Mono", "Droid Sans Mono", "Courier New", monospace',
      cursorBlink = true,
      cursorStyle = 'block',
      className,
      style,
    },
    ref
  ) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const xtermRef = useRef<XTerm | null>(null);
    const fitAddonRef = useRef<FitAddon | null>(null);
    const webglAddonRef = useRef<WebglAddon | null>(null);
    const [, setIsReady] = useState(false);

    // Merge theme with defaults
    const mergedTheme = { ...defaultTheme, ...theme };

    // Expose methods via ref
    useImperativeHandle(
      ref,
      () => ({
        focus: () => xtermRef.current?.focus(),
        writeToDisplay: (data: string) => xtermRef.current?.write(data),
        clear: () => xtermRef.current?.clear(),
        getDimensions: () => {
          const term = xtermRef.current;
          return term ? { cols: term.cols, rows: term.rows } : null;
        },
        fit: () => fitAddonRef.current?.fit(),
      }),
      []
    );

    // Initialize xterm.js
    useEffect(() => {
      if (!containerRef.current) return;

      // Create terminal instance
      const xterm = new XTerm({
        cursorBlink,
        cursorStyle,
        fontSize,
        fontFamily,
        theme: mergedTheme,
        allowProposedApi: true,
        scrollback: 10000,
        convertEol: true,
      });

      // Create and load addons
      const fitAddon = new FitAddon();
      xterm.loadAddon(fitAddon);
      xterm.loadAddon(new WebLinksAddon());

      // Open terminal in container
      xterm.open(containerRef.current);

      // Try to load WebGL addon for better performance
      try {
        const webglAddon = new WebglAddon();
        webglAddon.onContextLoss(() => {
          webglAddon.dispose();
          webglAddonRef.current = null;
        });
        xterm.loadAddon(webglAddon);
        webglAddonRef.current = webglAddon;
      } catch (e) {
        console.warn('WebGL addon failed to load, falling back to canvas renderer:', e);
      }

      // Fit to container
      fitAddon.fit();

      // Store refs
      xtermRef.current = xterm;
      fitAddonRef.current = fitAddon;

      // Mark as ready
      setIsReady(true);
      onReady?.();

      // Cleanup on unmount
      return () => {
        webglAddonRef.current?.dispose();
        xterm.dispose();
        xtermRef.current = null;
        fitAddonRef.current = null;
        webglAddonRef.current = null;
      };
    }, []); // Only run once on mount

    // Handle resize events
    useEffect(() => {
      if (!containerRef.current || !fitAddonRef.current || !xtermRef.current) return;

      const handleResize = (): void => {
        const fitAddon = fitAddonRef.current;
        const xterm = xtermRef.current;

        if (fitAddon && xterm) {
          fitAddon.fit();
          // Notify backend of new dimensions
          resize(xterm.cols, xterm.rows);
        }
      };

      // Create resize observer
      const resizeObserver = new ResizeObserver(handleResize);
      resizeObserver.observe(containerRef.current);

      // Also handle window resize
      window.addEventListener('resize', handleResize);

      // Initial resize notification
      if (sessionId && xtermRef.current) {
        resize(xtermRef.current.cols, xtermRef.current.rows);
      }

      return () => {
        resizeObserver.disconnect();
        window.removeEventListener('resize', handleResize);
      };
    }, [resize, sessionId]);

    // Handle terminal input (user typing)
    useEffect(() => {
      const xterm = xtermRef.current;
      if (!xterm || !sessionId) return;

      const disposable = xterm.onData((data: string) => {
        write(data);
      });

      return () => disposable.dispose();
    }, [sessionId, write]);

    // Handle terminal data from backend
    useEffect(() => {
      const xterm = xtermRef.current;
      if (!xterm || !sessionId) return;

      const cleanup = onData((data) => {
        xterm.write(data);
      });

      return cleanup;
    }, [sessionId, onData]);

    // Handle terminal exit
    useEffect(() => {
      const xterm = xtermRef.current;
      if (!xterm || !sessionId) return;

      const cleanup = onExit((code) => {
        xterm.write(`\r\n\x1b[33m[Session exited with code ${code}]\x1b[0m\r\n`);
      });

      return cleanup;
    }, [sessionId, onExit]);

    // Focus terminal when session connects
    useEffect(() => {
      if (sessionId && xtermRef.current) {
        xtermRef.current.focus();
      }
    }, [sessionId]);

    return (
      <div
        ref={containerRef}
        className={className}
        style={{
          width: '100%',
          height: '100%',
          minHeight: 200,
          backgroundColor: mergedTheme.background,
          ...style,
        }}
      />
    );
  }
);
