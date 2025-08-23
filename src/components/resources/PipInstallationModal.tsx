import React, { useState, useCallback, useMemo } from 'react'
import { 
  Modal, 
  Typography, 
  Space, 
  Alert, 
  Button, 
  Collapse, 
  Checkbox,
  Tabs,
  Tag,
  Divider,
  message
} from 'antd'
import { 
  RocketOutlined,
  CopyOutlined,
  CheckOutlined,
  InfoCircleOutlined,
  CodeOutlined,
  QuestionCircleOutlined,
  WarningOutlined,
  WindowsOutlined,
  AppleOutlined,
  DesktopOutlined
} from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { pipInstallationService, InstallOptions } from '@/services/pipInstallationService'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing, createModalStyle } from '@/utils/styleConstants'

const { Text, Title, Paragraph } = Typography
const { Panel } = Collapse

interface PipInstallationModalProps {
  visible: boolean
  onClose: () => void
  errorType?: 'not-installed' | 'protocol-not-registered' | 'permission-denied'
}

interface CommandDisplayProps {
  command: string
  description?: string
  showCopy?: boolean
}

const CommandDisplay: React.FC<CommandDisplayProps> = ({ command, description, showCopy = true }) => {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(command)
      setCopied(true)
      message.success('Command copied to clipboard!')
      // Reset copy state immediately after user interaction
      setCopied(false)
    } catch (error) {
      message.error('Failed to copy command')
    }
  }, [command])

  const formattedCommands = pipInstallationService.formatCommandsForDisplay([command])
  const { isCommand, isComment } = formattedCommands[0]

  return (
    <div style={{ marginBottom: spacing('XS') }} data-testid="pip-install-command-display">
      {description && <Text type="secondary" style={{ display: 'block', marginBottom: spacing('MICRO') }}>{description}</Text>}
      <div style={{ 
        background: '#f5f5f5', 
        border: '1px solid #d9d9d9',
        borderRadius: DESIGN_TOKENS.BORDER_RADIUS.SM,
        padding: `${spacing('XS')}px ${spacing('SM')}px`,
        fontFamily: 'monospace',
        fontSize: DESIGN_TOKENS.FONT_SIZE.SM,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between'
      }}
      data-testid="pip-install-command-text">
        <Text 
          code 
          style={{ 
            background: 'transparent',
            border: 'none',
            color: isComment ? '#8c8c8c' : isCommand ? '#1890ff' : 'inherit'
          }}
        >
          {command}
        </Text>
        {showCopy && isCommand && (
          <Button 
            size="small" 
            icon={copied ? <CheckOutlined /> : <CopyOutlined />}
            style={{ marginLeft: spacing('XS') }}
            onClick={handleCopy}
            data-testid="pip-install-command-copy"
          />
        )}
      </div>
    </div>
  )
}

export const PipInstallationModal: React.FC<PipInstallationModalProps> = ({
  visible,
  onClose,
  errorType = 'not-installed'
}) => {
  const { t } = useTranslation()
  const styles = useComponentStyles()
  const [includeGui, setIncludeGui] = useState(true)
  const [useUserInstall, setUseUserInstall] = useState(false)
  const [activeTab, setActiveTab] = useState('quick')

  const platformInstructions = useMemo(
    () => pipInstallationService.getPlatformInstructions(),
    []
  )

  const installOptions: InstallOptions = {
    includeGui,
    useUser: useUserInstall
  }

  const installCommands = pipInstallationService.getInstallationCommands(installOptions)
  const virtualEnvInstructions = pipInstallationService.getVirtualEnvInstructions()
  const uninstallInstructions = pipInstallationService.getUninstallInstructions()

  const handleCopyAllCommands = () => {
    const allCommands = [
      installCommands.install,
      ...installCommands.postInstall.filter(cmd => !cmd.includes('Restart')),
      ...installCommands.verify
    ].join('\n')
    
    navigator.clipboard.writeText(allCommands)
    message.success('All commands copied to clipboard!')
  }

  const renderPlatformIcon = () => {
    switch (platformInstructions.platform) {
      case 'windows':
        return <WindowsOutlined />
      case 'macos':
        return <AppleOutlined />
      default:
        return <DesktopOutlined />
    }
  }

  const renderQuickInstall = () => (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Alert
        message={t('resources:pipInstall.quickInstallTitle')}
        description={t('resources:pipInstall.quickInstallDesc')}
        type="info"
        showIcon
        icon={<RocketOutlined />}
        data-testid="pip-install-quick-alert"
      />

      <div>
        <Title level={5}>{t('resources:pipInstall.step1Install')}</Title>
        <CommandDisplay 
          command={pipInstallationService.generateInstallCommand(installOptions)}
          description={t('resources:pipInstall.installCommandDesc')}
        />
        
        <Space style={{ marginTop: spacing('XS') }}>
          <Checkbox 
            checked={includeGui} 
            onChange={(e) => setIncludeGui(e.target.checked)}
            data-testid="pip-install-gui-checkbox"
          >
            {t('resources:pipInstall.includeGuiSupport')}
          </Checkbox>
          <Checkbox 
            checked={useUserInstall} 
            onChange={(e) => setUseUserInstall(e.target.checked)}
            data-testid="pip-install-user-checkbox"
          >
            {t('resources:pipInstall.userInstallOnly')}
          </Checkbox>
        </Space>
      </div>

      <div>
        <Title level={5}>{t('resources:pipInstall.step2Register')}</Title>
        <CommandDisplay 
          command={pipInstallationService.generateProtocolCommand()}
          description={t('resources:pipInstall.registerCommandDesc')}
        />
      </div>

      <div>
        <Title level={5}>{t('resources:pipInstall.step3Verify')}</Title>
        {installCommands.verify.map((cmd, index) => (
          <CommandDisplay key={index} command={cmd} />
        ))}
      </div>

      <Alert
        message={
          <Space>
            {renderPlatformIcon()}
            {t('resources:pipInstall.platformSpecific', { platform: platformInstructions.platform })}
          </Space>
        }
        description={
          <ul style={{ marginBottom: 0, paddingLeft: 20 }}>
            {platformInstructions.notes.map((note, index) => (
              <li key={index}>{note}</li>
            ))}
          </ul>
        }
        type="warning"
        data-testid="pip-install-platform-alert"
      />

      <Button 
        type="primary" 
        icon={<CopyOutlined />} 
        onClick={handleCopyAllCommands}
        block
        data-testid="pip-install-copy-all-button"
        style={styles.buttonPrimary}
      >
        {t('resources:pipInstall.copyAllCommands')}
      </Button>
    </Space>
  )

  const renderAdvancedOptions = () => (
    <Collapse defaultActiveKey={[]} data-testid="pip-install-advanced-collapse">
      <Panel 
        header={t('resources:pipInstall.virtualEnvironment')} 
        key="venv"
        extra={<Tag color="green">{t('resources:pipInstall.recommended')}</Tag>}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text>{virtualEnvInstructions.description}</Text>
          {virtualEnvInstructions.commands.map((cmd, index) => (
            <CommandDisplay key={index} command={cmd} showCopy={!cmd.startsWith('#')} />
          ))}
        </Space>
      </Panel>

      <Panel header={t('resources:pipInstall.specificVersion')} key="version">
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text>{t('resources:pipInstall.versionDesc')}</Text>
          <CommandDisplay command="pip install rediacc==1.0.0" />
          <CommandDisplay command="pip install rediacc>=1.0.0,<2.0.0" />
          <CommandDisplay 
            command="pip install --upgrade rediacc" 
            description={t('resources:pipInstall.upgradeDesc')}
          />
        </Space>
      </Panel>

      <Panel header={t('resources:pipInstall.uninstall')} key="uninstall">
        <Space direction="vertical" style={{ width: '100%' }}>
          <Text>{uninstallInstructions.description}</Text>
          {uninstallInstructions.commands.map((cmd, index) => (
            <CommandDisplay key={index} command={cmd} showCopy={!cmd.startsWith('#')} />
          ))}
        </Space>
      </Panel>
    </Collapse>
  )

  const renderTroubleshooting = () => (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <Alert
        message={t('resources:pipInstall.commonIssues')}
        type="info"
        showIcon
        data-testid="pip-install-issues-alert"
      />

      <Collapse defaultActiveKey={['pip-not-found']} data-testid="pip-install-troubleshooting-collapse">
        <Panel 
          header={t('resources:pipInstall.pipNotFound')} 
          key="pip-not-found"
          extra={<Tag color="red">{t('resources:pipInstall.error')}</Tag>}
        >
          {(() => {
            const troubleshooting = pipInstallationService.getTroubleshootingCommands('pip-not-found')
            return (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Text>{troubleshooting.description}</Text>
                {troubleshooting.commands.map((cmd, index) => (
                  <CommandDisplay key={index} command={cmd} showCopy={!cmd.startsWith('#')} />
                ))}
              </Space>
            )
          })()}
        </Panel>

        <Panel 
          header={t('resources:pipInstall.permissionDenied')} 
          key="permission"
          extra={<Tag color="orange">{t('resources:pipInstall.warning')}</Tag>}
        >
          {(() => {
            const troubleshooting = pipInstallationService.getTroubleshootingCommands('permission-denied')
            return (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Text>{troubleshooting.description}</Text>
                {troubleshooting.commands.map((cmd, index) => (
                  <CommandDisplay key={index} command={cmd} showCopy={!cmd.startsWith('#')} />
                ))}
              </Space>
            )
          })()}
        </Panel>

        <Panel 
          header={t('resources:pipInstall.pythonVersion')} 
          key="python-version"
        >
          {(() => {
            const troubleshooting = pipInstallationService.getTroubleshootingCommands('python-version')
            return (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Text>{troubleshooting.description}</Text>
                {troubleshooting.commands.map((cmd, index) => (
                  <CommandDisplay key={index} command={cmd} showCopy={!cmd.startsWith('#')} />
                ))}
              </Space>
            )
          })()}
        </Panel>
      </Collapse>

      <Alert
        message={t('resources:pipInstall.stillNeedHelp')}
        description={
          <Space direction="vertical">
            <Text>
              {t('resources:pipInstall.checkDocs')}: {' '}
              <a 
                href="https://www.rediacc.com/docs/cli/installation" 
                target="_blank" 
                rel="noopener noreferrer"
                data-testid="pip-install-docs-link"
              >
                {t('resources:pipInstall.installationGuide')}
              </a>
            </Text>
            <Text>
              {t('resources:pipInstall.reportIssue')}: {' '}
              <a 
                href="https://github.com/rediacc/cli/issues" 
                target="_blank" 
                rel="noopener noreferrer"
                data-testid="pip-install-github-link"
              >
                GitHub Issues
              </a>
            </Text>
          </Space>
        }
        type="info"
        data-testid="pip-install-help-alert"
      />
    </Space>
  )

  const getModalTitle = () => {
    switch (errorType) {
      case 'protocol-not-registered':
        return t('resources:pipInstall.protocolNotRegisteredTitle')
      case 'permission-denied':
        return t('resources:pipInstall.permissionDeniedTitle')
      default:
        return t('resources:pipInstall.installRediaccCli')
    }
  }

  return (
    <Modal
      title={
        <Space>
          <RocketOutlined />
          {getModalTitle()}
        </Space>
      }
      open={visible}
      onCancel={onClose}
      footer={[
        <Button 
          key="close" 
          onClick={onClose} 
          data-testid="pip-install-close-button"
          style={styles.buttonSecondary}
        >
          {t('common:close')}
        </Button>
      ]}
      style={createModalStyle(DESIGN_TOKENS.DIMENSIONS.MODAL_WIDTH_LG)}
      data-testid="pip-install-modal"
    >
      <Tabs 
        activeKey={activeTab} 
        onChange={setActiveTab}
        data-testid="pip-install-tabs"
        items={[
          {
            key: 'quick',
            label: (
              <Space>
                <RocketOutlined />
                {t('resources:pipInstall.quickInstall')}
              </Space>
            ),
            children: renderQuickInstall()
          },
          {
            key: 'advanced',
            label: (
              <Space>
                <CodeOutlined />
                {t('resources:pipInstall.advancedOptions')}
              </Space>
            ),
            children: renderAdvancedOptions()
          },
          {
            key: 'troubleshooting',
            label: (
              <Space>
                <QuestionCircleOutlined />
                {t('resources:pipInstall.troubleshooting')}
              </Space>
            ),
            children: renderTroubleshooting()
          }
        ]}
      />
    </Modal>
  )
}