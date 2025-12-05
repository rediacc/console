import React, { useState, useRef, useEffect } from 'react'
import { Modal, Space, message, Upload, Tooltip } from 'antd'
import type { RcFile } from 'antd/es/upload'
import { CloseOutlined, SaveOutlined } from '@/utils/optimizedIcons'
import { useTranslation } from 'react-i18next'
import VaultEditor from '../VaultEditor'
import { ModalSize } from '@/types/modal'
import {
  ActionGroup,
  CancelButton,
  ContentStack,
  DownloadIcon,
  FileActionButton,
  FileActions,
  FooterBar,
  FooterWrapper,
  UnsavedChangesText,
  UnsavedVersionHint,
  UploadIcon,
  ValidationAlert,
  ValidationList,
  ValidationTitle,
  VersionBanner,
  VersionDescription,
  VersionLabel,
  VersionTag,
  WarningIcon,
  SaveButton,
} from './styles'

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

const VERSION_HINT_BULLET = '\u2022'

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
  const [vaultData, setVaultData] = useState<Record<string, unknown>>({})
  const [vaultVersion, setVaultVersion] = useState(initialVersion)
  const [isValid, setIsValid] = useState(true)
  const [hasChanges, setHasChanges] = useState(false)
  const [validationErrors, setValidationErrors] = useState<string[]>([])
  const [showValidationErrors, setShowValidationErrors] = useState(false)
  const importExportHandlers = useRef<{ handleImport: (file: RcFile) => boolean; handleExport: () => void } | null>(null)
  const validationErrorsRef = useRef<HTMLDivElement>(null)

  /* eslint-disable react-hooks/set-state-in-effect */
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
  /* eslint-enable react-hooks/set-state-in-effect */

  const handleVaultChange = (data: Record<string, unknown>, changed: boolean) => {
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
    } catch {
      // Parent handles notification
    }
  }

  useEffect(() => {
    if (showValidationErrors && validationErrorsRef.current) {
      validationErrorsRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
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
      <ContentStack>
        <VersionBanner>
          <Space size="small">
            <VersionLabel strong>{t('vaultEditor.vaultVersion')}</VersionLabel>
            <VersionTag color="processing">{vaultVersion}</VersionTag>
          </Space>
          <VersionDescription>{t('vaultEditor.versionAutoIncrement')}</VersionDescription>
        </VersionBanner>

        {showValidationErrors && validationErrors.length > 0 && (
          <ValidationAlert ref={validationErrorsRef}>
            <ValidationTitle strong>{t('vaultEditor.validationErrors')}</ValidationTitle>
            <ValidationList>
              {validationErrors.map((error, index) => (
                <li key={index}>{error}</li>
              ))}
            </ValidationList>
          </ValidationAlert>
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
            // Parent can track movements if needed
          }}
          data-testid="vault-modal-editor"
        />
      </ContentStack>

      <FooterWrapper>
        <FooterBar>
          <FileActions>
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
              <FileActionButton
                size="small"
                icon={<UploadIcon />}
                data-testid="vault-modal-import-button"
              >
                {t('vaultEditor.importJson')}
              </FileActionButton>
            </Upload>
            <FileActionButton
              size="small"
              icon={<DownloadIcon />}
              onClick={() => {
                if (importExportHandlers.current) {
                  importExportHandlers.current.handleExport()
                }
              }}
              data-testid="vault-modal-export-button"
            >
              {t('vaultEditor.exportJson')}
            </FileActionButton>
          </FileActions>

          <ActionGroup>
            {hasChanges && (
              <>
                <UnsavedChangesText>
                  <WarningIcon />
                  {t('vaultEditor.unsavedChanges')}
                </UnsavedChangesText>
                <UnsavedVersionHint type="secondary">
                  {VERSION_HINT_BULLET} {t('vaultEditor.versionWillIncrement', { version: vaultVersion + 1 })}
                </UnsavedVersionHint>
              </>
            )}
            <Tooltip title={t('actions.cancel')}>
              <CancelButton
                icon={<CloseOutlined />}
                onClick={onCancel}
                data-testid="vault-modal-cancel-button"
                aria-label={t('actions.cancel')}
              />
            </Tooltip>
            <Tooltip title={t('vaultEditor.saveVaultConfiguration')}>
              <SaveButton
                type="primary"
                icon={<SaveOutlined />}
                onClick={handleSave}
                loading={loading}
                disabled={!isValid}
                data-testid="vault-modal-save-button"
                aria-label={t('vaultEditor.saveVaultConfiguration')}
              />
            </Tooltip>
          </ActionGroup>
        </FooterBar>
      </FooterWrapper>
    </Modal>
  )
}

export default VaultEditorModal

