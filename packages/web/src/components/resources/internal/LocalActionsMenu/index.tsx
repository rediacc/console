import { DEFAULTS } from '@rediacc/shared/config';
import type { MenuProps } from 'antd';
import { Button, Dropdown, Tooltip, Typography } from 'antd';
import React, { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSelector } from 'react-redux';
import { ContainerLogsModal } from '@/components/app/ContainerLogsModal';
import { ContainerStatsModal } from '@/components/app/ContainerStatsModal';
import { ContainerTerminalModal } from '@/components/app/ContainerTerminalModal';
import { DirectFileBrowser } from '@/components/app/DirectFileBrowser';
import { TerminalModal } from '@/components/app/TerminalModal';
import { VSCodeSelectionModal } from '@/components/app/VSCodeSelectionModal';
import { LocalCommandModal } from '@/components/resources/internal/LocalCommandModal';
import { PipInstallationModal } from '@/components/resources/internal/PipInstallationModal';
import { useMessage } from '@/hooks';
import { useDialogState } from '@/hooks/useDialogState';
import { type MachineSSHCredentials, useMachineCredentials } from '@/hooks/useMachineCredentials';
import type { ProtocolAction } from '@/services/protocolUrlService';
import type { RootState } from '@/store/store';
import type { PluginContainer } from '@/types';
import { isElectron } from '@/types';
import {
  BuildOutlined,
  CodeOutlined,
  DesktopOutlined,
  FileTextOutlined,
} from '@/utils/optimizedIcons';
import {
  type ContainerMenuAction,
  type ContainerModalData,
  handleElectronFlow,
  handleWebProtocolFlow,
} from './helpers';
import { useVSCodeSelection } from './hooks/useVSCodeSelection';

type ItemType = NonNullable<MenuProps['items']>[number];
type MenuItemWithTestId = ItemType & { ['data-testid']?: string };

interface LocalActionsMenuProps {
  machine: string;
  repository?: string;
  teamName?: string;
  disabled?: boolean;
  userEmail?: string;
  pluginContainers?: PluginContainer[];
  containerId?: string;
  containerName?: string;
  containerState?: string;
  isContainerMenu?: boolean;
  isMachineOnlyMenu?: boolean;
}

const createMenuIcon = (IconComponent: React.ElementType) => <IconComponent />;

export const LocalActionsMenu: React.FC<LocalActionsMenuProps> = ({
  machine,
  repository,
  teamName = 'Default',
  disabled = false,
  userEmail,
  pluginContainers = [],
  containerId,
  containerName,
  containerState,
  isContainerMenu = false,
  isMachineOnlyMenu = false,
}) => {
  const { t } = useTranslation();
  const message = useMessage();
  const installModal = useDialogState<
    'not-installed' | 'protocol-not-registered' | 'permission-denied'
  >();
  const [isCheckingProtocol, setIsCheckingProtocol] = useState(false);
  const commandModal = useDialogState<void>();
  const terminalModal = useDialogState<{
    host: string;
    user: string;
    port: number;
    privateKey: string;
    known_hosts?: string;
    machineName: string;
    repositoryName?: string;
    initialPath?: string;
  }>();
  const fileBrowserModal = useDialogState<MachineSSHCredentials & { machineName: string }>();
  // Container modal states for Electron
  const containerTerminalModal = useDialogState<ContainerModalData>();
  const containerLogsModal = useDialogState<ContainerModalData>();
  const containerStatsModal = useDialogState<ContainerModalData>();
  const { getCredentials, isLoading: isLoadingCredentials } = useMachineCredentials();
  const vsCodeSelection = useVSCodeSelection({
    teamName,
    machine,
    repository,
    onError: (err) => message.error(err),
  });
  const currentUserEmail = useSelector((state: RootState) => state.auth.user?.email);

  const handleOpenInDesktop = useCallback(
    async (action?: ProtocolAction, containerAction?: ContainerMenuAction) => {
      // Use native Electron APIs when running in Electron
      if (isElectron()) {
        try {
          await handleElectronFlow({
            teamName,
            machine,
            repository,
            isContainerMenu,
            containerId,
            containerName,
            containerAction,
            action,
            getCredentials,
            containerTerminalModal,
            containerLogsModal,
            containerStatsModal,
            terminalModal,
            fileBrowserModal,
            vsCodeSelection,
            message,
          });
        } catch (error) {
          console.error('Failed to open native action:', error);
          message.error(error instanceof Error ? error.message : 'common:desktopConnectionFailed');
        }
        return;
      }

      // Fall back to protocol URLs for web
      const baseParams = {
        team: teamName,
        machine,
        repository: isMachineOnlyMenu ? '' : (repository ?? ''),
      };

      await handleWebProtocolFlow({
        baseParams,
        isContainerMenu,
        containerId,
        containerName,
        containerAction,
        action,
        setIsCheckingProtocol,
        installModal,
        message,
      });
    },
    [
      teamName,
      machine,
      repository,
      isContainerMenu,
      containerId,
      containerName,
      isMachineOnlyMenu,
      installModal,
      message,
      getCredentials,
      terminalModal,
      fileBrowserModal,
      containerTerminalModal,
      containerLogsModal,
      containerStatsModal,
      vsCodeSelection,
    ]
  );

  const buildContainerMenuItems = (): MenuItemWithTestId[] => {
    const items: MenuItemWithTestId[] = [];
    const isRunning = containerState === 'running';

    if (isRunning) {
      items.push({
        key: 'container-terminal',
        icon: createMenuIcon(CodeOutlined),
        label: (
          <Typography.Text>{t('resources:localActions.openContainerTerminal')}</Typography.Text>
        ),
        onClick: () => handleOpenInDesktop(undefined, 'terminal'),
        'data-testid': `local-actions-container-terminal-${containerId}`,
      });
    }

    if (items.length > 0) {
      items.push({ type: 'divider' });
    }

    items.push({
      key: 'container-logs',
      icon: createMenuIcon(BuildOutlined),
      label: <Typography.Text>{t('resources:localActions.viewContainerLogs')}</Typography.Text>,
      onClick: () => handleOpenInDesktop(undefined, 'logs'),
      'data-testid': `local-actions-container-logs-${containerId}`,
    });

    if (isRunning) {
      items.push({
        key: 'container-stats',
        icon: createMenuIcon(BuildOutlined),
        label: <Typography.Text>{t('resources:localActions.containerStats')}</Typography.Text>,
        onClick: () => handleOpenInDesktop(undefined, 'stats'),
        'data-testid': `local-actions-container-stats-${containerId}`,
      });
    }

    return items;
  };

  const buildMachineMenuItems = (): MenuItemWithTestId[] => [
    {
      key: 'open',
      icon: createMenuIcon(DesktopOutlined),
      label: <Typography.Text>{t('resources:localActions.openInDesktop')}</Typography.Text>,
      onClick: () => handleOpenInDesktop(),
      'data-testid': `local-actions-open-${repository}`,
    },
    {
      key: 'vscode',
      icon: createMenuIcon(FileTextOutlined),
      label: <Typography.Text>{t('resources:localActions.openInVSCode')}</Typography.Text>,
      onClick: () => handleOpenInDesktop('vscode'),
      'data-testid': `local-actions-vscode-${repository}`,
    },
    {
      key: 'terminal',
      icon: createMenuIcon(CodeOutlined),
      label: <Typography.Text>{t('resources:localActions.openTerminal')}</Typography.Text>,
      onClick: () => handleOpenInDesktop('terminal'),
      'data-testid': `local-actions-terminal-${repository}`,
    },
    { type: 'divider' },
    {
      key: 'cli-commands',
      icon: createMenuIcon(BuildOutlined),
      label: <Typography.Text>{t('resources:localActions.showCLICommands')}</Typography.Text>,
      onClick: () => commandModal.open(),
      'data-testid': `local-actions-cli-commands-${repository}`,
    },
  ];

  const menuItems = isContainerMenu ? buildContainerMenuItems() : buildMachineMenuItems();
  const menuConfig: MenuProps = { items: menuItems as ItemType[] };

  const tooltipLabel = isContainerMenu
    ? t('resources:localActions.containerLocal')
    : t('resources:localActions.local');

  const triggerTestId = isContainerMenu
    ? `local-actions-dropdown-${containerId}`
    : `local-actions-dropdown-${repository}`;

  return (
    <>
      <Dropdown
        menu={menuConfig}
        trigger={['click']}
        disabled={disabled || isCheckingProtocol || isLoadingCredentials}
        data-testid={`local-actions-dropdown-container-${repository}`}
      >
        <Tooltip title={tooltipLabel}>
          <Button
            icon={createMenuIcon(DesktopOutlined)}
            loading={isCheckingProtocol || isLoadingCredentials}
            disabled={disabled || isCheckingProtocol || isLoadingCredentials}
            data-testid={triggerTestId}
            aria-label={tooltipLabel}
            className="inline-flex items-center"
            // eslint-disable-next-line no-restricted-syntax
            style={{ minHeight: 40 }}
          />
        </Tooltip>
      </Dropdown>

      <PipInstallationModal
        open={installModal.isOpen}
        onClose={installModal.close}
        errorType={installModal.state.data ?? DEFAULTS.VSCODE.NOT_INSTALLED}
      />

      {!isContainerMenu && (
        <LocalCommandModal
          open={commandModal.isOpen}
          onClose={commandModal.close}
          machine={machine}
          repository={repository}
          userEmail={userEmail ?? currentUserEmail ?? ''}
          pluginContainers={pluginContainers}
        />
      )}

      {/* Electron-native modals */}
      {isElectron() && (
        <>
          <TerminalModal
            open={terminalModal.isOpen}
            onClose={terminalModal.close}
            host={terminalModal.state.data?.host ?? ''}
            user={terminalModal.state.data?.user ?? ''}
            port={terminalModal.state.data?.port}
            privateKey={terminalModal.state.data?.privateKey ?? ''}
            known_hosts={terminalModal.state.data?.known_hosts}
            machineName={terminalModal.state.data?.machineName ?? machine}
            repositoryName={terminalModal.state.data?.repositoryName}
            initialPath={terminalModal.state.data?.initialPath}
          />
          <DirectFileBrowser
            open={fileBrowserModal.isOpen}
            onCancel={fileBrowserModal.close}
            host={fileBrowserModal.state.data?.host ?? ''}
            user={fileBrowserModal.state.data?.user ?? ''}
            port={fileBrowserModal.state.data?.port}
            privateKey={fileBrowserModal.state.data?.privateKey ?? ''}
            machineName={fileBrowserModal.state.data?.machineName ?? machine}
            initialPath={fileBrowserModal.state.data?.datastore}
          />
          {/* Container modals for Electron */}
          <ContainerTerminalModal
            open={containerTerminalModal.isOpen}
            onClose={containerTerminalModal.close}
            host={containerTerminalModal.state.data?.host ?? ''}
            user={containerTerminalModal.state.data?.user ?? ''}
            port={containerTerminalModal.state.data?.port}
            privateKey={containerTerminalModal.state.data?.privateKey ?? ''}
            known_hosts={containerTerminalModal.state.data?.known_hosts}
            machineName={containerTerminalModal.state.data?.machineName ?? machine}
            containerId={containerTerminalModal.state.data?.containerId ?? ''}
            containerName={containerTerminalModal.state.data?.containerName}
          />
          <ContainerLogsModal
            open={containerLogsModal.isOpen}
            onClose={containerLogsModal.close}
            host={containerLogsModal.state.data?.host ?? ''}
            user={containerLogsModal.state.data?.user ?? ''}
            port={containerLogsModal.state.data?.port}
            privateKey={containerLogsModal.state.data?.privateKey ?? ''}
            known_hosts={containerLogsModal.state.data?.known_hosts}
            machineName={containerLogsModal.state.data?.machineName ?? machine}
            containerId={containerLogsModal.state.data?.containerId ?? ''}
            containerName={containerLogsModal.state.data?.containerName}
          />
          <ContainerStatsModal
            open={containerStatsModal.isOpen}
            onClose={containerStatsModal.close}
            host={containerStatsModal.state.data?.host ?? ''}
            user={containerStatsModal.state.data?.user ?? ''}
            port={containerStatsModal.state.data?.port}
            privateKey={containerStatsModal.state.data?.privateKey ?? ''}
            known_hosts={containerStatsModal.state.data?.known_hosts}
            machineName={containerStatsModal.state.data?.machineName ?? machine}
            containerId={containerStatsModal.state.data?.containerId ?? ''}
            containerName={containerStatsModal.state.data?.containerName}
          />
          {/* VS Code selection modal for Windows/WSL choice */}
          <VSCodeSelectionModal
            open={vsCodeSelection.modal.isOpen}
            onClose={vsCodeSelection.modal.close}
            installations={
              vsCodeSelection.modal.state.data?.installations ?? { windows: null, wsl: null }
            }
            onSelect={vsCodeSelection.handleSelection}
          />
        </>
      )}
    </>
  );
};
