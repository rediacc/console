/**
 * Terminal Modal Component
 * SSH terminal in a modal dialog for Electron desktop app
 */

import React, { useEffect, useRef, useState } from 'react';
import { Alert, Button, Flex, Space, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { Terminal, type TerminalRef } from '@/components/app/Terminal/Terminal';
import { SizedModal } from '@/components/common/SizedModal';
import { useTerminal } from '@/hooks/terminal/useTerminal';
import { getElectronAPI, isElectron } from '@/types';
import { ModalSize } from '@/types/modal';
import { CodeOutlined, ExpandOutlined, ReloadOutlined } from '@/utils/optimizedIcons';

const { Text } = Typography;

interface TerminalModalProps {
  /** Whether the modal is open */
  open: boolean;
  /** Callback when modal is closed */
  onClose: () => void;
  /** SSH host IP or hostname */
  host: string;
  /** SSH username */
  user: string;
  /** SSH port (default: 22) */
  port?: number;
  /** SSH private key (PEM format) */
  privateKey: string;
  /** SSH known_hosts entry */
  known_hosts?: string;
  /** Machine name for display */
  machineName: string;
  /** Repository name for display (optional) */
  repositoryName?: string;
  /** Initial path to cd into after connection */
  initialPath?: string;
}

/**
 * Terminal Modal for SSH connections in Electron desktop app
 *
 * Opens an xterm.js terminal connected via SSH to a remote machine.
 * Only functional in Electron - returns null in browser.
 */
export const TerminalModal: React.FC<TerminalModalProps> = ({
  open,
  onClose,
  host,
  user,
  port = 22,
  privateKey,
  known_hosts,
  machineName,
  repositoryName,
  initialPath,
}) => {
  const { t } = useTranslation(['resources', 'common']);
  const terminalRef = useRef<TerminalRef>(null);
  const [isPopoutLoading, setIsPopoutLoading] = useState(false);
  // Track if session was transferred to popout (don't disconnect on close)
  const transferredToPopout = useRef(false);

  // Use the terminal hook for SSH session management
  const terminal = useTerminal({
    host,
    user,
    port,
    privateKey,
    known_hosts,
    onConnect: () => {
      // Navigate to initial path if provided
      if (initialPath) {
        // Give terminal a moment to be ready, then cd
        setTimeout(() => {
          terminal.write(`cd ${initialPath} && clear\n`);
        }, 500);
      }
    },
  });

  // Connect when modal opens
  useEffect(() => {
    if (open && isElectron() && !terminal.isConnected && !terminal.isConnecting) {
      void terminal.connect();
    }
  }, [open, terminal.isConnected, terminal.isConnecting, terminal]);

  // Disconnect when modal closes (unless transferred to popout)
  useEffect(() => {
    if (!open && terminal.isConnected && !transferredToPopout.current) {
      void terminal.disconnect();
    }
  }, [open, terminal.isConnected, terminal]);

  // Reset state when modal opens/closes
  useEffect(() => {
    if (open) {
      // Reset popout flag when modal opens (new session)
      transferredToPopout.current = false;
    }
  }, [open]);

  // Focus terminal when connected
  useEffect(() => {
    if (terminal.isConnected && terminalRef.current) {
      terminalRef.current.focus();
    }
  }, [terminal.isConnected]);

  // Don't render if not in Electron
  if (!isElectron()) {
    return null;
  }

  const handleReconnect = () => {
    void terminal.disconnect().then(() => {
      void terminal.connect();
    });
  };

  const handlePopout = async () => {
    if (!terminal.sessionId) return;

    setIsPopoutLoading(true);
    try {
      const api = getElectronAPI();
      const result = await api.window.openPopout({
        type: 'terminal',
        sessionId: terminal.sessionId,
        machineName,
        repositoryName,
      });

      if (result.success) {
        // Mark as transferred so we don't disconnect the session
        transferredToPopout.current = true;
        // Close the modal - session continues in the new window
        onClose();
      }
      // else: error handled silently (popout failed, user can try again)
    } catch {
      // Failed to open popout window - user can try again
    } finally {
      setIsPopoutLoading(false);
    }
  };

  const title = (
    <Space>
      <CodeOutlined />
      <Text>
        {t('common:terminal.terminal')} - {machineName}
      </Text>
      {repositoryName && <Text type="secondary">/ {repositoryName}</Text>}
    </Space>
  );

  return (
    <SizedModal
      open={open}
      onCancel={onClose}
      size={ModalSize.Large}
      title={title}
      footer={
        <Flex justify="space-between" align="center">
          <Space>
            {terminal.isConnected && (
              <Text type="secondary">
                {t('common:terminal.connectedTo', { host: `${user}@${host}:${port}` })}
              </Text>
            )}
            {terminal.error && <Text type="danger">{terminal.error}</Text>}
          </Space>
          <Space>
            <Tooltip title={t('common:terminal.popout')}>
              <Button
                icon={<ExpandOutlined />}
                onClick={() => void handlePopout()}
                disabled={!terminal.isConnected || isPopoutLoading}
                loading={isPopoutLoading}
              />
            </Tooltip>
            <Tooltip title={t('common:terminal.reconnect')}>
              <Button
                icon={<ReloadOutlined />}
                onClick={handleReconnect}
                disabled={terminal.isConnecting}
                loading={terminal.isConnecting}
              />
            </Tooltip>
            <Button onClick={onClose}>{t('common:actions.close')}</Button>
          </Space>
        </Flex>
      }
      destroyOnHidden
    >
      <Flex
        vertical
        // eslint-disable-next-line no-restricted-syntax
        style={{ height: '60vh', minHeight: 400 }}
      >
        {/* Error Alert */}
        {terminal.error && !terminal.isConnected && (
          <Alert
            type="error"
            message={t('common:terminal.connectionFailed')}
            description={terminal.error}
            showIcon
            // eslint-disable-next-line no-restricted-syntax
            style={{ marginBottom: 16 }}
          />
        )}

        {/* Connecting state */}
        {terminal.isConnecting && (
          <Alert
            type="info"
            message={t('common:terminal.connecting')}
            description={t('common:terminal.establishingConnection', { host })}
            showIcon
            // eslint-disable-next-line no-restricted-syntax
            style={{ marginBottom: 16 }}
          />
        )}

        {/* Terminal */}
        {terminal.sessionId ? (
          <Terminal
            ref={terminalRef}
            sessionId={terminal.sessionId}
            write={terminal.write}
            resize={terminal.resize}
            onData={terminal.onData}
            onExit={terminal.onExit}
            // eslint-disable-next-line no-restricted-syntax
            style={{ flex: 1, borderRadius: 8, overflow: 'hidden' }}
          />
        ) : (
          !terminal.isConnecting &&
          !terminal.error && (
            <Flex
              justify="center"
              align="center"
              // eslint-disable-next-line no-restricted-syntax
              style={{
                flex: 1,
                backgroundColor: '#1e1e2e',
                borderRadius: 8,
              }}
            >
              <Text type="secondary">{t('common:terminal.waitingForConnection')}</Text>
            </Flex>
          )
        )}
      </Flex>
    </SizedModal>
  );
};
