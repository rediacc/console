import React, { useState } from 'react'
import { Modal, Steps, Upload, Button, Alert, Table, Checkbox, Space, Typography, Spin, Tag, Tooltip } from 'antd'
import { UploadOutlined, CloudOutlined, QuestionCircleOutlined, InfoCircleOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import { showMessage } from '@/utils/messages'
import { useCreateStorage } from '@/api/queries/storage'
import { useStorage } from '@/api/queries/storage'
import storageProviders from '@/data/storageProviders.json'
import type { UploadFile } from 'antd/es/upload'

const { Step } = Steps
const { Text, Title, Paragraph } = Typography

interface RcloneConfig {
  name: string
  type: string
  config: Record<string, any>
}

interface ImportStatus {
  name: string
  status: 'pending' | 'success' | 'error' | 'skipped'
  message?: string
  exists?: boolean
  selected?: boolean
}

interface RcloneImportWizardProps {
  open: boolean
  onClose: () => void
  teamName: string
  onImportComplete?: () => void
}

const RcloneImportWizard: React.FC<RcloneImportWizardProps> = ({
  open,
  onClose,
  teamName,
  onImportComplete
}) => {
  const { t } = useTranslation(['resources', 'common'])
  const [currentStep, setCurrentStep] = useState(0)
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [parsedConfigs, setParsedConfigs] = useState<RcloneConfig[]>([])
  const [importStatuses, setImportStatuses] = useState<ImportStatus[]>([])
  const [isImporting, setIsImporting] = useState(false)
  const [parsingError, setParsingError] = useState<string | null>(null)

  const createStorageMutation = useCreateStorage()
  const { data: existingStorages = [] } = useStorage(teamName)

  // Parse INI-style rclone config
  const parseRcloneConfig = (content: string): RcloneConfig[] => {
    const configs: RcloneConfig[] = []
    const lines = content.split('\n')
    let currentSection: string | null = null
    let currentConfig: Record<string, any> = {}

    for (const line of lines) {
      const trimmedLine = line.trim()
      
      // Skip empty lines and comments
      if (!trimmedLine || trimmedLine.startsWith('#') || trimmedLine.startsWith(';')) {
        continue
      }

      // Check if it's a section header
      const sectionMatch = trimmedLine.match(/^\[(.+)\]$/)
      if (sectionMatch) {
        // Save previous section if exists
        if (currentSection && currentConfig.type) {
          configs.push({
            name: currentSection,
            type: currentConfig.type,
            config: { ...currentConfig }
          })
        }
        
        // Start new section
        currentSection = sectionMatch[1]
        currentConfig = {}
      } else if (currentSection) {
        // Parse key-value pair
        const kvMatch = trimmedLine.match(/^([^=]+)=(.*)$/)
        if (kvMatch) {
          const key = kvMatch[1].trim()
          const value = kvMatch[2].trim()
          
          // Try to parse JSON values (for complex objects like tokens)
          try {
            currentConfig[key] = JSON.parse(value)
          } catch {
            // If not JSON, store as string
            currentConfig[key] = value
          }
        }
      }
    }

    // Don't forget the last section
    if (currentSection && currentConfig.type) {
      configs.push({
        name: currentSection,
        type: currentConfig.type,
        config: { ...currentConfig }
      })
    }

    return configs
  }

  // Map rclone config to our storage provider format
  const mapRcloneToStorageProvider = (rcloneConfig: RcloneConfig): Record<string, any> | null => {
    const { type, config } = rcloneConfig
    
    // Map rclone type to our provider type
    const providerMapping: Record<string, string> = {
      'drive': 'drive',
      'onedrive': 'onedrive',
      's3': 's3',
      'b2': 'b2',
      'mega': 'mega',
      'dropbox': 'dropbox',
      'box': 'box',
      'azureblob': 'azureblob',
      'swift': 'swift',
      'webdav': 'webdav',
      'ftp': 'ftp',
      'sftp': 'sftp'
    }

    const provider = providerMapping[type]
    if (!provider) {
      return null
    }

    // Storage vault should contain all fields directly at top level
    // matching the format used in data.json
    const storageVault: Record<string, any> = {}

    // Process all config fields
    Object.entries(config).forEach(([key, value]) => {
      if (key === 'type') {
        // Replace 'type' with 'provider' for our system
        storageVault.provider = provider
      } else {
        // Parse JSON strings if needed
        let processedValue = value
        if (typeof value === 'string') {
          // Check if it's a JSON string that needs to be parsed
          if ((key === 'token' || key.endsWith('_token')) && value.startsWith('{')) {
            try {
              processedValue = JSON.parse(value)
            } catch {
              processedValue = value
            }
          }
        }
        
        // Add field directly to vault
        storageVault[key] = processedValue
      }
    })
    
    // Ensure provider is set if not already
    if (!storageVault.provider) {
      storageVault.provider = provider
    }
    
    return storageVault
  }

  const handleFileUpload = async (file: File) => {
    setParsingError(null)
    
    try {
      const content = await file.text()
      const configs = parseRcloneConfig(content)
      
      if (configs.length === 0) {
        setParsingError(t('resources:storage.import.noConfigsFound'))
        return false
      }

      setParsedConfigs(configs)
      
      // Initialize import statuses
      const statuses: ImportStatus[] = configs.map(config => {
        const exists = existingStorages.some(s => s.storageName === config.name)
        return {
          name: config.name,
          status: 'pending',
          exists,
          selected: !exists // Only select non-existing by default
        }
      })
      setImportStatuses(statuses)
      
      setCurrentStep(1)
      return false
    } catch (error) {
      setParsingError(t('resources:storage.import.parseError'))
      return false
    }
  }

  const handleImport = async () => {
    setIsImporting(true)
    const selectedConfigs = parsedConfigs.filter((_, index) => 
      importStatuses[index].selected
    )

    for (let i = 0; i < selectedConfigs.length; i++) {
      const config = selectedConfigs[i]
      const statusIndex = parsedConfigs.findIndex(c => c.name === config.name)
      
      try {
        const mappedConfig = mapRcloneToStorageProvider(config)
        if (!mappedConfig) {
          setImportStatuses(prev => {
            const newStatuses = [...prev]
            newStatuses[statusIndex] = {
              ...newStatuses[statusIndex],
              status: 'error',
              message: t('resources:storage.import.unsupportedProvider', { type: config.type })
            }
            return newStatuses
          })
          continue
        }

        // Create storage vault content
        const storageVault = JSON.stringify(mappedConfig)

        await createStorageMutation.mutateAsync({
          teamName,
          storageName: config.name,
          storageVault
        })

        setImportStatuses(prev => {
          const newStatuses = [...prev]
          newStatuses[statusIndex] = {
            ...newStatuses[statusIndex],
            status: 'success',
            message: t('resources:storage.import.imported')
          }
          return newStatuses
        })
      } catch (error: any) {
        setImportStatuses(prev => {
          const newStatuses = [...prev]
          newStatuses[statusIndex] = {
            ...newStatuses[statusIndex],
            status: 'error',
            message: error.message || t('resources:storage.import.importError')
          }
          return newStatuses
        })
      }
    }

    setIsImporting(false)
    setCurrentStep(2)
  }

  const handleClose = () => {
    // Reset state
    setCurrentStep(0)
    setFileList([])
    setParsedConfigs([])
    setImportStatuses([])
    setIsImporting(false)
    setParsingError(null)
    
    // Call callbacks
    if (currentStep === 2 && importStatuses.some(s => s.status === 'success')) {
      onImportComplete?.()
    }
    onClose()
  }

  const toggleSelection = (index: number) => {
    setImportStatuses(prev => {
      const newStatuses = [...prev]
      newStatuses[index] = {
        ...newStatuses[index],
        selected: !newStatuses[index].selected
      }
      return newStatuses
    })
  }

  const selectAll = (selected: boolean) => {
    setImportStatuses(prev => 
      prev.map(status => ({ ...status, selected }))
    )
  }

  const columns = [
    {
      title: (
        <Checkbox
          checked={importStatuses.every(s => s.selected)}
          indeterminate={importStatuses.some(s => s.selected) && !importStatuses.every(s => s.selected)}
          onChange={(e) => selectAll(e.target.checked)}
          disabled={currentStep === 2}
        />
      ),
      dataIndex: 'selected',
      key: 'selected',
      width: 50,
      render: (_: any, record: ImportStatus, index: number) => (
        <Checkbox
          checked={record.selected}
          onChange={() => toggleSelection(index)}
          disabled={currentStep === 2}
        />
      )
    },
    {
      title: t('resources:storage.storageName'),
      dataIndex: 'name',
      key: 'name',
      render: (name: string, record: ImportStatus) => (
        <Space>
          <CloudOutlined />
          <Text strong>{name}</Text>
          {record.exists && (
            <Tooltip title={t('resources:storage.import.alreadyExists')}>
              <Tag color="warning">
                <InfoCircleOutlined /> {t('resources:storage.import.exists')}
              </Tag>
            </Tooltip>
          )}
        </Space>
      )
    },
    {
      title: t('resources:storage.provider'),
      key: 'provider',
      width: 120,
      render: (_: any, record: ImportStatus) => {
        const config = parsedConfigs.find(c => c.name === record.name)
        if (!config) return null
        
        // Capitalize provider name for display
        const displayName = config.type.charAt(0).toUpperCase() + config.type.slice(1)
        return <Tag color="blue">{displayName}</Tag>
      }
    },
    {
      title: t('resources:storage.import.status'),
      dataIndex: 'status',
      key: 'status',
      width: 150,
      render: (status: string, record: ImportStatus) => {
        if (currentStep < 2) return null
        
        const statusConfig = {
          pending: { color: 'default', text: t('resources:storage.import.pending') },
          success: { color: 'success', text: t('resources:storage.import.success') },
          error: { color: 'error', text: t('resources:storage.import.error') },
          skipped: { color: 'warning', text: t('resources:storage.import.skipped') }
        }[status] || { color: 'default', text: status }

        return (
          <Space direction="vertical" size="small">
            <Tag color={statusConfig.color}>{statusConfig.text}</Tag>
            {record.message && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {record.message}
              </Text>
            )}
          </Space>
        )
      }
    }
  ]

  const renderStepContent = () => {
    switch (currentStep) {
      case 0:
        return (
          <div style={{ padding: '20px 0' }}>
            <Alert
              message={t('resources:storage.import.instructions')}
              description={
                <div>
                  <Paragraph>
                    {t('resources:storage.import.instructionsDetail')}
                  </Paragraph>
                  <Paragraph>
                    <Text code>rclone config file</Text>
                  </Paragraph>
                  <Paragraph>
                    {t('resources:storage.import.uploadPrompt')}
                  </Paragraph>
                </div>
              }
              type="info"
              showIcon
              icon={<InfoCircleOutlined />}
              style={{ marginBottom: 20 }}
            />
            
            <Upload.Dragger
              accept=".conf"
              fileList={fileList}
              beforeUpload={handleFileUpload}
              onChange={({ fileList }) => setFileList(fileList)}
              maxCount={1}
            >
              <p className="ant-upload-drag-icon">
                <UploadOutlined />
              </p>
              <p className="ant-upload-text">
                {t('resources:storage.import.dragDropText')}
              </p>
              <p className="ant-upload-hint">
                {t('resources:storage.import.supportedFormats')}
              </p>
            </Upload.Dragger>

            {parsingError && (
              <Alert
                message={parsingError}
                type="error"
                showIcon
                style={{ marginTop: 16 }}
              />
            )}
          </div>
        )

      case 1:
        return (
          <div>
            <Alert
              message={t('resources:storage.import.selectStorages')}
              description={t('resources:storage.import.selectDescription')}
              type="info"
              showIcon
              style={{ marginBottom: 16 }}
            />
            
            <Table
              dataSource={importStatuses}
              columns={columns}
              rowKey="name"
              pagination={false}
              size="small"
            />
          </div>
        )

      case 2:
        return (
          <div>
            {isImporting ? (
              <div style={{ textAlign: 'center', padding: '40px 0' }}>
                <Spin size="large" />
                <Title level={4} style={{ marginTop: 16 }}>
                  {t('resources:storage.import.importing')}
                </Title>
              </div>
            ) : (
              <>
                <Alert
                  message={t('resources:storage.import.complete')}
                  description={t('resources:storage.import.completeDescription')}
                  type="success"
                  showIcon
                  style={{ marginBottom: 16 }}
                />
                
                <Table
                  dataSource={importStatuses}
                  columns={columns}
                  rowKey="name"
                  pagination={false}
                  size="small"
                />
              </>
            )}
          </div>
        )

      default:
        return null
    }
  }

  return (
    <Modal
      title={
        <Space>
          <CloudOutlined />
          {t('resources:storage.import.title')}
        </Space>
      }
      open={open}
      onCancel={handleClose}
      width={800}
      footer={
        currentStep === 0 ? (
          <Button onClick={handleClose}>{t('common:actions.cancel')}</Button>
        ) : currentStep === 1 ? (
          <>
            <Button onClick={() => setCurrentStep(0)}>
              {t('common:actions.back')}
            </Button>
            <Button onClick={handleClose}>
              {t('common:actions.cancel')}
            </Button>
            <Button
              type="primary"
              onClick={handleImport}
              disabled={!importStatuses.some(s => s.selected)}
              loading={isImporting}
            >
              {t('resources:storage.import.importSelected')}
            </Button>
          </>
        ) : (
          <Button type="primary" onClick={handleClose}>
            {t('common:actions.close')}
          </Button>
        )
      }
    >
      <Steps current={currentStep} style={{ marginBottom: 24 }}>
        <Step title={t('resources:storage.import.step1')} />
        <Step title={t('resources:storage.import.step2')} />
        <Step title={t('resources:storage.import.step3')} />
      </Steps>

      {renderStepContent()}
    </Modal>
  )
}

export default RcloneImportWizard