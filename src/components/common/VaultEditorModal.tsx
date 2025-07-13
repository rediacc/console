import React, { useState, useEffect, useRef } from 'react'
import { Modal, Button, Space, message, Typography, Tag, Upload } from 'antd'
import { InfoCircleOutlined, UploadOutlined, DownloadOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import VaultEditor from './VaultEditor'

const { Text } = Typography

interface VaultEditorModalProps {
  open: boolean
  onCancel: () => void
  onSave: (vault: string, version: number) => Promise<void>
  entityType: string
  title?: string
  initialVault?: string
  initialVersion?: number
  loading?: boolean
}

const VaultEditorModal: React.FC<VaultEditorModalProps> = ({
  open,
  onCancel,
  onSave,
  entityType,
  title = 'Configure Vault',
  initialVault = '{}',
  initialVersion = 1,
  loading = false,
}) => {
  const { t } = useTranslation('common')
  const [vaultData, setVaultData] = useState<Record<string, any>>({})
  const [vaultVersion, setVaultVersion] = useState(initialVersion)
  const [isValid, setIsValid] = useState(true) // Start with true to avoid blocking
  const [hasChanges, setHasChanges] = useState(false)
  const [validationErrors, setValidationErrors] = useState<string[]>([])
  const [showValidationErrors, setShowValidationErrors] = useState(false)
  const importExportHandlers = useRef<{ handleImport: (file: any) => boolean; handleExport: () => void } | null>(null)

  useEffect(() => {
    try {
      const parsed = JSON.parse(initialVault)
      setVaultData(parsed)
    } catch {
      setVaultData({})
    }
    setVaultVersion(initialVersion)
    setHasChanges(false)
    // Don't reset isValid to avoid blocking
    setValidationErrors([])
    setShowValidationErrors(false)
  }, [initialVault, initialVersion])

  const handleVaultChange = (data: Record<string, any>, changed: boolean) => {
    setVaultData(data)
    setHasChanges(changed)
  }

  const handleValidate = (valid: boolean, errors?: string[]) => {
    setIsValid(valid)
    setValidationErrors(errors || [])
  }

  const handleSave = async () => {
    console.log('=== VaultEditorModal handleSave ===')
    console.log('Is valid:', isValid)
    console.log('Vault data:', vaultData)
    console.log('Validation errors:', validationErrors)
    
    if (!isValid) {
      console.log('VaultEditorModal validation failed - showing error message')
      setShowValidationErrors(true)
      message.error(t('vaultEditor.pleaseFixErrors'))
      return
    }

    try {
      const vaultJson = JSON.stringify(vaultData)
      await onSave(vaultJson, vaultVersion)
      onCancel()
    } catch (error) {
      // Error handled by parent
    }
  }

  return (
    <Modal
      title={`${title} - ${entityType}`}
      open={open}
      onCancel={onCancel}
      width={900}
      footer={null}
      style={{ top: 20 }}
    >
      <Space direction="vertical" style={{ width: '100%' }} size={12}>
        <div 
          className="bg-tertiary"
          style={{ 
            padding: '8px 16px', 
            borderRadius: 8,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}>
          <Space size="small">
            <Text strong>{t('vaultEditor.vaultVersion')}</Text>
            <Tag color="processing" style={{ margin: 0, fontSize: 12 }}>{vaultVersion}</Tag>
          </Space>
          <Text type="secondary" style={{ fontSize: 11 }}>
            {t('vaultEditor.versionAutoIncrement')}
          </Text>
        </div>

        <VaultEditor
          entityType={entityType}
          initialData={vaultData}
          onChange={handleVaultChange}
          onValidate={handleValidate}
          onImportExport={(handlers) => {
            importExportHandlers.current = handlers
          }}
          onFieldMovement={(movedToExtra, movedFromExtra) => {
            // Field movement notifications are already shown by VaultEditor
            // This callback is optional for parent components that need to track movements
          }}
        />
      </Space>

      <div style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space size="small">
            <Upload
              accept=".json"
              showUploadList={false}
              beforeUpload={(file) => {
                if (importExportHandlers.current) {
                  return importExportHandlers.current.handleImport(file)
                }
                return false
              }}
            >
              <Button size="small" icon={<UploadOutlined />}>{t('vaultEditor.importJson')}</Button>
            </Upload>
            <Button 
              size="small"
              icon={<DownloadOutlined />} 
              onClick={() => {
                if (importExportHandlers.current) {
                  importExportHandlers.current.handleExport()
                }
              }}
            >
              {t('vaultEditor.exportJson')}
            </Button>
          </Space>
          
          <Space size="small">
            {hasChanges && (
              <Space size="small">
                <span style={{ color: '#faad14', fontSize: 12 }}>
                  <InfoCircleOutlined style={{ fontSize: 12 }} /> {t('vaultEditor.unsavedChanges')}
                </span>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  • {t('vaultEditor.versionWillIncrement', { version: vaultVersion + 1 })}
                </Text>
              </Space>
            )}
            <Button onClick={onCancel}>{t('actions.cancel')}</Button>
            <Button
              type="primary"
              onClick={handleSave}
              loading={loading}
              disabled={!isValid}
              style={{ background: '#556b2f', borderColor: '#556b2f' }}
            >
              {t('vaultEditor.saveVaultConfiguration')}
            </Button>
          </Space>
        </div>
      </div>

      {showValidationErrors && validationErrors.length > 0 && (
        <div style={{ marginTop: 16, color: '#ff4d4f' }}>
          <strong>{t('vaultEditor.validationErrors')}</strong>
          <ul style={{ marginTop: 8 }}>
            {validationErrors.map((error, index) => (
              <li key={index}>{error}</li>
            ))}
          </ul>
        </div>
      )}
    </Modal>
  )
}

export default VaultEditorModal