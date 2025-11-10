import React, { useState, useRef, useEffect } from 'react'
import { Modal, Button, Space, message, Typography, Tag, Upload, Tooltip } from 'antd'
import { InfoCircleOutlined, UploadOutlined, DownloadOutlined, CloseOutlined, SaveOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import VaultEditor from './VaultEditor'
import { useComponentStyles } from '@/hooks/useComponentStyles'
import { DESIGN_TOKENS, spacing, borderRadius, fontSize } from '@/utils/styleConstants'
import { ModalSize } from '@/types/modal'

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
  const validationErrorsRef = useRef<HTMLDivElement>(null)
  const styles = useComponentStyles()

  // Sync state with initial props when they change
  useEffect(() => {
    try {
      const parsed = JSON.parse(initialVault)
      setVaultData(parsed)
    } catch {
      setVaultData({})
    }
    setVaultVersion(initialVersion)
    setHasChanges(false)
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
    if (!isValid) {
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

  // Auto-scroll to validation errors when they appear
  useEffect(() => {
    if (showValidationErrors && validationErrorsRef.current) {
      validationErrorsRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
      })
    }
  }, [showValidationErrors])

  return (
    <Modal
      title={`${title} - ${entityType}`}
      open={open}
      onCancel={onCancel}
      className={ModalSize.Fullscreen}
      footer={null}
      data-testid="vault-modal"
      destroyOnHidden
    >
      <Space direction="vertical" style={{ width: '100%' }} size={spacing('SM')}>
        <div 
          className="bg-tertiary"
          style={{ 
            padding: spacing('SM'), 
            borderRadius: borderRadius('LG'),
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            backgroundColor: 'var(--color-fill-quaternary)'
          }}>
          <Space size="small">
            <Text strong style={{ fontSize: fontSize('SM') }}>{t('vaultEditor.vaultVersion')}</Text>
            <Tag 
              color="processing" 
              style={{ 
                margin: 0, 
                fontSize: fontSize('XS'),
                borderRadius: borderRadius('SM')
              }}
            >
              {vaultVersion}
            </Tag>
          </Space>
          <Text type="secondary" style={{ fontSize: fontSize('XS') }}>
            {t('vaultEditor.versionAutoIncrement')}
          </Text>
        </div>

        {/* Validation Errors - displayed at top for visibility */}
        {showValidationErrors && validationErrors.length > 0 && (
          <div
            ref={validationErrorsRef}
            style={{
              padding: spacing('MD'),
              backgroundColor: 'var(--color-error-bg)',
              border: '1px solid var(--color-error-border)',
              borderRadius: borderRadius('LG'),
              color: 'var(--color-error)',
              fontSize: fontSize('SM')
            }}
          >
            <strong style={{ display: 'block', marginBottom: spacing('XS') }}>
              {t('vaultEditor.validationErrors')}
            </strong>
            <ul style={{ margin: 0, paddingLeft: spacing('LG') }}>
              {validationErrors.map((error, index) => (
                <li key={index}>{error}</li>
              ))}
            </ul>
          </div>
        )}

        <VaultEditor
          entityType={entityType}
          initialData={vaultData}
          onChange={handleVaultChange}
          onValidate={handleValidate}
          onImportExport={(handlers) => {
            importExportHandlers.current = handlers
          }}
          onFieldMovement={(_movedToExtra, _movedFromExtra) => {
            // Field movement notifications are already shown by VaultEditor
            // This callback is optional for parent components that need to track movements
          }}
          data-testid="vault-modal-editor"
        />
      </Space>

      <div style={{ marginTop: spacing('MD') }}>
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
              data-testid="vault-modal-file-upload"
            >
              <Button 
                size="small" 
                icon={<UploadOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_SM }} />} 
                style={{
                  // Height managed by CSS
                  borderRadius: borderRadius('MD'),
                  fontSize: fontSize('SM')
                }}
                data-testid="vault-modal-import-button"
              >
                {t('vaultEditor.importJson')}
              </Button>
            </Upload>
            <Button 
              size="small"
              icon={<DownloadOutlined style={{ fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_SM }} />} 
              onClick={() => {
                if (importExportHandlers.current) {
                  importExportHandlers.current.handleExport()
                }
              }}
              style={{
                // Height managed by CSS
                borderRadius: borderRadius('MD'),
                fontSize: fontSize('SM')
              }}
              data-testid="vault-modal-export-button"
            >
              {t('vaultEditor.exportJson')}
            </Button>
          </Space>
          
          <Space size="small">
            {hasChanges && (
              <Space size="small">
                <span style={{ 
                  color: 'var(--color-warning)', 
                  fontSize: fontSize('XS'),
                  display: 'flex',
                  alignItems: 'center'
                }}>
                  <InfoCircleOutlined style={{ 
                    fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_SM,
                    marginRight: spacing('XS')
                  }} /> 
                  {t('vaultEditor.unsavedChanges')}
                </span>
                <Text type="secondary" style={{ fontSize: fontSize('XS') }}>
                  • {t('vaultEditor.versionWillIncrement', { version: vaultVersion + 1 })}
                </Text>
              </Space>
            )}
            <Tooltip title={t('actions.cancel')}>
              <Button 
                icon={<CloseOutlined />}
                onClick={onCancel} 
                style={{
                  // Height managed by CSS
                  borderRadius: borderRadius('LG'),
                  fontSize: fontSize('SM')
                }}
                data-testid="vault-modal-cancel-button"
                aria-label={t('actions.cancel')}
              />
            </Tooltip>
            <Tooltip title={t('vaultEditor.saveVaultConfiguration')}>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                onClick={handleSave}
                loading={loading}
                disabled={!isValid}
                style={{ 
                  ...styles.buttonPrimary,
                  background: 'var(--color-primary)', 
                  borderColor: 'var(--color-primary)'
                  // Height managed by CSS
                }}
                data-testid="vault-modal-save-button"
                aria-label={t('vaultEditor.saveVaultConfiguration')}
              />
            </Tooltip>
          </Space>
        </div>
      </div>
    </Modal>
  )
}

export default VaultEditorModal