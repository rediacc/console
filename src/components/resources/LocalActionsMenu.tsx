import React, { useState, useCallback } from 'react'
import { Dropdown, Button, Menu, message, Tooltip } from 'antd'
import { 
  DesktopOutlined, 
  SyncOutlined, 
  CodeOutlined, 
  ApiOutlined, 
  FolderOpenOutlined,
  DownOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { protocolUrlService, ProtocolAction } from '@/services/protocolUrlService'
import { PipInstallationModal } from './PipInstallationModal'
import { useComponentStyles } from '@/hooks/useComponentStyles'

interface LocalActionsMenuProps {
  machine: string
  repository: string
  token: string
  teamName?: string
  disabled?: boolean
  pluginContainers?: Array<{
    name: string
    image: string
    status: string
  }>
}

export const LocalActionsMenu: React.FC<LocalActionsMenuProps> = ({
  machine,
  repository,
  token,
  teamName = 'Default',
  disabled = false,
  pluginContainers = []
}) => {
  const { t } = useTranslation()
  const [showInstallModal, setShowInstallModal] = useState(false)
  const [installModalErrorType, setInstallModalErrorType] = useState<'not-installed' | 'protocol-not-registered' | 'permission-denied'>('not-installed')
  const [isCheckingProtocol, setIsCheckingProtocol] = useState(false)
  
  const styles = useComponentStyles()

  // Filter running plugin containers
  const runningPlugins = pluginContainers.filter(container => 
    container.image?.includes('rediacc/plugin') && 
    container.status?.toLowerCase().includes('running')
  )

  const handleOpenInDesktop = useCallback(async (action?: ProtocolAction) => {
    const baseParams = {
      token,
      team: teamName,
      machine,
      repository
    }

    let url: string
    if (action) {
      // Generate action-specific URL
      switch (action) {
        case 'sync':
          url = protocolUrlService.generateSyncUrl(baseParams)
          break
        case 'terminal':
          url = protocolUrlService.generateTerminalUrl(baseParams)
          break
        case 'plugin':
          url = protocolUrlService.generatePluginUrl(baseParams, {
            // Auto-select first running plugin if available
            name: runningPlugins[0]?.name
          })
          break
        case 'browser':
          url = protocolUrlService.generateBrowserUrl(baseParams)
          break
        default:
          url = protocolUrlService.generateUrl(baseParams)
      }
    } else {
      // Just navigate to the repository
      url = protocolUrlService.generateUrl(baseParams)
    }

    // Try to open the URL
    setIsCheckingProtocol(true)
    const result = await protocolUrlService.openUrl(url)
    setIsCheckingProtocol(false)

    // If protocol failed, show installation modal
    if (!result.success) {
      // Determine error type based on the error
      if (result.error?.type === 'timeout') {
        setInstallModalErrorType('not-installed')
      } else if (result.error?.message.includes('permission')) {
        setInstallModalErrorType('permission-denied')
      } else {
        setInstallModalErrorType('protocol-not-registered')
      }
      
      // Show modal immediately
      setShowInstallModal(true)
    }
  }, [token, teamName, machine, repository, runningPlugins])

  const menuItems: any[] = [
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
    }
  ]

  const menu = <Menu items={menuItems} data-testid={`local-actions-menu-${repository}`} />

  return (
    <>
      <Dropdown 
        overlay={menu} 
        trigger={['click']}
        disabled={disabled || isCheckingProtocol}
        data-testid={`local-actions-dropdown-container-${repository}`}
      >
        <Tooltip title={t('resources:localActions.local')}>
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
            data-testid={`local-actions-dropdown-${repository}`}
            aria-label={t('resources:localActions.local')}
          />
        </Tooltip>
      </Dropdown>

      <PipInstallationModal
        visible={showInstallModal}
        onClose={() => setShowInstallModal(false)}
        errorType={installModalErrorType}
      />
    </>
  )
}