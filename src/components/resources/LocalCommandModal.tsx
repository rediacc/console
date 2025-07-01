import React, { useState, useEffect } from 'react'
import { Modal, Tabs, Form, Input, Select, Checkbox, Button, Space, Typography, message, Radio } from 'antd'
import { CopyOutlined, CodeOutlined, DesktopOutlined, WindowsOutlined, AppleOutlined } from '@ant-design/icons'
import { useTranslation } from 'react-i18next'

const { Text, Paragraph } = Typography
const { Option } = Select
const { TabPane } = Tabs

interface LocalCommandModalProps {
  visible: boolean
  onClose: () => void
  machine: string
  repository: string
  token: string
  userEmail: string
}

export const LocalCommandModal: React.FC<LocalCommandModalProps> = ({
  visible,
  onClose,
  machine,
  repository,
  token,
  userEmail
}) => {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState('sync')
  const [useDocker, setUseDocker] = useState(false)
  const [os, setOs] = useState<'unix' | 'windows'>('unix')
  const [useLogin, setUseLogin] = useState(false)
  const [apiUrl, setApiUrl] = useState('')
  
  // Sync command state
  const [syncAction, setSyncAction] = useState<'upload' | 'download'>('upload')
  const [localPath, setLocalPath] = useState('')
  const [syncOptions, setSyncOptions] = useState({
    mirror: false,
    verify: false,
    confirm: false,
    dev: false
  })
  
  // Terminal command state
  const [termCommand, setTermCommand] = useState('')
  const [termDev, setTermDev] = useState(false)

  // Auto-detect API URL from current browser location
  useEffect(() => {
    if (visible) {
      const protocol = window.location.protocol
      const host = window.location.host
      setApiUrl(`${protocol}//${host}/api`)
    }
  }, [visible])

  const formatPath = (path: string) => {
    if (os === 'windows' && path.includes('/')) {
      // Convert Unix paths to Windows paths
      return path.replace(/\//g, '\\')
    }
    return path
  }

  const buildLoginCommand = () => {
    const setEnvCmd = os === 'windows' 
      ? `set REDIACC_API_URL=${apiUrl}` 
      : `export REDIACC_API_URL="${apiUrl}"`
    
    // Use email from props and let CLI prompt for password
    const loginCmd = useDocker 
      ? `docker run -it --rm -e REDIACC_API_URL="${apiUrl}" rediacc/cli login --email="${userEmail}"`
      : `rediacc-cli login --email="${userEmail}"`
    
    return `${setEnvCmd} && ${loginCmd}`
  }

  const buildSyncCommand = () => {
    const localPathFormatted = formatPath(localPath || (os === 'windows' ? 'C:\\path\\to\\local' : '/path/to/local'))
    
    let baseCommand
    if (useDocker) {
      const volumeMount = os === 'windows' 
        ? `-v "${localPathFormatted}:/data"`
        : `-v "${localPathFormatted}:/data"`
      baseCommand = `docker run --rm ${volumeMount} -e REDIACC_API_URL="${apiUrl}" rediacc/cli sync`
    } else {
      baseCommand = 'rediacc-cli-sync'
    }
    
    const action = syncAction
    // Only include token if not using login
    const tokenParam = useLogin ? '' : `--token=${token}`
    const machineParam = `--machine=${machine}`
    const repoParam = `--repo=${repository}`
    const localParam = useDocker ? '--local=/data' : `--local="${localPathFormatted}"`
    
    const options = []
    if (syncOptions.mirror) options.push('--mirror')
    if (syncOptions.verify) options.push('--verify')
    if (syncOptions.confirm) options.push('--confirm')
    if (syncOptions.dev) options.push('--dev')
    
    const optionsStr = options.length > 0 ? ' ' + options.join(' ') : ''
    
    // Build the command with proper spacing
    const cmdParts = [baseCommand, action]
    if (tokenParam) cmdParts.push(tokenParam)
    cmdParts.push(machineParam, repoParam, localParam)
    if (optionsStr) cmdParts.push(optionsStr.trim())
    
    const syncCmd = cmdParts.join(' ')
    
    // Include login command if using login
    if (useLogin) {
      const connector = os === 'windows' ? ' && ' : ' && '
      return buildLoginCommand() + connector + syncCmd
    }
    
    return syncCmd
  }

  const buildTermCommand = () => {
    const baseCommand = useDocker 
      ? `docker run -it --rm -e REDIACC_API_URL="${apiUrl}" rediacc/cli term`
      : 'rediacc-cli-term'
    
    // Only include token if not using login
    const tokenParam = useLogin ? '' : `--token=${token}`
    const machineParam = `--machine=${machine}`
    const repoParam = `--repo=${repository}`
    const commandParam = termCommand ? ` --command="${termCommand}"` : ''
    const devParam = termDev ? ' --dev' : ''
    
    // Build the command with proper spacing
    const cmdParts = [baseCommand]
    if (tokenParam) cmdParts.push(tokenParam)
    cmdParts.push(machineParam, repoParam)
    if (commandParam.trim()) cmdParts.push(commandParam.trim())
    if (devParam.trim()) cmdParts.push(devParam.trim())
    
    const termCmd = cmdParts.join(' ')
    
    // Include login command if using login
    if (useLogin) {
      const connector = os === 'windows' ? ' && ' : ' && '
      return buildLoginCommand() + connector + termCmd
    }
    
    return termCmd
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      message.success(t('common:copiedToClipboard'))
    }).catch(() => {
      message.error(t('common:copyFailed'))
    })
  }

  const getCommand = () => {
    return activeTab === 'sync' ? buildSyncCommand() : buildTermCommand()
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

        <Form.Item>
          <Checkbox
            checked={useLogin}
            onChange={(e) => setUseLogin(e.target.checked)}
          >
            {t('resources:localCommandBuilder.useLoginAuth')}
            <Text type="secondary" style={{ marginLeft: 8 }}>
              {t('resources:localCommandBuilder.useLoginAuthHelp', { email: userEmail })}
            </Text>
          </Checkbox>
        </Form.Item>
      </Form>

      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane tab={t('resources:localCommandBuilder.syncTab')} key="sync" icon={<CodeOutlined />}>
          <Form layout="vertical">
            <Form.Item label={t('resources:localCommandBuilder.action')}>
              <Select value={syncAction} onChange={setSyncAction}>
                <Option value="upload">{t('resources:localCommandBuilder.upload')}</Option>
                <Option value="download">{t('resources:localCommandBuilder.download')}</Option>
              </Select>
            </Form.Item>

            <Form.Item 
              label={t('resources:localCommandBuilder.localPath')}
              help={t('resources:localCommandBuilder.localPathHelp')}
            >
              <Input
                placeholder={os === 'windows' ? 'C:\\path\\to\\local\\folder' : '/path/to/local/folder'}
                value={localPath}
                onChange={(e) => setLocalPath(e.target.value)}
              />
            </Form.Item>

            <Form.Item label={t('resources:localCommandBuilder.options')}>
              <Space direction="vertical">
                <Checkbox
                  checked={syncOptions.mirror}
                  onChange={(e) => setSyncOptions({ ...syncOptions, mirror: e.target.checked })}
                >
                  {t('resources:localCommandBuilder.mirror')}
                  <Text type="secondary" style={{ marginLeft: 8 }}>
                    {t('resources:localCommandBuilder.mirrorHelp')}
                  </Text>
                </Checkbox>
                <Checkbox
                  checked={syncOptions.verify}
                  onChange={(e) => setSyncOptions({ ...syncOptions, verify: e.target.checked })}
                >
                  {t('resources:localCommandBuilder.verify')}
                  <Text type="secondary" style={{ marginLeft: 8 }}>
                    {t('resources:localCommandBuilder.verifyHelp')}
                  </Text>
                </Checkbox>
                <Checkbox
                  checked={syncOptions.confirm}
                  onChange={(e) => setSyncOptions({ ...syncOptions, confirm: e.target.checked })}
                >
                  {t('resources:localCommandBuilder.confirm')}
                  <Text type="secondary" style={{ marginLeft: 8 }}>
                    {t('resources:localCommandBuilder.confirmHelp')}
                  </Text>
                </Checkbox>
                <Checkbox
                  checked={syncOptions.dev}
                  onChange={(e) => setSyncOptions({ ...syncOptions, dev: e.target.checked })}
                >
                  {t('resources:localCommandBuilder.devMode')}
                  <Text type="secondary" style={{ marginLeft: 8 }}>
                    {t('resources:localCommandBuilder.devModeHelp')}
                  </Text>
                </Checkbox>
              </Space>
            </Form.Item>
          </Form>
        </TabPane>

        <TabPane tab={t('resources:localCommandBuilder.terminalTab')} key="terminal" icon={<DesktopOutlined />}>
          <Form layout="vertical">
            <Form.Item 
              label={t('resources:localCommandBuilder.command')}
              help={t('resources:localCommandBuilder.commandHelp')}
            >
              <Input
                placeholder="docker ps"
                value={termCommand}
                onChange={(e) => setTermCommand(e.target.value)}
              />
            </Form.Item>

            <Form.Item>
              <Checkbox
                checked={termDev}
                onChange={(e) => setTermDev(e.target.checked)}
              >
                {t('resources:localCommandBuilder.devMode')}
                <Text type="secondary" style={{ marginLeft: 8 }}>
                  {t('resources:localCommandBuilder.devModeHelp')}
                </Text>
              </Checkbox>
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
          backgroundColor: '#f5f5f5', 
          borderRadius: 8,
          marginBottom: 16
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