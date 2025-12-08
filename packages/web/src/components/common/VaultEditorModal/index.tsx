import React, { useState, useRef, useEffect } from 'react';
import { Modal, Space, message, Upload, Tooltip } from 'antd';
import { useTranslation } from 'react-i18next';
import VaultEditor from '@/components/common/VaultEditor';
import { RediaccButton, RediaccText, RediaccStack } from '@/components/ui';
import { ActionGroup } from '@/components/common/styled';
import { ModalSize } from '@/types/modal';
import { CloseOutlined, SaveOutlined } from '@/utils/optimizedIcons';
import {
  DownloadIcon,
  FileActionButton,
  FileActions,
  FooterBar,
  FooterWrapper,
  UnsavedChangesText,
  UploadIcon,
  ValidationAlert,
  ValidationList,
  VersionBanner,
  VersionTag,
  WarningIcon,
} from './styles';
import type { RcFile } from 'antd/es/upload';

interface VaultEditorModalProps {
  open: boolean;
  onCancel: () => void;
  onSave: (vault: string, version: number) => Promise<void>;
  entityType: string;
  title?: string;
  initialVault?: string;
  initialVersion?: number;
  loading?: boolean;
}

const VERSION_HINT_BULLET = '•';

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
  const { t } = useTranslation('common');
  const [vaultData, setVaultData] = useState<Record<string, unknown>>({});
  const [vaultVersion, setVaultVersion] = useState(initialVersion);
  const [isValid, setIsValid] = useState(true);
  const [hasChanges, setHasChanges] = useState(false);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [showValidationErrors, setShowValidationErrors] = useState(false);
  const importExportHandlers = useRef<{
    handleImport: (file: RcFile) => boolean;
    handleExport: () => void;
  } | null>(null);
  const validationErrorsRef = useRef<HTMLDivElement>(null);

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    try {
      const parsed = JSON.parse(initialVault);
      setVaultData(parsed);
    } catch {
      setVaultData({});
    }
    setVaultVersion(initialVersion);
    setHasChanges(false);
    setValidationErrors([]);
    setShowValidationErrors(false);
  }, [initialVault, initialVersion]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const handleVaultChange = (data: Record<string, unknown>, changed: boolean) => {
    setVaultData(data);
    setHasChanges(changed);
  };

  const handleValidate = (valid: boolean, errors?: string[]) => {
    setIsValid(valid);
    setValidationErrors(errors || []);
  };

  const handleSave = async () => {
    if (!isValid) {
      setShowValidationErrors(true);
      message.error(t('vaultEditor.pleaseFixErrors'));
      return;
    }

    try {
      const vaultJson = JSON.stringify(vaultData);
      await onSave(vaultJson, vaultVersion);
      onCancel();
    } catch {
      // Parent handles notification
    }
  };

  useEffect(() => {
    if (showValidationErrors && validationErrorsRef.current) {
      validationErrorsRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      });
    }
  }, [showValidationErrors]);

  return (
    <Modal
      title={`${title} - ${entityType}`}
      open={open}
      onCancel={onCancel}
      className={ModalSize.Fullscreen}
      footer={null}
      data-testid="vault-modal"
      destroyOnClose
    >
      <RediaccStack variant="spaced-column" fullWidth>
        <VersionBanner>
          <Space size="small">
            <RediaccText variant="label" weight="bold">
              {t('vaultEditor.vaultVersion')}
            </RediaccText>
            <VersionTag variant="info">{vaultVersion}</VersionTag>
          </Space>
          <RediaccText variant="helper">{t('vaultEditor.versionAutoIncrement')}</RediaccText>
        </VersionBanner>

        {showValidationErrors && validationErrors.length > 0 && (
          <ValidationAlert ref={validationErrorsRef}>
            <RediaccText
              variant="title"
              weight="bold"
              style={{ display: 'block', marginBottom: 4 }}
            >
              {t('vaultEditor.validationErrors')}
            </RediaccText>
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
            importExportHandlers.current = handlers;
          }}
          onFieldMovement={(_movedToExtra, _movedFromExtra) => {
            // Parent can track movements if needed
          }}
          data-testid="vault-modal-editor"
        />
      </RediaccStack>

      <FooterWrapper>
        <FooterBar>
          <FileActions>
            <Upload
              accept=".json"
              showUploadList={false}
              beforeUpload={(file) => {
                if (importExportHandlers.current) {
                  return importExportHandlers.current.handleImport(file);
                }
                return false;
              }}
              data-testid="vault-modal-file-upload"
            >
              <FileActionButton
                size="sm"
                icon={<UploadIcon />}
                data-testid="vault-modal-import-button"
              >
                {t('vaultEditor.importJson')}
              </FileActionButton>
            </Upload>
            <FileActionButton
              size="sm"
              icon={<DownloadIcon />}
              onClick={() => {
                if (importExportHandlers.current) {
                  importExportHandlers.current.handleExport();
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
                <RediaccText variant="helper">
                  {VERSION_HINT_BULLET}{' '}
                  {t('vaultEditor.versionWillIncrement', { version: vaultVersion + 1 })}
                </RediaccText>
              </>
            )}
            <Tooltip title={t('actions.cancel')}>
              <RediaccButton
                iconOnly
                icon={<CloseOutlined />}
                onClick={onCancel}
                data-testid="vault-modal-cancel-button"
                aria-label={t('actions.cancel')}
              />
            </Tooltip>
            <Tooltip title={t('vaultEditor.saveVaultConfiguration')}>
              <RediaccButton
                iconOnly
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
  );
};

export default VaultEditorModal;
