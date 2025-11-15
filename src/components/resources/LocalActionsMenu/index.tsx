import React, { useCallback, useState } from 'react'
import { Dropdown, Tooltip, message } from 'antd'
import type { MenuProps } from 'antd'
import type { ItemType } from 'antd/es/menu/hooks/useItems'
import {
  DesktopOutlined,
  CodeOutlined,
  BuildOutlined,
  FileTextOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useSelector } from 'react-redux'
import { protocolUrlService, type ProtocolAction, type ContainerParams } from '@/services/protocolUrlService'
import { PipInstallationModal } from '../PipInstallationModal'
import { LocalCommandModal } from '../LocalCommandModal'
import type { RootState } from '@/store/store'
import type { PluginContainer } from '@/types'
import { IconWrapper, MenuLabel, TriggerButton } from './styles'

type ContainerMenuAction = 'terminal' | 'logs' | 'stats'

type MenuItemWithTestId = ItemType & { ['data-testid']?: string }

interface LocalActionsMenuProps {
  machine: string
  repository?: string
  teamName?: string
  disabled?: boolean
  userEmail?: string
  pluginContainers?: PluginContainer[]
  containerId?: string
  containerName?: string
  containerState?: string
  isContainerMenu?: boolean
  isMachineOnlyMenu?: boolean
}

const createMenuIcon = (IconComponent: React.ElementType, size: 'sm' | 'md' = 'sm') => (
  <IconWrapper $size={size}>
    <IconComponent />
  </IconWrapper>
)

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
  const { t } = useTranslation()
  const [showInstallModal, setShowInstallModal] = useState(false)
  const [installModalErrorType, setInstallModalErrorType] = useState<
    'not-installed' | 'protocol-not-registered' | 'permission-denied'
  >('not-installed')
  const [isCheckingProtocol, setIsCheckingProtocol] = useState(false)
  const [showCommandModal, setShowCommandModal] = useState(false)

  const currentUserEmail = useSelector((state: RootState) => state.auth.user?.email)

  const handleOpenInDesktop = useCallback(
    async (action?: ProtocolAction, containerAction?: ContainerMenuAction) => {
      const baseParams = {
        team: teamName,
        machine,
        repository: isMachineOnlyMenu ? '' : repository ?? '',
      }

      let url: string
      try {
        if (isContainerMenu && containerId) {
          const containerParams: ContainerParams = {
            containerId,
            containerName,
            action: containerAction ?? 'terminal',
          }

          if (containerAction) {
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
          } else {
            url = await protocolUrlService.generateDesktopUrl(baseParams, containerParams)
          }
        } else if (action) {
          if (action === 'terminal') {
            url = await protocolUrlService.generateTerminalUrl(baseParams)
          } else if (action === 'desktop') {
            url = await protocolUrlService.generateDesktopUrl(baseParams)
          } else if (action === 'vscode') {
            url = await protocolUrlService.generateVSCodeUrl(baseParams)
          } else {
            url = await protocolUrlService.generateUrl(baseParams)
          }
        } else {
          url = await protocolUrlService.generateDesktopUrl(baseParams)
        }
      } catch (error) {
        console.error('Failed to generate protocol URL:', error)
        message.error('Failed to create secure connection for desktop app')
        return
      }

      setIsCheckingProtocol(true)
      const result = await protocolUrlService.openUrl(url)
      setIsCheckingProtocol(false)

      if (!result.success) {
        try {
          const protocolStatus = await protocolUrlService.checkProtocolStatus()

          if (protocolStatus.available) {
            setInstallModalErrorType('permission-denied')
          } else if (protocolStatus.errorReason?.includes('not registered')) {
            setInstallModalErrorType('protocol-not-registered')
          } else {
            setInstallModalErrorType('not-installed')
          }
        } catch {
          if (result.error?.type === 'timeout') {
            setInstallModalErrorType('not-installed')
          } else if (result.error?.message.includes('permission')) {
            setInstallModalErrorType('permission-denied')
          } else {
            setInstallModalErrorType('protocol-not-registered')
          }
        }

        setShowInstallModal(true)
      }
    },
    [teamName, machine, repository, isContainerMenu, containerId, containerName, isMachineOnlyMenu]
  )

  const buildContainerMenuItems = (): MenuItemWithTestId[] => {
    const items: MenuItemWithTestId[] = []
    const isRunning = containerState === 'running'

    if (isRunning) {
      items.push({
        key: 'container-terminal',
        icon: createMenuIcon(CodeOutlined),
        label: <MenuLabel>{t('resources:localActions.openContainerTerminal')}</MenuLabel>,
        onClick: () => handleOpenInDesktop(undefined, 'terminal'),
        'data-testid': `local-actions-container-terminal-${containerId}`,
      })
    }

    if (items.length > 0) {
      items.push({ type: 'divider' })
    }

    items.push({
      key: 'container-logs',
      icon: createMenuIcon(BuildOutlined),
      label: <MenuLabel>{t('resources:localActions.viewContainerLogs')}</MenuLabel>,
      onClick: () => handleOpenInDesktop(undefined, 'logs'),
      'data-testid': `local-actions-container-logs-${containerId}`,
    })

    if (isRunning) {
      items.push({
        key: 'container-stats',
        icon: createMenuIcon(BuildOutlined),
        label: <MenuLabel>{t('resources:localActions.containerStats')}</MenuLabel>,
        onClick: () => handleOpenInDesktop(undefined, 'stats'),
        'data-testid': `local-actions-container-stats-${containerId}`,
      })
    }

    return items
  }

  const buildMachineMenuItems = (): MenuItemWithTestId[] => [
    {
      key: 'open',
      icon: createMenuIcon(DesktopOutlined),
      label: <MenuLabel>{t('resources:localActions.openInDesktop')}</MenuLabel>,
      onClick: () => handleOpenInDesktop(),
      'data-testid': `local-actions-open-${repository}`,
    },
    {
      key: 'vscode',
      icon: createMenuIcon(FileTextOutlined),
      label: <MenuLabel>{t('resources:localActions.openInVSCode')}</MenuLabel>,
      onClick: () => handleOpenInDesktop('vscode'),
      'data-testid': `local-actions-vscode-${repository}`,
    },
    {
      key: 'terminal',
      icon: createMenuIcon(CodeOutlined),
      label: <MenuLabel>{t('resources:localActions.openTerminal')}</MenuLabel>,
      onClick: () => handleOpenInDesktop('terminal'),
      'data-testid': `local-actions-terminal-${repository}`,
    },
    { type: 'divider' },
    {
      key: 'cli-commands',
      icon: createMenuIcon(BuildOutlined),
      label: <MenuLabel>{t('resources:localActions.showCLICommands')}</MenuLabel>,
      onClick: () => setShowCommandModal(true),
      'data-testid': `local-actions-cli-commands-${repository}`,
    },
  ]

  const menuItems = isContainerMenu ? buildContainerMenuItems() : buildMachineMenuItems()
  const menuConfig: MenuProps = { items: menuItems as ItemType[] }

  const tooltipLabel = isContainerMenu
    ? t('resources:localActions.containerLocal')
    : t('resources:localActions.local')

  const triggerTestId = isContainerMenu
    ? `local-actions-dropdown-${containerId}`
    : `local-actions-dropdown-${repository}`

  return (
    <>
      <Dropdown
        menu={menuConfig}
        trigger={['click']}
        disabled={disabled || isCheckingProtocol}
        data-testid={`local-actions-dropdown-container-${repository}`}
      >
        <Tooltip title={tooltipLabel}>
          <TriggerButton
            icon={createMenuIcon(DesktopOutlined, 'md')}
            loading={isCheckingProtocol}
            disabled={disabled || isCheckingProtocol}
            data-testid={triggerTestId}
            aria-label={tooltipLabel}
          />
        </Tooltip>
      </Dropdown>

      <PipInstallationModal
        visible={showInstallModal}
        onClose={() => setShowInstallModal(false)}
        errorType={installModalErrorType}
      />

      {!isContainerMenu && (
        <LocalCommandModal
          visible={showCommandModal}
          onClose={() => setShowCommandModal(false)}
          machine={machine}
          repository={repository}
          userEmail={userEmail ?? currentUserEmail ?? ''}
          pluginContainers={pluginContainers}
        />
      )}
    </>
  )
}
