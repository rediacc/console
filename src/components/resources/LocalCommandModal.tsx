import React, { useState, useEffect } from 'react'
import { Modal, Tabs, Form, Input, Checkbox, Button, Space, Typography, message, Radio, theme, Spin } from 'antd'
import { CopyOutlined, CodeOutlined, WindowsOutlined, AppleOutlined, DesktopOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { createFreshForkToken } from '@/services/forkTokenService'

const { Text, Paragraph } = Typography
const { TabPane } = Tabs

interface LocalCommandModalProps {
  visible: boolean
  onClose: () => void
  machine: string
  repository?: string
  userEmail: string
  pluginContainers?: Array<{
    name: string
    image: string
    status: string
    [key: string]: any
  }>
}

export const LocalCommandModal: React.FC<LocalCommandModalProps> = ({
  visible,
  onClose,
  machine,
  repository,
  userEmail,
  pluginContainers = []
}) => {
  const { t } = useTranslation()
  const { token: themeToken } = theme.useToken()
  const [activeTab, setActiveTab] = useState('terminal')
  const [os, setOs] = useState<'unix' | 'windows'>('unix')
  const [useDocker, setUseDocker] = useState(false)
  const [apiUrl, setApiUrl] = useState('')

  // Terminal command state
  const [termCommand, setTermCommand] = useState('')

  // Token state - no longer pre-generate tokens
  const [isGeneratingToken, setIsGeneratingToken] = useState(false)
  const [tokenError, setTokenError] = useState<string>('')

  // Auto-detect API URL from current browser location
  useEffect(() => {
    if (visible) {
      const protocol = window.location.protocol
      const host = window.location.host
      setApiUrl(`${protocol}//${host}/api`)
    }
  }, [visible])

  // Generate fork token only when needed (on copy)
  const generateForkTokenForCopy = async (action: string): Promise<string> => {
    setIsGeneratingToken(true)
    setTokenError('')

    try {
      const token = await createFreshForkToken(action)
      return token
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to generate token'
      setTokenError(errorMessage)
      console.error('Failed to generate fork token:', error)
      message.error(`Token generation failed: ${errorMessage}`)
      throw error
    } finally {
      setIsGeneratingToken(false)
    }
  }

  // Clear error state when modal closes
  useEffect(() => {
    if (!visible) {
      setTokenError('')
    }
  }, [visible])





  const buildTermCommand = (token: string = '<SECURE_TOKEN>') => {
    const apiEnvCmd = os === 'windows'
      ? `set REDIACC_API_URL=${apiUrl}`
      : `export REDIACC_API_URL="${apiUrl}"`

    const tokenEnvCmd = os === 'windows'
      ? `set REDIACC_TOKEN=${token}`
      : `export REDIACC_TOKEN="${token}"`

    const baseCommand = useDocker
      ? `docker run -it --rm -e REDIACC_TOKEN="${token}" -e REDIACC_API_URL="${apiUrl}" rediacc/cli term`
      : (os === 'windows' ? 'rediacc.bat term' : 'rediacc term')
    const machineParam = `--machine ${machine}`
    const repoParam = repository ? ` --repo ${repository}` : ''
    const commandParam = termCommand ? ` --command "${termCommand}"` : ''

    const termCmd = `${baseCommand} ${machineParam}${repoParam}${commandParam}`

    return useDocker ? termCmd : `${tokenEnvCmd} && ${apiEnvCmd} && ${termCmd}`
  }

  const buildDesktopCommand = (token: string = '<SECURE_TOKEN>') => {
    const apiEnvCmd = os === 'windows'
      ? `set REDIACC_API_URL=${apiUrl}`
      : `export REDIACC_API_URL="${apiUrl}"`

    const tokenEnvCmd = os === 'windows'
      ? `set REDIACC_TOKEN=${token}`
      : `export REDIACC_TOKEN="${token}"`

    const baseCommand = useDocker
      ? `docker run -it --rm -e REDIACC_TOKEN="${token}" -e REDIACC_API_URL="${apiUrl}" rediacc/cli desktop`
      : (os === 'windows' ? 'rediacc.bat desktop' : 'rediacc desktop')
    const teamParam = ' --team Default'  // Default team as placeholder
    const machineParam = ` --machine ${machine}`
    const repoParam = repository ? ` --repo ${repository}` : ''

    const desktopCmd = `${baseCommand}${teamParam}${machineParam}${repoParam}`

    return useDocker ? desktopCmd : `${tokenEnvCmd} && ${apiEnvCmd} && ${desktopCmd}`
  }

  // Fallback versions without token (for error cases)
  const buildTermCommandWithoutToken = () => {
    const apiEnvCmd = os === 'windows'
      ? `set REDIACC_API_URL=${apiUrl}`
      : `export REDIACC_API_URL="${apiUrl}"`

    const baseCommand = useDocker
      ? `docker run -it --rm -e REDIACC_API_URL="${apiUrl}" rediacc/cli term`
      : (os === 'windows' ? 'rediacc.bat term' : 'rediacc term')
    const machineParam = `--machine ${machine}`
    const repoParam = repository ? ` --repo ${repository}` : ''
    const commandParam = termCommand ? ` --command "${termCommand}"` : ''

    const termCmd = `${baseCommand} ${machineParam}${repoParam}${commandParam}`

    return useDocker ? termCmd : `${apiEnvCmd} && ${termCmd}`
  }

  const buildDesktopCommandWithoutToken = () => {
    const apiEnvCmd = os === 'windows'
      ? `set REDIACC_API_URL=${apiUrl}`
      : `export REDIACC_API_URL="${apiUrl}"`

    const baseCommand = useDocker
      ? `docker run -it --rm -e REDIACC_API_URL="${apiUrl}" rediacc/cli desktop`
      : (os === 'windows' ? 'rediacc.bat desktop' : 'rediacc desktop')
    const teamParam = ' --team Default'  // Default team as placeholder
    const machineParam = ` --machine ${machine}`
    const repoParam = repository ? ` --repo ${repository}` : ''

    const desktopCmd = `${baseCommand}${teamParam}${machineParam}${repoParam}`

    return useDocker ? desktopCmd : `${apiEnvCmd} && ${desktopCmd}`
  }

  const copyToClipboard = async () => {
    try {
      setIsGeneratingToken(true)

      // Generate fresh token for the current action
      const token = await generateForkTokenForCopy(activeTab)

      // Build command with real token
      const commandWithToken = activeTab === 'desktop'
        ? buildDesktopCommand(token)
        : buildTermCommand(token)

      // Copy to clipboard
      await navigator.clipboard.writeText(commandWithToken)
      message.success(t('common:copiedToClipboard'))

      // Close modal after successful copy to prevent multiple token generations
      onClose()
    } catch (error) {
      // If token generation fails, copy command without token (fallback)
      try {
        // Build command without token environment variables
        const fallbackCommand = activeTab === 'desktop'
          ? buildDesktopCommandWithoutToken()
          : buildTermCommandWithoutToken()

        await navigator.clipboard.writeText(fallbackCommand)
        message.warning('Copied without secure token - please login manually')

        // Close modal after fallback copy as well
        onClose()
      } catch (clipboardError) {
        message.error(t('common:copyFailed'))
      }
    } finally {
      setIsGeneratingToken(false)
    }
  }

  const getCommand = () => {
    // Always show placeholder token in preview
    switch (activeTab) {
      case 'terminal':
        return buildTermCommand()
      case 'desktop':
        return buildDesktopCommand()
      default:
        return buildTermCommand()
    }
  }

  return (
    <Modal
      title={t('resources:localCommandBuilder.title')}
      open={visible}
      onCancel={onClose}
      width={800}
      footer={null}
    >
      <div style={{ marginBottom: 16 }}>
        <Text type="secondary">
          {t('resources:localCommandBuilder.description', { machine, repository })}
        </Text>
      </div>

      <Form layout="vertical" style={{ marginBottom: 16 }}>
        <Form.Item label={t('resources:localCommandBuilder.operatingSystem')}>
          <Radio.Group value={os} onChange={(e: any) => setOs(e.target.value)}>
            <Radio.Button value="unix">
              <AppleOutlined /> {t('resources:localCommandBuilder.unixLinuxMac')}
            </Radio.Button>
            <Radio.Button value="windows">
              <WindowsOutlined /> {t('resources:localCommandBuilder.windows')}
            </Radio.Button>
          </Radio.Group>
        </Form.Item>
      </Form>

      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane tab={t('resources:localCommandBuilder.terminalTab')} key="terminal" icon={<CodeOutlined />}>
          <Form layout="vertical">
            <Form.Item
              label={t('resources:localCommandBuilder.command')}
              help={t('resources:localCommandBuilder.commandHelp')}
            >
              <Input
                placeholder="docker ps"
                value={termCommand}
                onChange={(e) => setTermCommand(e.target.value)}
                autoComplete="off"
              />
            </Form.Item>
          </Form>
        </TabPane>

        <TabPane tab={t('resources:localCommandBuilder.desktopTab')} key="desktop" icon={<DesktopOutlined />}>
          <Form layout="vertical">
            <Form.Item help={t('resources:localCommandBuilder.desktopHelp')}>
              <Text type="secondary">
                {t('resources:localCommandBuilder.desktopDescription')}
              </Text>
            </Form.Item>
          </Form>
        </TabPane>
      </Tabs>

      <div style={{ marginTop: 24 }}>
        <Form.Item>
          <Checkbox
            checked={useDocker}
            onChange={(e) => setUseDocker(e.target.checked)}
          >
            {t('resources:localCommandBuilder.useDocker')}
            <Text type="secondary" style={{ marginLeft: 8 }}>
              {t('resources:localCommandBuilder.useDockerHelp')}
            </Text>
          </Checkbox>
        </Form.Item>

        <div style={{
          padding: 16,
          backgroundColor: themeToken.colorFillAlter,
          borderRadius: 8,
          marginBottom: 16,
          border: `1px solid ${themeToken.colorBorder}`
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <Text strong>{t('resources:localCommandBuilder.generatedCommand')}:</Text>
            {isGeneratingToken && (
              <Spin size="small" />
            )}
          </div>

          {tokenError ? (
            <div style={{ padding: '12px 0' }}>
              <Text type="danger">Token generation failed: {tokenError}</Text>
              <br />
              <Text type="secondary" style={{ fontSize: 12 }}>
                Copy will attempt without secure token. You may need to login manually.
              </Text>
            </div>
          ) : null}

          <Paragraph
            code
            copyable={{
              text: getCommand(),
              icon: <CopyOutlined />,
              onCopy: copyToClipboard
            }}
            style={{ marginTop: 8, marginBottom: 8 }}
          >
            {getCommand()}
          </Paragraph>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t('resources:localCommandBuilder.apiUrl')}: {apiUrl}
            </Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              Token: Secure token will be generated on copy
            </Text>
          </div>
        </div>

        <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
          <Button onClick={onClose}>
            {t('common:close')}
          </Button>
          <Button
            type="primary"
            icon={<CopyOutlined />}
            onClick={copyToClipboard}
            disabled={isGeneratingToken}
            loading={isGeneratingToken}
          >
            {t('resources:localCommandBuilder.copyCommand')}
          </Button>
        </Space>
      </div>
    </Modal>
  )
}