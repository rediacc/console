import React, { useState, useCallback } from 'react'
import { Dropdown, Button, Menu, message, Tooltip } from 'antd'
import {
  DesktopOutlined,
  SyncOutlined,
  CodeOutlined,
  ApiOutlined,
  FolderOpenOutlined,
  DownOutlined,
  BuildOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useSelector } from 'react-redux'
import { protocolUrlService, ProtocolAction, ContainerParams } from '@/services/protocolUrlService'
import { PipInstallationModal } from './PipInstallationModal'
import { LocalCommandModal } from './LocalCommandModal'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import type { RootState } from '@/store/store'

interface LocalActionsMenuProps {
  machine: string
  repository: string
  teamName?: string
  disabled?: boolean
  userEmail?: string
  pluginContainers?: Array<{
    name: string
    image: string
    status: string
    [key: string]: any
  }>
  // Container-specific props
  containerId?: string
  containerName?: string
  isContainerMenu?: boolean
}

export const LocalActionsMenu: React.FC<LocalActionsMenuProps> = ({
  machine,
  repository,
  teamName = 'Default',
  disabled = false,
  userEmail,
  pluginContainers = [],
  containerId,
  containerName,
  isContainerMenu = false
}) => {
  const { t } = useTranslation()
  const [showInstallModal, setShowInstallModal] = useState(false)
  const [installModalErrorType, setInstallModalErrorType] = useState<'not-installed' | 'protocol-not-registered' | 'permission-denied'>('not-installed')
  const [isCheckingProtocol, setIsCheckingProtocol] = useState(false)
  const [showCommandModal, setShowCommandModal] = useState(false)

  const styles = useComponentStyles()
  const currentUserEmail = useSelector((state: RootState) => state.auth.user?.email)

  // Filter running plugin containers
  const runningPlugins = pluginContainers.filter(container => 
    container.image?.includes('rediacc/plugin') && 
    container.status?.toLowerCase().includes('running')
  )

  const handleOpenInDesktop = useCallback(async (action?: ProtocolAction, containerAction?: 'terminal' | 'logs' | 'stats') => {
    const baseParams = {
      team: teamName,
      machine,
      repository
    }

    let url: string
    try {
      if (isContainerMenu && containerId) {
        // Container-specific URL generation
        const containerParams: ContainerParams = {
          containerId,
          containerName,
          action: containerAction || 'terminal'
        }

        switch (containerAction) {
          case 'logs':
            url = await protocolUrlService.generateContainerLogsUrl(baseParams, containerParams)
            break
          case 'stats':
            url = await protocolUrlService.generateContainerStatsUrl(baseParams, containerParams)
            break
          case 'terminal':
          default:
            url = await protocolUrlService.generateContainerTerminalUrl(baseParams, containerParams)
            break
        }
      } else if (action) {
        // Generate action-specific URL
        switch (action) {
          case 'sync':
            url = await protocolUrlService.generateSyncUrl(baseParams)
            break
          case 'terminal':
            url = await protocolUrlService.generateTerminalUrl(baseParams)
            break
          case 'plugin':
            url = await protocolUrlService.generatePluginUrl(baseParams, {
              // Auto-select first running plugin if available
              name: runningPlugins[0]?.name
            })
            break
          case 'browser':
            url = await protocolUrlService.generateBrowserUrl(baseParams)
            break
          default:
            url = await protocolUrlService.generateUrl(baseParams)
        }
      } else {
        // Default action for "Open in Desktop" - use terminal as default (most commonly useful)
        if (isContainerMenu && containerId) {
          const containerParams: ContainerParams = {
            containerId,
            containerName,
            action: 'terminal'
          }
          url = await protocolUrlService.generateContainerTerminalUrl(baseParams, containerParams)
        } else {
          url = await protocolUrlService.generateTerminalUrl(baseParams)
        }
      }
    } catch (error) {
      console.error('Failed to generate protocol URL:', error)
      message.error('Failed to create secure connection for desktop app')
      return
    }

    // Try to open the URL
    setIsCheckingProtocol(true)
    const result = await protocolUrlService.openUrl(url)
    setIsCheckingProtocol(false)

    // If protocol failed, show installation modal
    if (!result.success) {
      // Enhanced error detection using protocol status
      try {
        const protocolStatus = await protocolUrlService.checkProtocolStatus()
        
        if (protocolStatus.available) {
          // Protocol is available but URL failed - might be permission issue
          setInstallModalErrorType('permission-denied')
        } else {
          // Protocol not available - check error reason
          if (protocolStatus.errorReason?.includes('not registered')) {
            setInstallModalErrorType('protocol-not-registered')
          } else {
            setInstallModalErrorType('not-installed')
          }
        }
      } catch (statusError) {
        // Fallback to original error detection
        if (result.error?.type === 'timeout') {
          setInstallModalErrorType('not-installed')
        } else if (result.error?.message.includes('permission')) {
          setInstallModalErrorType('permission-denied')
        } else {
          setInstallModalErrorType('protocol-not-registered')
        }
      }
      
      // Show modal immediately
      setShowInstallModal(true)
    }
  }, [teamName, machine, repository, runningPlugins, isContainerMenu, containerId, containerName])

  // Generate different menu items based on whether this is a container menu
  const menuItems: any[] = isContainerMenu ? [
    {
      key: 'container-terminal',
      icon: <CodeOutlined style={styles.icon.small} />,
      label: (
        <span style={styles.body}>
          {t('resources:localActions.openContainerTerminal')}
        </span>
      ),
      onClick: () => handleOpenInDesktop(undefined, 'terminal'),
      'data-testid': `local-actions-container-terminal-${containerId}`
    },
    {
      type: 'divider'
    },
    {
      key: 'container-logs',
      icon: <BuildOutlined style={styles.icon.small} />,
      label: (
        <span style={styles.body}>
          {t('resources:localActions.viewContainerLogs')}
        </span>
      ),
      onClick: () => handleOpenInDesktop(undefined, 'logs'),
      'data-testid': `local-actions-container-logs-${containerId}`
    },
    {
      key: 'container-stats',
      icon: <BuildOutlined style={styles.icon.small} />,
      label: (
        <span style={styles.body}>
          {t('resources:localActions.containerStats')}
        </span>
      ),
      onClick: () => handleOpenInDesktop(undefined, 'stats'),
      'data-testid': `local-actions-container-stats-${containerId}`
    }
  ] : [
    {
      key: 'open',
      icon: <DesktopOutlined style={styles.icon.small} />,
      label: (
        <span style={styles.body}>
          {t('resources:localActions.openInDesktop')}
        </span>
      ),
      onClick: () => handleOpenInDesktop(),
      'data-testid': `local-actions-open-${repository}`
    },
    {
      type: 'divider'
    },
    {
      key: 'sync',
      icon: <SyncOutlined style={styles.icon.small} />,
      label: (
        <span style={styles.body}>
          {t('resources:localActions.openFileSync')}
        </span>
      ),
      onClick: () => handleOpenInDesktop('sync'),
      'data-testid': `local-actions-sync-${repository}`
    },
    {
      key: 'terminal',
      icon: <CodeOutlined style={styles.icon.small} />,
      label: (
        <span style={styles.body}>
          {t('resources:localActions.openTerminal')}
        </span>
      ),
      onClick: () => handleOpenInDesktop('terminal'),
      'data-testid': `local-actions-terminal-${repository}`
    },
    {
      key: 'plugin',
      icon: <ApiOutlined style={styles.icon.small} />,
      label: (
        <span style={styles.body}>
          {t('resources:localActions.openPluginManager')}
        </span>
      ),
      onClick: () => handleOpenInDesktop('plugin'),
      disabled: runningPlugins.length === 0,
      title: runningPlugins.length === 0 ? t('resources:localActions.noPluginsRunning') : undefined,
      'data-testid': `local-actions-plugin-${repository}`
    },
    {
      key: 'browser',
      icon: <FolderOpenOutlined style={styles.icon.small} />,
      label: (
        <span style={styles.body}>
          {t('resources:localActions.openFileBrowser')}
        </span>
      ),
      onClick: () => handleOpenInDesktop('browser'),
      'data-testid': `local-actions-browser-${repository}`
    },
    {
      type: 'divider'
    },
    {
      key: 'cli-commands',
      icon: <BuildOutlined style={styles.icon.small} />,
      label: (
        <span style={styles.body}>
          {t('resources:localActions.showCLICommands')}
        </span>
      ),
      onClick: () => setShowCommandModal(true),
      'data-testid': `local-actions-cli-commands-${repository}`
    }
  ]

  return (
    <>
      <Dropdown
        menu={{
          items: menuItems,
          'data-testid': `local-actions-menu-${repository}`
        }} 
        trigger={['click']}
        disabled={disabled || isCheckingProtocol}
        data-testid={`local-actions-dropdown-container-${repository}`}
      >
        <Tooltip title={isContainerMenu ? t('resources:localActions.containerLocal') : t('resources:localActions.local')}>
          <Button
            size="small"
            icon={<DesktopOutlined style={styles.icon.small} />}
            loading={isCheckingProtocol}
            style={{
              ...styles.buttonSecondary,
              ...styles.touchTargetSmall,
              display: 'flex',
              alignItems: 'center',
              gap: '4px'
            }}
            data-testid={isContainerMenu ? `local-actions-dropdown-${containerId}` : `local-actions-dropdown-${repository}`}
            aria-label={isContainerMenu ? t('resources:localActions.containerLocal') : t('resources:localActions.local')}
          />
        </Tooltip>
      </Dropdown>

      <PipInstallationModal
        visible={showInstallModal}
        onClose={() => setShowInstallModal(false)}
        errorType={installModalErrorType}
      />

      {/* Only show command modal for repository menus, not container menus */}
      {!isContainerMenu && (
        <LocalCommandModal
          visible={showCommandModal}
          onClose={() => setShowCommandModal(false)}
          machine={machine}
          repository={repository}
          userEmail={userEmail || currentUserEmail || ''}
          pluginContainers={pluginContainers}
        />
      )}
    </>
  )
}