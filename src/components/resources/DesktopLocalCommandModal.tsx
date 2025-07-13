import React, { useState, useEffect } from 'react'
import { Modal, Tabs, Form, Input, Select, Checkbox, Button, Space, Typography, message, Radio, Alert } from 'antd'
import { CopyOutlined, CodeOutlined, DesktopOutlined, WindowsOutlined, AppleOutlined, FolderOpenOutlined, PlayCircleOutlined, ApiOutlined, SyncOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { useDesktopMode } from '@/hooks/useDesktopMode'
import { unifiedApiClient } from '@/api/unifiedClient'
import {  } from '@tauri-apps/api'
import * as dialog from "@tauri-apps/plugin-dialog"

const { Text, Paragraph } = Typography
const { Option } = Select
const { TabPane } = Tabs

interface DesktopLocalCommandModalProps {
  visible: boolean
  onClose: () => void
  machine: string
  repository: string
  token: string
  userEmail: string
  pluginContainers?: Array<{
    name: string
    image: string
    status: string
    [key: string]: any
  }>
}

export const DesktopLocalCommandModal: React.FC<DesktopLocalCommandModalProps> = ({
  visible,
  onClose,
  machine,
  repository,
  token,
  userEmail,
  pluginContainers = []
}) => {
  const { t } = useTranslation()
  const { isDesktop, hasPython, pythonVersion, hasCli } = useDesktopMode()
  const [activeTab, setActiveTab] = useState('plugin')
  const [executing, setExecuting] = useState(false)
  const [output, setOutput] = useState('')
  
  // Sync command state
  const [syncAction, setSyncAction] = useState<'upload' | 'download'>('upload')
  const [localPath, setLocalPath] = useState('')
  const [syncOptions, setSyncOptions] = useState({
    mirror: false,
    verify: false,
    confirm: false
  })
  
  // Terminal command state
  const [termCommand, setTermCommand] = useState('')
  
  // Plugin command state
  const [pluginAction, setPluginAction] = useState<'list' | 'connect' | 'connections'>('list')
  const [pluginName, setPluginName] = useState('')
  const [pluginPort, setPluginPort] = useState('')

  // Filter containers that are plugins (image contains 'rediacc/plugin')
  const availablePlugins = pluginContainers.filter(container => 
    container.image && container.image.includes('rediacc/plugin') && 
    container.status && container.status.toLowerCase().includes('running')
  )

  const handleBrowse = async () => {
    if (!isDesktop) return

    try {
      const selected = await dialog.open({
        directory: true,
        multiple: false,
        title: t('resources:localCommandBuilder.selectFolder')
      })
      
      if (selected && typeof selected === 'string') {
        setLocalPath(selected)
      }
    } catch (error) {
      // Failed to open dialog
    }
  }

  const executeSyncCommand = async () => {
    if (!isDesktop || !hasCli) {
      message.error(t('resources:localCommandBuilder.cliRequired'))
      return
    }

    setExecuting(true)
    setOutput('')

    try {
      const result = await unifiedApiClient.syncFiles(
        syncAction,
        machine,
        repository,
        localPath,
        {
          mirror: syncOptions.mirror,
          verify: syncOptions.verify,
          confirm: syncOptions.confirm
        }
      )

      setOutput(result.output + (result.error ? `\n\nErrors:\n${result.error}` : ''))
      
      if (result.success) {
        message.success(t('resources:localCommandBuilder.syncSuccess'))
      } else {
        message.error(t('resources:localCommandBuilder.syncFailed'))
      }
    } catch (error: any) {
      setOutput(`Error: ${error.message}`)
      message.error(error.message)
    } finally {
      setExecuting(false)
    }
  }

  const executeTermCommand = async () => {
    if (!isDesktop || !hasCli) {
      message.error(t('resources:localCommandBuilder.cliRequired'))
      return
    }

    if (!termCommand) {
      message.warning(t('resources:localCommandBuilder.enterCommand'))
      return
    }

    setExecuting(true)
    setOutput('')

    try {
      const result = await unifiedApiClient.executeTerminalCommand(
        machine,
        repository,
        termCommand
      )

      setOutput(result.output + (result.error ? `\n\nErrors:\n${result.error}` : ''))
      
      if (result.success) {
        message.success(t('resources:localCommandBuilder.commandSuccess'))
      } else {
        message.error(t('resources:localCommandBuilder.commandFailed'))
      }
    } catch (error: any) {
      setOutput(`Error: ${error.message}`)
      message.error(error.message)
    } finally {
      setExecuting(false)
    }
  }

  const executePluginCommand = async () => {
    if (!isDesktop || !hasCli) {
      message.error(t('resources:localCommandBuilder.cliRequired'))
      return
    }

    if (pluginAction === 'connect' && !pluginName) {
      message.warning(t('resources:localCommandBuilder.enterPluginName'))
      return
    }

    setExecuting(true)
    setOutput('')

    try {
      const options: any = {}
      if (pluginAction === 'connect') {
        options.plugin = pluginName
        if (pluginPort) {
          options.port = parseInt(pluginPort, 10)
        }
      }

      const result = await unifiedApiClient.executePluginCommand(
        pluginAction,
        machine,
        repository,
        options
      )

      setOutput(result.output + (result.error ? `\n\nErrors:\n${result.error}` : ''))
      
      if (result.success) {
        message.success(t('resources:localCommandBuilder.pluginSuccess'))
      } else {
        message.error(t('resources:localCommandBuilder.pluginFailed'))
      }
    } catch (error: any) {
      setOutput(`Error: ${error.message}`)
      message.error(error.message)
    } finally {
      setExecuting(false)
    }
  }

  const copyOutput = () => {
    navigator.clipboard.writeText(output).then(() => {
      message.success(t('common:copiedToClipboard'))
    }).catch(() => {
      message.error(t('common:copyFailed'))
    })
  }

  return (
    <Modal
      title={t('resources:localCommandBuilder.title')}
      open={visible}
      onCancel={onClose}
      width={900}
      footer={null}
    >
      <div style={{ marginBottom: 16 }}>
        <Text type="secondary">
          {t('resources:localCommandBuilder.desktopDescription', { machine, repository })}
        </Text>
      </div>

      {isDesktop && (
        <Alert
          message={t('resources:localCommandBuilder.desktopMode')}
          description={
            <Space direction="vertical" size="small">
              <Text>Python: {hasPython ? pythonVersion : t('resources:localCommandBuilder.notInstalled')}</Text>
              <Text>Rediacc CLI: {hasCli ? t('resources:localCommandBuilder.installed') : t('resources:localCommandBuilder.notInstalled')}</Text>
            </Space>
          }
          type={hasPython && hasCli ? 'success' : 'warning'}
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane tab={t('resources:localCommandBuilder.pluginTab')} key="plugin" icon={<ApiOutlined />}>
          <Form layout="vertical">
            <Form.Item label={t('resources:localCommandBuilder.pluginAction')}>
              <Select value={pluginAction} onChange={setPluginAction} disabled={executing}>
                <Option value="list">{t('resources:localCommandBuilder.listPlugins')}</Option>
                <Option value="connect">{t('resources:localCommandBuilder.connectPlugin')}</Option>
                <Option value="connections">{t('resources:localCommandBuilder.pluginListConnections')}</Option>
              </Select>
            </Form.Item>

            {pluginAction === 'connect' && (
              <>
                <Form.Item 
                  label={t('resources:localCommandBuilder.pluginName')}
                  help={t('resources:localCommandBuilder.pluginNameHelp')}
                  required
                >
                  <Select
                    placeholder={t('resources:localCommandBuilder.pluginNamePlaceholder')}
                    value={pluginName}
                    onChange={setPluginName}
                    disabled={executing}
                    notFoundContent={availablePlugins.length === 0 ? t('resources:localCommandBuilder.noPluginsRunning') : null}
                  >
                    {availablePlugins.map((container) => (
                      <Option key={container.name} value={container.name}>
                        {container.name}
                      </Option>
                    ))}
                  </Select>
                </Form.Item>

                <Form.Item 
                  label={t('resources:localCommandBuilder.pluginPort')}
                  help={t('resources:localCommandBuilder.pluginPortHelp')}
                >
                  <Input
                    placeholder={t('resources:localCommandBuilder.pluginPortPlaceholder')}
                    value={pluginPort}
                    onChange={(e) => setPluginPort(e.target.value)}
                    type="number"
                    disabled={executing}
                    autoComplete="off"
                  />
                </Form.Item>
              </>
            )}

            {isDesktop && hasCli && (
              <Form.Item>
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  onClick={executePluginCommand}
                  loading={executing}
                  disabled={pluginAction === 'connect' && !pluginName}
                >
                  {t('resources:localCommandBuilder.executePlugin')}
                </Button>
              </Form.Item>
            )}
          </Form>
        </TabPane>

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
                disabled={executing}
                onPressEnter={executeTermCommand}
                autoComplete="off"
              />
            </Form.Item>

            {isDesktop && hasCli && (
              <Form.Item>
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  onClick={executeTermCommand}
                  loading={executing}
                  disabled={!termCommand}
                >
                  {t('resources:localCommandBuilder.executeCommand')}
                </Button>
              </Form.Item>
            )}
          </Form>
        </TabPane>

        <TabPane tab={t('resources:localCommandBuilder.syncTab')} key="sync" icon={<SyncOutlined />}>
          <Form layout="vertical">
            <Form.Item label={t('resources:localCommandBuilder.action')}>
              <Select value={syncAction} onChange={setSyncAction} disabled={executing}>
                <Option value="upload">{t('resources:localCommandBuilder.upload')}</Option>
                <Option value="download">{t('resources:localCommandBuilder.download')}</Option>
              </Select>
            </Form.Item>

            <Form.Item 
              label={t('resources:localCommandBuilder.localPath')}
              help={t('resources:localCommandBuilder.localPathHelp')}
            >
              <Space.Compact style={{ width: '100%' }}>
                <Input
                  placeholder={t('resources:localCommandBuilder.localPathPlaceholder')}
                  value={localPath}
                  onChange={(e) => setLocalPath(e.target.value)}
                  disabled={executing}
                  autoComplete="off"
                />
                {isDesktop && (
                  <Button 
                    icon={<FolderOpenOutlined />} 
                    onClick={handleBrowse}
                    disabled={executing}
                  >
                    {t('resources:localCommandBuilder.browse')}
                  </Button>
                )}
              </Space.Compact>
            </Form.Item>

            <Form.Item label={t('resources:localCommandBuilder.options')}>
              <Space direction="vertical">
                <Checkbox
                  checked={syncOptions.mirror}
                  onChange={(e) => {
                    const mirrorChecked = e.target.checked
                    setSyncOptions(prev => ({
                      ...prev,
                      mirror: mirrorChecked,
                      // When mirror is checked, also check confirm
                      confirm: mirrorChecked ? true : prev.confirm
                    }))
                  }}
                  disabled={executing}
                >
                  {t('resources:localCommandBuilder.mirror')}
                  <Text type="secondary" style={{ marginLeft: 8 }}>
                    {t('resources:localCommandBuilder.mirrorHelp')}
                  </Text>
                </Checkbox>
                <Checkbox
                  checked={syncOptions.verify}
                  onChange={(e) => setSyncOptions({ ...syncOptions, verify: e.target.checked })}
                  disabled={executing}
                >
                  {t('resources:localCommandBuilder.verify')}
                  <Text type="secondary" style={{ marginLeft: 8 }}>
                    {t('resources:localCommandBuilder.verifyHelp')}
                  </Text>
                </Checkbox>
                <Checkbox
                  checked={syncOptions.confirm}
                  onChange={(e) => setSyncOptions({ ...syncOptions, confirm: e.target.checked })}
                  disabled={executing || syncOptions.mirror}
                >
                  {t('resources:localCommandBuilder.confirm')}
                  <Text type="secondary" style={{ marginLeft: 8 }}>
                    {t('resources:localCommandBuilder.confirmHelp')}
                  </Text>
                </Checkbox>
              </Space>
            </Form.Item>

            {isDesktop && hasCli && (
              <Form.Item>
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  onClick={executeSyncCommand}
                  loading={executing}
                  disabled={!localPath}
                >
                  {t('resources:localCommandBuilder.executeSync')}
                </Button>
              </Form.Item>
            )}
          </Form>
        </TabPane>
      </Tabs>

      {output && (
        <div style={{ marginTop: 24 }}>
          <div style={{ 
            padding: 16, 
            backgroundColor: '#f5f5f5', 
            borderRadius: 8,
            marginBottom: 16
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <Text strong>{t('resources:localCommandBuilder.output')}:</Text>
              <Button
                size="small"
                icon={<CopyOutlined />}
                onClick={copyOutput}
              >
                {t('common:copy')}
              </Button>
            </div>
            <pre style={{ 
              margin: 0, 
              maxHeight: 300, 
              overflow: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word'
            }}>
              {output}
            </pre>
          </div>
        </div>
      )}

      <Space style={{ width: '100%', justifyContent: 'flex-end', marginTop: 16 }}>
        <Button onClick={onClose}>
          {t('common:close')}
        </Button>
      </Space>
    </Modal>
  )
}