import React, { useState, useEffect } from 'react'
import { Modal, Tabs, Form, Input, Checkbox, Button, Space, Typography, message, Radio, theme } from 'antd'
import { CopyOutlined, CodeOutlined, WindowsOutlined, AppleOutlined, DesktopOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'

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

  // Auto-detect API URL from current browser location
  useEffect(() => {
    if (visible) {
      const protocol = window.location.protocol
      const host = window.location.host
      setApiUrl(`${protocol}//${host}/api`)
    }
  }, [visible])





  const buildTermCommand = () => {
    const setEnvCmd = os === 'windows'
      ? `set REDIACC_API_URL=${apiUrl}`
      : `export REDIACC_API_URL="${apiUrl}"`

    const baseCommand = useDocker
      ? `docker run -it --rm -e REDIACC_API_URL="${apiUrl}" rediacc/cli term`
      : (os === 'windows' ? 'rediacc.bat term' : 'rediacc term')
    const machineParam = `--machine ${machine}`
    const repoParam = repository ? ` --repo ${repository}` : ''
    const commandParam = termCommand ? ` --command "${termCommand}"` : ''

    const termCmd = `${baseCommand} ${machineParam}${repoParam}${commandParam}`

    return useDocker ? termCmd : `${setEnvCmd} && ${termCmd}`
  }

  const buildDesktopCommand = () => {
    const setEnvCmd = os === 'windows'
      ? `set REDIACC_API_URL=${apiUrl}`
      : `export REDIACC_API_URL="${apiUrl}"`

    const baseCommand = useDocker
      ? `docker run -it --rm -e REDIACC_API_URL="${apiUrl}" rediacc/cli desktop`
      : (os === 'windows' ? 'rediacc.bat desktop' : 'rediacc desktop')
    const teamParam = ' --team Default'  // Default team as placeholder
    const machineParam = ` --machine ${machine}`
    const repoParam = repository ? ` --repo ${repository}` : ''

    const desktopCmd = `${baseCommand}${teamParam}${machineParam}${repoParam}`

    return useDocker ? desktopCmd : `${setEnvCmd} && ${desktopCmd}`
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      message.success(t('common:copiedToClipboard'))
    }).catch(() => {
      message.error(t('common:copyFailed'))
    })
  }

  const getCommand = () => {
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
          <Radio.Group value={os} onChange={(e) => setOs(e.target.value)}>
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
          <Text strong>{t('resources:localCommandBuilder.generatedCommand')}:</Text>
          <Paragraph
            code
            copyable={{
              text: getCommand(),
              icon: <CopyOutlined />
            }}
            style={{ marginTop: 8, marginBottom: 8 }}
          >
            {getCommand()}
          </Paragraph>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {t('resources:localCommandBuilder.apiUrl')}: {apiUrl}
          </Text>
        </div>

        <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
          <Button onClick={onClose}>
            {t('common:close')}
          </Button>
          <Button
            type="primary"
            icon={<CopyOutlined />}
            onClick={() => copyToClipboard(getCommand())}
          >
            {t('resources:localCommandBuilder.copyCommand')}
          </Button>
        </Space>
      </div>
    </Modal>
  )
}