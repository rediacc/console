import React, { useState, useCallback } from 'react'
import { Dropdown, Button, Menu, message } from 'antd'
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
      
      // Show modal after a short delay
      setTimeout(() => {
        setShowInstallModal(true)
      }, 500)
    }
  }, [token, teamName, machine, repository, runningPlugins])

  const menuItems: any[] = [
    {
      key: 'open',
      icon: <DesktopOutlined />,
      label: t('resources:localActions.openInDesktop'),
      onClick: () => handleOpenInDesktop()
    },
    {
      type: 'divider'
    },
    {
      key: 'sync',
      icon: <SyncOutlined />,
      label: t('resources:localActions.openFileSync'),
      onClick: () => handleOpenInDesktop('sync')
    },
    {
      key: 'terminal',
      icon: <CodeOutlined />,
      label: t('resources:localActions.openTerminal'),
      onClick: () => handleOpenInDesktop('terminal')
    },
    {
      key: 'plugin',
      icon: <ApiOutlined />,
      label: t('resources:localActions.openPluginManager'),
      onClick: () => handleOpenInDesktop('plugin'),
      disabled: runningPlugins.length === 0,
      title: runningPlugins.length === 0 ? t('resources:localActions.noPluginsRunning') : undefined
    },
    {
      key: 'browser',
      icon: <FolderOpenOutlined />,
      label: t('resources:localActions.openFileBrowser'),
      onClick: () => handleOpenInDesktop('browser')
    }
  ]

  const menu = <Menu items={menuItems} />

  return (
    <>
      <Dropdown 
        overlay={menu} 
        trigger={['click']}
        disabled={disabled || isCheckingProtocol}
      >
        <Button 
          size="small" 
          icon={<DesktopOutlined />}
          loading={isCheckingProtocol}
        >
          {t('resources:localActions.local')} <DownOutlined />
        </Button>
      </Dropdown>

      <PipInstallationModal
        visible={showInstallModal}
        onClose={() => setShowInstallModal(false)}
        errorType={installModalErrorType}
      />
    </>
  )
}