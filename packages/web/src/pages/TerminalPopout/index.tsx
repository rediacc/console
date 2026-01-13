/**
 * Terminal Popout Page
 * Fullscreen terminal for popped-out Electron windows
 */

import React, { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { Alert, Flex, Spin, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { Terminal, type TerminalRef } from '@/components/app/Terminal/Terminal';
import { isElectron, getElectronAPI } from '@/types';

const { Text } = Typography;

/**
 * Terminal Popout Page
 *
 * This page is loaded in a separate Electron window when the user
 * pops out a terminal from the TerminalModal. It receives the
 * sessionId via URL query params and connects to the existing session.
 */
export const TerminalPopout: React.FC = () => {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get('sessionId');
  const machineName = searchParams.get('machineName');
  const repositoryName = searchParams.get('repositoryName');

  const terminalRef = useRef<TerminalRef>(null);
  const [isReady, setIsReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Buffer for replaying terminal history after transfer
  const [initialBuffer, setInitialBuffer] = useState<string | null>(null);
  // Track when the Terminal component's xterm.js is actually initialized
  const [terminalReady, setTerminalReady] = useState(false);
  // Track if buffer has been replayed
  const bufferReplayedRef = useRef(false);

  // Validate environment and sessionId upfront (no setState needed)
  const validationError = useMemo(() => {
    if (!isElectron()) {
      return t('resources:localActions.popoutElectronOnly');
    }
    if (!sessionId) {
      return t('resources:localActions.popoutNoSession');
    }
    return null;
  }, [sessionId, t]);

  // Set window title based on machine/repository
  useEffect(() => {
    const parts = ['Terminal'];
    if (machineName) parts.push(machineName);
    if (repositoryName) parts.push(repositoryName);
    document.title = parts.join(' - ');
  }, [machineName, repositoryName]);

  // Transfer session to this window (only if valid)
  useEffect(() => {
    if (validationError || !sessionId) {
      return;
    }

    // Transfer the terminal session to this window
    // This re-registers IPC listeners to send data to this window instead of the original modal
    const transferSession = async () => {
      try {
        const api = getElectronAPI();
        const result = await api.terminal.transfer(sessionId);
        if (!result.success) {
          setError(
            `${t('resources:localActions.popoutTransferFailed')}: ${result.error ?? t('shared:errors.unknownError')}`
          );
          return;
        }

        // Store the buffer for replay (contains terminal history from before popout)
        if (result.buffer) {
          setInitialBuffer(result.buffer);
        }

        // Session now sends data to this window
        setIsReady(true);
        // Focus after a brief delay to ensure terminal is mounted
        setTimeout(() => {
          terminalRef.current?.focus();
        }, 50);
      } catch (err) {
        setError(
          `${t('resources:localActions.popoutTransferFailed')}: ${err instanceof Error ? err.message : 'Unknown error'}`
        );
      }
    };

    void transferSession();
  }, [sessionId, validationError, t]);

  // Replay terminal history buffer after terminal is TRULY ready (xterm initialized)
  useEffect(() => {
    if (
      isReady &&
      terminalReady &&
      initialBuffer &&
      terminalRef.current &&
      !bufferReplayedRef.current
    ) {
      // Write buffered history to the terminal display
      terminalRef.current.writeToDisplay(initialBuffer);
      // Mark buffer as replayed to prevent re-rendering
      bufferReplayedRef.current = true;
    }
  }, [isReady, terminalReady, initialBuffer]);

  // Handle terminal ready callback (xterm.js is initialized)
  const handleTerminalReady = useCallback(() => {
    setTerminalReady(true);
  }, []);

  // Handle terminal input
  const handleWrite = useCallback(
    (data: string) => {
      if (sessionId && isElectron()) {
        getElectronAPI().terminal.write(sessionId, data);
      }
    },
    [sessionId]
  );

  // Handle terminal resize
  const handleResize = useCallback(
    (cols: number, rows: number) => {
      if (sessionId && isElectron()) {
        getElectronAPI().terminal.resize(sessionId, cols, rows);
      }
    },
    [sessionId]
  );

  // Subscription function for terminal data (matches Terminal component's expected signature)
  const handleOnData = useCallback(
    (callback: (data: string) => void): (() => void) => {
      if (!sessionId || !isElectron()) {
        return () => {};
      }
      return getElectronAPI().terminal.onData(sessionId, callback);
    },
    [sessionId]
  );

  // Subscription function for terminal exit (matches Terminal component's expected signature)
  const handleOnExit = useCallback(
    (callback: (code: number) => void): (() => void) => {
      if (!sessionId || !isElectron()) {
        return () => {};
      }
      return getElectronAPI().terminal.onExit(sessionId, callback);
    },
    [sessionId]
  );

  // Validation error state (from useMemo, no setState needed)
  if (validationError) {
    return (
      <Flex
        align="center"
        justify="center"
        // eslint-disable-next-line no-restricted-syntax
        style={{ height: '100vh', backgroundColor: '#1e1e2e', padding: 24 }}
      >
        <Alert
          type="error"
          message={t('resources:localActions.terminalError')}
          description={validationError}
          showIcon
        />
      </Flex>
    );
  }

  // Error state (from async transfer)
  if (error) {
    return (
      <Flex
        align="center"
        justify="center"
        // eslint-disable-next-line no-restricted-syntax
        style={{ height: '100vh', backgroundColor: '#1e1e2e', padding: 24 }}
      >
        <Alert
          type="error"
          message={t('resources:localActions.terminalError')}
          description={error}
          showIcon
        />
      </Flex>
    );
  }

  // Loading state
  if (!isReady) {
    return (
      <Flex
        align="center"
        justify="center"
        vertical
        gap={16}
        // eslint-disable-next-line no-restricted-syntax
        style={{ height: '100vh', backgroundColor: '#1e1e2e' }}
      >
        <Spin size="large" />
        {/* eslint-disable-next-line no-restricted-syntax */}
        <Text style={{ color: '#cdd6f4' }}>{t('resources:localActions.popoutConnecting')}</Text>
      </Flex>
    );
  }

  return (
    <Flex
      vertical
      // eslint-disable-next-line no-restricted-syntax
      style={{
        height: '100vh',
        width: '100vw',
        backgroundColor: '#1e1e2e',
        overflow: 'hidden',
      }}
    >
      {sessionId && (
        <Terminal
          ref={terminalRef}
          sessionId={sessionId}
          write={handleWrite}
          resize={handleResize}
          onData={handleOnData}
          onExit={handleOnExit}
          onReady={handleTerminalReady}
          // eslint-disable-next-line no-restricted-syntax
          style={{ flex: 1, width: '100%', height: '100%' }}
        />
      )}
    </Flex>
  );
};
