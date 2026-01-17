/**
 * Container Logs Modal Component
 * Docker logs streaming in a modal dialog for Electron desktop app
 */

import React, { useEffect, useRef, useState } from 'react';
import { Alert, Button, Flex, Space, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { Terminal, type TerminalRef } from '@/components/app/Terminal/Terminal';
import { SizedModal } from '@/components/common/SizedModal';
import { useContainer } from '@/hooks/container/useContainer';
import { getElectronAPI, isElectron } from '@/types';
import { ModalSize } from '@/types/modal';
import { ExpandOutlined, FileTextOutlined, ReloadOutlined } from '@/utils/optimizedIcons';

const { Text } = Typography;

interface ContainerLogsModalProps {
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
  /** Docker container ID */
  containerId: string;
  /** Docker container name for display */
  containerName?: string;
  /** Follow log output (default: true) */
  follow?: boolean;
  /** Number of lines to show from the end (default: 100) */
  tail?: number;
}

/**
 * Container Logs Modal for docker logs in Electron desktop app
 *
 * Opens an xterm.js terminal to stream docker logs.
 * Only functional in Electron - returns null in browser.
 */
export const ContainerLogsModal: React.FC<ContainerLogsModalProps> = ({
  open,
  onClose,
  host,
  user,
  port = 22,
  privateKey,
  known_hosts,
  machineName,
  containerId,
  containerName,
  follow = true,
  tail = 100,
}) => {
  const { t } = useTranslation(['resources', 'common']);
  const terminalRef = useRef<TerminalRef>(null);
  const [isPopoutLoading, setIsPopoutLoading] = useState(false);
  const transferredToPopout = useRef(false);

  // Use the container hook for docker logs session management
  const container = useContainer({
    type: 'logs',
    host,
    user,
    port,
    privateKey,
    known_hosts,
    containerId,
    containerName,
    follow,
    tail,
  });

  // Connect when modal opens
  useEffect(() => {
    if (open && isElectron() && !container.isConnected && !container.isConnecting) {
      void container.connect();
    }
  }, [open, container.isConnected, container.isConnecting, container]);

  // Disconnect when modal closes (unless transferred to popout)
  useEffect(() => {
    if (!open && container.isConnected && !transferredToPopout.current) {
      void container.disconnect();
    }
  }, [open, container.isConnected, container]);

  // Reset state when modal opens/closes
  useEffect(() => {
    if (open) {
      transferredToPopout.current = false;
    }
  }, [open]);

  // Focus terminal when connected
  useEffect(() => {
    if (container.isConnected && terminalRef.current) {
      terminalRef.current.focus();
    }
  }, [container.isConnected]);

  // Don't render if not in Electron
  if (!isElectron()) {
    return null;
  }

  const handleReconnect = () => {
    void container.disconnect().then(() => {
      void container.connect();
    });
  };

  const handlePopout = async () => {
    if (!container.sessionId) return;

    setIsPopoutLoading(true);
    try {
      const api = getElectronAPI();
      const result = await api.window.openPopout({
        type: 'container',
        sessionId: container.sessionId,
        machineName,
        containerId,
        containerName,
        containerSessionType: 'logs',
      });

      if (result.success) {
        transferredToPopout.current = true;
        onClose();
      }
      // else: error handled silently (popout failed, user can try again)
    } catch {
      // Failed to open popout window - user can try again
    } finally {
      setIsPopoutLoading(false);
    }
  };

  const displayName = containerName ?? containerId.slice(0, 12);

  const title = (
    <Space>
      <FileTextOutlined />
      <Text>
        {t('resources:localActions.containerLogs')} - {displayName}
      </Text>
      <Text type="secondary">@ {machineName}</Text>
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
            {container.isConnected && (
              <Text type="secondary">
                {t('resources:localActions.containerLogsStreaming', {
                  container: displayName,
                })}
              </Text>
            )}
            {container.error && <Text type="danger">{container.error}</Text>}
          </Space>
          <Space>
            <Tooltip title={t('common:terminal.popout')}>
              <Button
                icon={<ExpandOutlined />}
                onClick={() => void handlePopout()}
                disabled={!container.isConnected || isPopoutLoading}
                loading={isPopoutLoading}
              />
            </Tooltip>
            <Tooltip title={t('common:terminal.reconnect')}>
              <Button
                icon={<ReloadOutlined />}
                onClick={handleReconnect}
                disabled={container.isConnecting}
                loading={container.isConnecting}
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
        {container.error && !container.isConnected && (
          <Alert
            type="error"
            message={t('resources:localActions.containerConnectionFailed')}
            description={container.error}
            showIcon
            // eslint-disable-next-line no-restricted-syntax
            style={{ marginBottom: 16 }}
          />
        )}

        {/* Connecting state */}
        {container.isConnecting && (
          <Alert
            type="info"
            message={t('resources:localActions.containerConnecting')}
            description={t('resources:localActions.containerLogsLoading', {
              container: displayName,
            })}
            showIcon
            // eslint-disable-next-line no-restricted-syntax
            style={{ marginBottom: 16 }}
          />
        )}

        {/* Terminal (read-only logs display) */}
        {container.sessionId ? (
          <Terminal
            ref={terminalRef}
            sessionId={container.sessionId}
            write={container.write}
            resize={container.resize}
            onData={container.onData}
            onExit={container.onExit}
            // eslint-disable-next-line no-restricted-syntax
            style={{ flex: 1, borderRadius: 8, overflow: 'hidden' }}
          />
        ) : (
          !container.isConnecting &&
          !container.error && (
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
              <Text type="secondary">
                {t('resources:localActions.containerWaitingForConnection')}
              </Text>
            </Flex>
          )
        )}
      </Flex>
    </SizedModal>
  );
};
